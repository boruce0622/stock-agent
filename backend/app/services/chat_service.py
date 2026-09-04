import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import select, update

from app.agent.graph import StockAgentGraph
from app.db.models import AgentRun, Conversation, Message, ToolCall, new_id
from app.db.session import SessionLocal
from app.llm.gateway import LangChainLLMGateway
from app.providers.public_realtime import PublicRealtimeMarketDataProvider
from app.services.ai_config_service import build_saved_chat_model
from app.services.market_config_service import build_market_provider
from app.services.run_broker import run_broker

logger = logging.getLogger(__name__)
HISTORY_MESSAGE_LIMIT = 20
HISTORY_CHARACTER_LIMIT = 12_000
_active_run_tasks: set[asyncio.Task] = set()


def schedule_run(run_id: str, conversation_id: str, query: str) -> None:
    task = asyncio.create_task(execute_run(run_id, conversation_id, query))
    _active_run_tasks.add(task)
    task.add_done_callback(_active_run_tasks.discard)


async def recover_incomplete_runs() -> None:
    """Requeue runs interrupted by a process restart and resume their saved query."""
    async with SessionLocal() as db:
        rows = await db.execute(
            select(AgentRun.id, AgentRun.conversation_id, AgentRun.status, Message.content)
            .join(Message, Message.run_id == AgentRun.id)
            .where(
                AgentRun.status.in_(("queued", "running", "cancelling")),
                Message.role == "user",
            )
        )
        pending = list(rows)
        await db.execute(
            update(AgentRun).where(AgentRun.status == "running").values(status="queued")
        )
        await db.commit()

    for run_id, conversation_id, run_status, query in pending:
        if run_status == "cancelling":
            await mark_cancelled(run_id)
        else:
            schedule_run(run_id, conversation_id, query)


async def shutdown_background_runs() -> None:
    tasks = list(_active_run_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def execute_run(run_id: str, conversation_id: str, query: str) -> None:
    started = perf_counter()
    try:
        async with SessionLocal() as db:
            claimed = await db.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id, AgentRun.status == "queued")
                .values(status="running")
            )
            if claimed.rowcount != 1:
                run = await db.get(AgentRun, run_id)
                if run and run.status == "cancelling":
                    await db.rollback()
                    await mark_cancelled(run_id)
                return
            chat_model = await build_saved_chat_model(db)
            market_provider = await build_market_provider(db)
            conversation = await db.get(Conversation, conversation_id)
            history = await load_conversation_history(db, conversation_id, run_id)
            current_symbol = conversation.current_symbol if conversation else None
            await db.commit()

        llm = LangChainLLMGateway(chat_model) if chat_model else None
        agent = StockAgentGraph(
            market_provider,
            llm=llm,
            resolver=PublicRealtimeMarketDataProvider(),
        )

        await run_broker.publish(
            run_id, "run.status", {"status": "running", "stage": "ai_planning"}
        )
        final_state = None
        initial_state = {
            "query": query,
            "conversation_id": conversation_id,
            "conversation_history": history,
            "current_symbol": current_symbol,
        }
        async for graph_update in agent.graph.astream(initial_state, stream_mode="updates"):
            if run_broker.is_cancelled(run_id) or await run_cancel_requested(run_id):
                await mark_cancelled(run_id)
                return
            node, values = next(iter(graph_update.items()))
            final_state = {**(final_state or initial_state), **values}
            if node == "plan":
                stage = (
                    "collecting_evidence"
                    if values.get("plan", {}).get("tools")
                    else "ai_synthesizing"
                )
                await run_broker.publish(
                    run_id,
                    "run.status",
                    {
                        "status": "running",
                        "stage": stage,
                        "analysis_mode": values.get("analysis_mode"),
                        "plan": values.get("plan"),
                    },
                )
            elif node == "execute_tools":
                for name, result in values.get("evidence", {}).items():
                    await save_tool_call(run_id, name, result, final_state.get("symbol"))
                    await run_broker.publish(
                        run_id,
                        "tool.result",
                        {
                            "name": name,
                            "status": ("failed" if result.get("ok", True) is False else "success"),
                            "source": result.get("source"),
                            "as_of": result.get("as_of"),
                        },
                    )
                await run_broker.publish(
                    run_id, "run.status", {"status": "running", "stage": "ai_synthesizing"}
                )
            elif node == "respond":
                answer = values["answer"]
                for start in range(0, len(answer), 18):
                    if run_broker.is_cancelled(run_id) or await run_cancel_requested(run_id):
                        await mark_cancelled(run_id)
                        return
                    chunk = answer[start : start + 18]
                    await run_broker.publish(run_id, "message.delta", {"content": chunk})
                    await asyncio.sleep(0.01)

        answer = (final_state or {}).get("answer", "暂时无法生成回答。")
        message_id = await complete_run(
            run_id,
            conversation_id,
            answer,
            started,
            (final_state or {}).get("symbol"),
        )
        await run_broker.publish(run_id, "message.completed", {"message_id": message_id})
    except Exception:
        logger.exception("Agent run failed", extra={"run_id": run_id})
        async with SessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            if run:
                run.status = "failed"
                run.error_code = "AGENT_RUN_FAILED"
                run.completed_at = datetime.now(UTC)
                await db.commit()
        await run_broker.publish(
            run_id,
            "run.error",
            {"code": "AGENT_RUN_FAILED", "message": "Agent 运行失败，请稍后重试"},
        )


