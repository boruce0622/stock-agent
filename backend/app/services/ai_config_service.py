from time import perf_counter

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import SecretCipher, mask_secret
from app.db.models import AIConfiguration
from app.llm.providers import resolve_base_url
from app.schemas.ai_config import AIConfigOut, AIConfigPayload, AIConnectionTestOut

CONFIG_ID = "default"


async def get_stored_config(db: AsyncSession) -> AIConfiguration | None:
    return await db.get(AIConfiguration, CONFIG_ID)


async def get_public_config(db: AsyncSession) -> AIConfigOut:
    config = await get_stored_config(db)
    if config is None:
        return AIConfigOut(configured=False)
    api_key = SecretCipher().decrypt(config.api_key_encrypted)
    return AIConfigOut(
        configured=True,
        provider=config.provider,
        model=config.model,
        base_url=config.base_url,
        api_key_masked=mask_secret(api_key),
        enabled=config.enabled,
    )


async def save_config(db: AsyncSession, payload: AIConfigPayload) -> AIConfigOut:
    config = await get_stored_config(db)
    submitted_key = payload.api_key.get_secret_value() if payload.api_key else None
    if config is None and not submitted_key:
        raise ValueError("首次保存必须填写 API Key")
    base_url = resolve_base_url(payload.provider, payload.base_url)
    if config is None:
        config = AIConfiguration(
            id=CONFIG_ID,
            provider=payload.provider,
            model=payload.model,
            base_url=base_url,
            api_key_encrypted=SecretCipher().encrypt(submitted_key or ""),
            enabled=payload.enabled,
        )
        db.add(config)
    else:
        config.provider = payload.provider
        config.model = payload.model
        config.base_url = base_url
        config.enabled = payload.enabled
        if submitted_key:
            config.api_key_encrypted = SecretCipher().encrypt(submitted_key)
    await db.commit()
    return await get_public_config(db)


def build_chat_model(*, model: str, api_key: str, base_url: str | None = None) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=settings.llm_temperature,
        max_tokens=1200,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


async def build_saved_chat_model(db: AsyncSession) -> ChatOpenAI | None:
    config = await get_stored_config(db)
    if config is None or not config.enabled:
        return None
    api_key = SecretCipher().decrypt(config.api_key_encrypted)
    return build_chat_model(model=config.model, api_key=api_key, base_url=config.base_url)


async def test_connection(db: AsyncSession, payload: AIConfigPayload) -> AIConnectionTestOut:
    config = await get_stored_config(db)
    submitted_key = payload.api_key.get_secret_value() if payload.api_key else None
    if submitted_key:
        api_key = submitted_key
    elif config:
        api_key = SecretCipher().decrypt(config.api_key_encrypted)
    else:
        raise ValueError("请填写 API Key")

    chat_model = build_chat_model(
        model=payload.model,
        api_key=api_key,
        base_url=resolve_base_url(payload.provider, payload.base_url),
    )
    started = perf_counter()
    response = await chat_model.ainvoke(
        [
            SystemMessage(content="你是连接检测助手。"),
            HumanMessage(content="仅回复 OK。"),
        ]
    )
    latency_ms = int((perf_counter() - started) * 1000)
    content = response.content if isinstance(response.content, str) else str(response.content)
    return AIConnectionTestOut(
        ok=bool(content.strip()),
        model=payload.model,
        latency_ms=latency_ms,
        message="连接成功",
    )
