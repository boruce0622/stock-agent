from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.market_config import (
    MarketConfigOut,
    MarketConfigPayload,
    MarketConnectionTestOut,
)
from app.services.market_config_service import (
    get_public_market_config,
    save_market_config,
    test_market_connection,
)

router = APIRouter(prefix="/api/v1/market-config", tags=["Market data configuration"])


@router.get("", response_model=MarketConfigOut)
async def read_market_config(db: AsyncSession = Depends(get_db)):
    try:
        return await get_public_market_config(db)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("", response_model=MarketConfigOut)
async def update_market_config(payload: MarketConfigPayload, db: AsyncSession = Depends(get_db)):
    try:
        return await save_market_config(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/test", response_model=MarketConnectionTestOut)
async def test_market_data_connection(
    payload: MarketConfigPayload, db: AsyncSession = Depends(get_db)
):
    try:
        return await test_market_connection(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
