import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Conversation, Message, new_id
from app.db.session import get_db
from app.schemas.chat import ConversationCreate, ConversationOut, MessageOut, RunAccepted, RunCreate
from app.services.chat_service import (
    get_terminal_run_events,
    run_exists,
    schedule_run,
)
from app.services.run_broker import run_broker

router = APIRouter(prefix="/api/v1")


@router.get("/health/live")
async def liveness() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    await db.execute(select(1))
    return {"status": "ready", "market_data": "fake"}


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(body: ConversationCreate, db: AsyncSession = Depends(get_db)):
    conversation = Conversation(id=new_id(), title=body.title)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(
        select(Conversation)
        .where(Conversation.deleted_at.is_(None))
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    )
    return list(result)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(conversation_id: str, db: AsyncSession = Depends(get_db)):
    if await db.get(Conversation, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    latest_messages = (
        select(Message.id)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(500)
        .subquery()
    )
    result = await db.scalars(
        select(Message)
        .join(latest_messages, latest_messages.c.id == Message.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return list(result)


@router.post(
    "/conversations/{conversation_id}/runs",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(conversation_id: str, body: RunCreate, db: AsyncSession = Depends(get_db)):
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    existing = await db.scalar(
        select(AgentRun).where(
            AgentRun.conversation_id == conversation_id,
            AgentRun.idempotency_key == body.client_request_id,
        )
    )
    if existing:
        return RunAccepted(
            run_id=existing.id,
            conversation_id=conversation_id,
            status=existing.status,
            events_url=f"/api/v1/runs/{existing.id}/events",
        )

    now = datetime.now(UTC)
    run_id = new_id()
    db.add(
        AgentRun(
            id=run_id,
            conversation_id=conversation_id,
            status="queued",
            idempotency_key=body.client_request_id,
            created_at=now,
        )
    )
    db.add(
        Message(
            id=new_id(),
            conversation_id=conversation_id,
            run_id=run_id,
            role="user",
            content=body.message.strip(),
            extra_data={},
            created_at=now,
        )
    )
    if conversation.title == "新会话":
        conversation.title = body.message.strip()[:30]
    conversation.updated_at = now
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate request") from None

    schedule_run(run_id, conversation_id, body.message.strip())
    return RunAccepted(
        run_id=run_id,
        conversation_id=conversation_id,
        status="queued",
        events_url=f"/api/v1/runs/{run_id}/events",
    )


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str, request: Request, last_event_id: str | None = Header(default=None)
):
    if not await run_exists(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    after = int(last_event_id or 0)
    terminal_events = (
        []
        if run_broker.has_events(run_id)
        else await get_terminal_run_events(run_id, include_content=after == 0)
    )

    def encode_event(item: dict, event_id: int | None = None) -> str:
        data = {"run_id": run_id, **item["data"]}
        payload = json.dumps(data, ensure_ascii=False)
        prefix = f"id: {event_id}\n" if event_id is not None else ""
        return f"{prefix}event: {item['event']}\ndata: {payload}\n\n"

    async def event_source():
        if terminal_events:
            for item in terminal_events:
                yield encode_event(item)
            return
        async for item in run_broker.subscribe(run_id, after):
            if await request.is_disconnected():
                break
            if item["event"] == "heartbeat":
                recovered = await get_terminal_run_events(run_id, include_content=after == 0)
                if recovered:
                    for terminal_item in recovered:
                        yield encode_event(terminal_item)
                    return
            yield encode_event(item, item.get("id"))

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        update(AgentRun)
        .where(
            AgentRun.id == run_id,
            AgentRun.status.in_(("queued", "running")),
        )
        .values(status="cancelling")
    )
    if result.rowcount != 1:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"run_id": run_id, "status": run.status}
    await db.commit()
    run_broker.cancel(run_id)
    return {"run_id": run_id, "status": "cancelling"}
