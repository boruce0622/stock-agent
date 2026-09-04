from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MarketDataConfiguration
from app.providers.base import MarketDataProvider
from app.providers.fake_market_data import FakeMarketDataProvider
from app.providers.hybrid_market_data import HybridMarketDataProvider
from app.schemas.market_config import (
    MarketConfigOut,
    MarketConfigPayload,
    MarketConnectionTestOut,
)

CONFIG_ID = "default"


async def get_market_config(db: AsyncSession) -> MarketDataConfiguration | None:
    return await db.get(MarketDataConfiguration, CONFIG_ID)


async def get_public_market_config(db: AsyncSession) -> MarketConfigOut:
    config = await get_market_config(db)
    if config is None:
        return MarketConfigOut(configured=False)
    return MarketConfigOut(
        configured=True,
        provider="hybrid",
        enabled=config.enabled,
    )


async def save_market_config(db: AsyncSession, payload: MarketConfigPayload) -> MarketConfigOut:
    config = await get_market_config(db)
    if config is None:
        config = MarketDataConfiguration(
            id=CONFIG_ID,
            provider=payload.provider,
            credential_encrypted="",
            enabled=payload.enabled,
        )
        db.add(config)
    else:
        config.provider = payload.provider
        config.enabled = payload.enabled
        config.credential_encrypted = ""
    await db.commit()
    return await get_public_market_config(db)


async def build_market_provider(db: AsyncSession) -> MarketDataProvider:
    config = await get_market_config(db)
    if config is None or not config.enabled:
        return FakeMarketDataProvider()
    return HybridMarketDataProvider()


async def test_market_connection(
    db: AsyncSession, payload: MarketConfigPayload
) -> MarketConnectionTestOut:
    started = perf_counter()
    quote = await HybridMarketDataProvider().get_stock_quote("300033.SZ")
    if not quote.ok:
        raise ValueError(quote.error or "AKShare 行情连接失败")
    return MarketConnectionTestOut(
        ok=True,
        provider="hybrid",
        latency_ms=int((perf_counter() - started) * 1000),
        sample_symbol="300033.SZ",
        data_as_of=quote.as_of.isoformat(),
        message="已通过 AKShare/Baostock 混合行情源获取数据",
    )
