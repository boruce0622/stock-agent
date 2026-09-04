from datetime import UTC, datetime

import pytest

from app.db.models import MarketDataConfiguration
from app.db.session import SessionLocal
from app.main import app
from app.providers.akshare_market_data import AKShareMarketDataProvider
from app.providers.base import ToolEnvelope
from app.providers.hybrid_market_data import HybridMarketDataProvider
from app.providers.symbol_resolver import classify_a_share_board, resolve_symbols
from app.schemas.market_config import MarketConfigPayload
from app.services.market_config_service import build_market_provider, save_market_config


def test_resolves_a_share_hk_codes_and_known_names():
    assert resolve_symbols("中国平安今天走势")[0]["symbol"] == "601318.SH"
    assert resolve_symbols("看看 2318.HK") == [{"symbol": "02318.HK", "name": "02318.HK"}]
    assert resolve_symbols("分析601318")[0]["board"] == "沪市主板"


def test_classifies_all_supported_a_share_boards():
    assert classify_a_share_board("600519.SH")["board"] == "沪市主板"
    assert classify_a_share_board("000001.SZ")["board"] == "深市主板"
    assert classify_a_share_board("688836.SH")["board"] == "科创板"
    assert classify_a_share_board("300750.SZ")["board"] == "创业板"
    assert classify_a_share_board("920001.BJ")["board"] == "北交所"
    assert classify_a_share_board("510300.SH") is None


def test_normalizes_akshare_quote():
    values = {
        "最新": 50.8,
        "涨跌": 0.8,
        "涨幅": 1.6,
        "最高": 51.2,
        "最低": 49.8,
        "今开": 50.1,
        "昨收": 50.0,
        "总手": 12345,
        "金额": 62500000,
    }

    data = AKShareMarketDataProvider._normalize_quote(values, "601318.SH")

    assert data["name"] == "中国平安"
    assert data["price"] == 50.8
    assert data["change"] == pytest.approx(0.8)
    assert data["change_pct"] == pytest.approx(1.6)
    assert data["currency"] == "CNY"


def test_rejects_invalid_akshare_quote():
    with pytest.raises(ValueError, match="最新价无效"):
        AKShareMarketDataProvider._normalize_quote({"最新": "--"}, "601318.SH")


@pytest.mark.asyncio
async def test_market_config_needs_no_credential():
    async with app.router.lifespan_context(app):
        async with SessionLocal() as db:
            result = await save_market_config(db, MarketConfigPayload(enabled=True))
            stored = await db.get(MarketDataConfiguration, "default")
            provider = await build_market_provider(db)

    assert result.provider == "hybrid"
    assert result.enabled is True
    assert stored.credential_encrypted == ""
    assert isinstance(provider, HybridMarketDataProvider)


class StubRealtime:
    def __init__(self, quote):
        self.quote = quote

    async def resolve_stock(self, _query):
        return []

    async def get_stock_quote(self, _symbol):
        return self.quote


class StubHistory:
    def __init__(self, row):
        self.row = row

    async def get_recent_daily(self, _symbol):
        return self.row


@pytest.mark.asyncio
async def test_hybrid_provider_cross_checks_previous_close():
    quote = ToolEnvelope(
        ok=True,
        data={"previous_close": 50.0},
        source="AKShare",
        as_of=datetime.now(UTC),
    )
    history = {"date": "2026-09-02", "close": "50.00"}
    provider = HybridMarketDataProvider(StubRealtime(quote), StubHistory(history))

    result = await provider.get_stock_quote("601318.SH")

    assert result.ok is True
    assert result.data["cross_check"]["status"] == "matched"
    assert "Baostock" in result.source


@pytest.mark.asyncio
async def test_hybrid_provider_falls_back_to_baostock_daily_bar():
    quote = ToolEnvelope(
        ok=False,
        data={},
        source="AKShare",
        as_of=datetime.now(UTC),
        error="upstream unavailable",
    )
    history = {
        "date": "2026-09-02",
        "open": "49.5",
        "high": "51.0",
        "low": "49.2",
        "close": "50.8",
        "preclose": "50.0",
        "volume": "123456",
        "amount": "6250000",
        "pctChg": "1.6",
    }
    provider = HybridMarketDataProvider(StubRealtime(quote), StubHistory(history))

    result = await provider.get_stock_quote("601318.SH")

    assert result.ok is True
    assert result.is_delayed is True
    assert result.data["name"] == "中国平安"
    assert result.data["price"] == 50.8
    assert "Baostock 最近日线" in result.data["fallback_reason"]