async def save_tool_call(run_id: str, tool_name: str, result: dict, symbol: str | None) -> None:
    as_of = result.get("as_of")
    async with SessionLocal() as db:
        db.add(
            ToolCall(
                id=new_id(),
                run_id=run_id,
                tool_name=tool_name,
                arguments_redacted={"symbol": symbol},
                status="failed" if result.get("ok", True) is False else "success",
                source=result.get("source"),
                data_as_of=datetime.fromisoformat(as_of) if as_of else None,
                latency_ms=result.get("latency_ms"),
            )
        )
        await db.commit()


async def load_conversation_history(
    db, conversation_id: str, current_run_id: str, limit: int = HISTORY_MESSAGE_LIMIT
) -> list[dict[str, str]]:
    """Load recent completed turns, excluding the user message for the current run."""
    result = await db.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.run_id != current_run_id,
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    newest_first: list[dict[str, str]] = []
    remaining = HISTORY_CHARACTER_LIMIT
    for item in result:
        if remaining <= 0:
            break
        content = item.content.strip()[:remaining]
        if content:
            newest_first.append({"role": item.role, "content": content})
            remaining -= len(content)
    return list(reversed(newest_first))


async def complete_run(
    run_id: str,
    conversation_id: str,
    answer: str,
    started: float,
    symbol: str | None = None,
) -> str:
    now = datetime.now(UTC)
    message_id = new_id()
    async with SessionLocal() as db:
        run = await db.get(AgentRun, run_id)
        conversation = await db.get(Conversation, conversation_id)
        db.add(
            Message(
                id=message_id,
                conversation_id=conversation_id,
                run_id=run_id,
                role="assistant",
                content=answer,
                extra_data={},
                created_at=now,
            )
        )
        if run:
            run.status = "completed"
            run.latency_ms = int((perf_counter() - started) * 1000)
            run.completed_at = now
        if conversation:
            conversation.updated_at = now
            if symbol:
                conversation.current_symbol = symbol
        await db.commit()
    return message_id


async def mark_cancelled(run_id: str) -> None:
    async with SessionLocal() as db:
        result = await db.execute(
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status.in_(("queued", "running", "cancelling")),
            )
            .values(status="cancelled", completed_at=datetime.now(UTC))
        )
        await db.commit()
    if result.rowcount:
        await run_broker.publish(run_id, "run.cancelled", {"status": "cancelled"})


async def run_cancel_requested(run_id: str) -> bool:
    async with SessionLocal() as db:
        status = await db.scalar(select(AgentRun.status).where(AgentRun.id == run_id))
        return status in {"cancelling", "cancelled"}


async def get_terminal_run_events(run_id: str, include_content: bool) -> list[dict]:
    """Reconstruct terminal SSE events after an in-memory broker restart."""
    async with SessionLocal() as db:
        run = await db.get(AgentRun, run_id)
        if run is None or run.status not in {"completed", "failed", "cancelled"}:
            return []
        if run.status == "completed":
            message = await db.scalar(
                select(Message).where(
                    Message.run_id == run_id,
                    Message.role == "assistant",
                )
            )
            if message is None:
                return []
            events = []
            if include_content:
                events.append({"event": "message.delta", "data": {"content": message.content}})
            events.append({"event": "message.completed", "data": {"message_id": message.id}})
            return events
        if run.status == "cancelled":
            return [{"event": "run.cancelled", "data": {"status": "cancelled"}}]
        return [
            {
                "event": "run.error",
                "data": {
                    "code": run.error_code or "AGENT_RUN_FAILED",
                    "message": "Agent 运行失败，请稍后重试",
                },
            }
        ]


async def run_exists(run_id: str) -> bool:
    async with SessionLocal() as db:
        return (await db.scalar(select(AgentRun.id).where(AgentRun.id == run_id))) is not None
