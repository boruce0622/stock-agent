from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.llm.providers import PROVIDER_PRESETS
from app.schemas.ai_config import (
    AIConfigOut,
    AIConfigPayload,
    AIConnectionTestOut,
    AIProviderOut,
)
from app.services.ai_config_service import get_public_config, save_config, test_connection

router = APIRouter(prefix="/api/v1/ai-config", tags=["AI configuration"])


@router.get("/providers", response_model=list[AIProviderOut])
async def list_ai_providers():
    return [preset.to_dict() for preset in PROVIDER_PRESETS.values()]


@router.get("", response_model=AIConfigOut)
async def read_ai_config(db: AsyncSession = Depends(get_db)):
    try:
        return await get_public_config(db)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("", response_model=AIConfigOut)
async def update_ai_config(payload: AIConfigPayload, db: AsyncSession = Depends(get_db)):
    try:
        return await save_config(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/test", response_model=AIConnectionTestOut)
async def test_ai_connection(payload: AIConfigPayload, db: AsyncSession = Depends(get_db)):
    try:
        return await test_connection(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="连接失败，请检查模型、地址和 API Key") from exc
