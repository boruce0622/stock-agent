import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
from langchain_core.messages import AIMessage

from app.core.crypto import SecretCipher
from app.db.session import SessionLocal
from app.llm.providers import PROVIDER_PRESETS, resolve_base_url
from app.main import app
from app.schemas.ai_config import AIConfigPayload
from app.services import ai_config_service


class StubChatModel:
    async def ainvoke(self, _messages):
        return AIMessage(content="OK")


def test_secret_cipher_does_not_store_plaintext():
    cipher = SecretCipher("test-encryption-secret")
    encrypted = cipher.encrypt("sk-test-secret-value")

    assert "sk-test" not in encrypted
    assert cipher.decrypt(encrypted) == "sk-test-secret-value"


def test_domestic_provider_presets_have_compatible_urls():
    expected = {"deepseek", "zhipu", "kimi", "minimax", "qwen", "doubao"}

    assert expected.issubset(PROVIDER_PRESETS)
    for provider_id in expected:
        assert resolve_base_url(provider_id, None).startswith("https://")


@pytest.mark.asyncio
async def test_save_returns_masked_key_only():
    async with app.router.lifespan_context(app):
        async with SessionLocal() as db:
            result = await ai_config_service.save_config(
                db,
                AIConfigPayload(
                    model="test-model",
                    api_key="sk-test-secret-value",
                    enabled=False,
                ),
            )

    assert result.configured is True
    assert result.api_key_masked == "sk-••••••••alue"
    assert not hasattr(result, "api_key")


@pytest.mark.asyncio
async def test_connection_uses_submitted_settings(monkeypatch):
    monkeypatch.setattr(ai_config_service, "build_chat_model", lambda **_kwargs: StubChatModel())
    async with app.router.lifespan_context(app):
        async with SessionLocal() as db:
            result = await ai_config_service.test_connection(
                db,
                AIConfigPayload(
                    provider="deepseek",
                    model="test-model",
                    api_key="sk-test-new-key",
                ),
            )

    assert result.ok is True
    assert result.model == "test-model"
