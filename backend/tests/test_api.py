import os
from datetime import UTC, datetime, timedelta

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import AgentRun, Conversation, Message, new_id
from app.db.session import SessionLocal
from app.main import app
from app.services import chat_service


@pytest.mark.asyncio
async def test_health_and_conversation():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/api/v1/health/live")
            created = await client.post("/api/v1/conversations", json={"title": "测试"})

    assert health.status_code == 200
    assert created.status_code == 201
    assert created.json()["title"] == "测试"


@pytest.mark.asyncio
async def test_provider_catalog_contains_domestic_vendors():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/ai-config/providers")

    provider_ids = {item["id"] for item in response.json()}
    assert response.status_code == 200
    assert {"deepseek", "zhipu", "kimi", "minimax", "qwen", "doubao"}.issubset(provider_ids)


@pytest.mark.asyncio
async def test_knowledge_search_exposes_rag_hits():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/knowledge/search", params={"q": "科创板代码"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["hits"][0]["source"].startswith("knowledge/")


@pytest.mark.asyncio
async def test_complete_chat_run_streams_and_persists():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            conversation = await client.post("/api/v1/conversations", json={})
            conversation_id = conversation.json()["id"]
            accepted = await client.post(
                f"/api/v1/conversations/{conversation_id}/runs",
                json={
                    "message": "贵州茅台今天涨了多少？",
                    "client_request_id": "test-request-0001",
                },
            )
            run = accepted.json()
            events = await client.get(run["events_url"])
            history = await client.get(f"/api/v1/conversations/{conversation_id}/messages")

    assert accepted.status_code == 202
    assert events.status_code == 200
    assert "event: tool.result" in events.text
    assert "event: message.completed" in events.text
    assert [message["role"] for message in history.json()] == ["user", "assistant"]
    assert "1488.88" in history.json()[1]["content"]


@pytest.mark.asyncio
async def test_follow_up_run_remembers_previous_stock():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            conversation = await client.post("/api/v1/conversations", json={})
            conversation_id = conversation.json()["id"]
            first = await client.post(
                f"/api/v1/conversations/{conversation_id}/runs",
                json={
                    "message": "贵州茅台今天涨了多少？",
                    "client_request_id": "memory-request-0001",
                },
            )
            await client.get(first.json()["events_url"])

            second = await client.post(
                f"/api/v1/conversations/{conversation_id}/runs",
                json={
                    "message": "它现在多少钱？",
                    "client_request_id": "memory-request-0002",
                },
            )
            events = await client.get(second.json()["events_url"])
            history = await client.get(f"/api/v1/conversations/{conversation_id}/messages")

    assert "event: message.completed" in events.text
    assert [message["role"] for message in history.json()] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert "1488.88" in history.json()[-1]["content"]


@pytest.mark.asyncio
async def test_message_history_returns_latest_500_in_chronological_order():
    async with app.router.lifespan_context(app):
        conversation_id = new_id()
        started = datetime.now(UTC)
        async with SessionLocal() as db:
            db.add(Conversation(id=conversation_id, title="长对话"))
            db.add_all(
                [
                    Message(
                        id=new_id(),
                        conversation_id=conversation_id,
                        role="user",
                        content=f"message-{index}",
                        extra_data={},
                        created_at=started + timedelta(seconds=index),
                    )
                    for index in range(502)
                ]
            )
            await db.commit()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(f"/api/v1/conversations/{conversation_id}/messages")

    contents = [item["content"] for item in response.json()]
    assert len(contents) == 500
    assert contents[0] == "message-2"
    assert contents[-1] == "message-501"


@pytest.mark.asyncio
async def test_recovery_requeues_interrupted_run(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        chat_service,
        "schedule_run",
        lambda run_id, conversation_id, query: scheduled.append((run_id, conversation_id, query)),
    )
    async with app.router.lifespan_context(app):
        conversation_id = new_id()
        run_id = new_id()
        now = datetime.now(UTC)
        async with SessionLocal() as db:
            db.add(Conversation(id=conversation_id, title="恢复测试"))
            db.add(
                AgentRun(
                    id=run_id,
                    conversation_id=conversation_id,
                    status="running",
                    idempotency_key="recovery-request-0001",
                    created_at=now,
                )
            )
            db.add(
                Message(
                    id=new_id(),
                    conversation_id=conversation_id,
                    run_id=run_id,
                    role="user",
                    content="恢复这次分析",
                    extra_data={},
                    created_at=now,
                )
            )
            await db.commit()

        await chat_service.recover_incomplete_runs()
        async with SessionLocal() as db:
            recovered = await db.get(AgentRun, run_id)
            assert recovered.status == "queued"

    assert scheduled == [(run_id, conversation_id, "恢复这次分析")]
