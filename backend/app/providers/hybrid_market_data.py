from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone
from time import perf_counter
from typing import Any

from app.providers.baostock_history import BaoStockHistoryProvider
from app.providers.base import ToolEnvelope
from app.providers.public_realtime import PublicRealtimeMarketDataProvider
from app.providers.symbol_resolver import KNOWN_SECURITIES

SOURCE_NAME = "AKShare 实时行情 + Baostock 历史校验"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class HybridMarketDataProvider:
    def __init__(
        self,
        realtime: PublicRealtimeMarketDataProvider | None = None,
        history: BaoStockHistoryProvider | None = None,
    ) -> None:
        self.realtime = realtime or PublicRealtimeMarketDataProvider()
        self.history = history or BaoStockHistoryProvider()

    async def resolve_stock(self, query: str) -> list[dict[str, str]]:
        return await self.realtime.resolve_stock(query)

    async def get_stock_quote(self, symbol: str) -> ToolEnvelope:
        started = perf_counter()
        realtime_quote = await self.realtime.get_stock_quote(symbol)
        try:
            history_row = await self.history.get_recent_daily(symbol)
        except Exception as exc:
            if realtime_quote.ok:
                realtime_quote.data["cross_check"] = {
                    "status": "unavailable",
                    "source": "Baostock",
                    "detail": str(exc),
                }
                return realtime_quote
            realtime_quote.error = f"AKShare: {realtime_quote.error}; Baostock: {exc}"
            return realtime_quote

        if realtime_quote.ok:
            self._attach_cross_check(realtime_quote, history_row)
            realtime_quote.source = SOURCE_NAME
            realtime_quote.latency_ms = int((perf_counter() - started) * 1000)
            return realtime_quote
        try:
            return self._historical_fallback(symbol, history_row, started, realtime_quote.error)
        except (TypeError, ValueError, KeyError) as exc:
            realtime_quote.error = f"AKShare: {realtime_quote.error}; Baostock: {exc}"
            return realtime_quote

    @staticmethod
    def _attach_cross_check(quote: ToolEnvelope, history_row: dict[str, Any]) -> None:
        baostock_close = _number(history_row.get("close"))
        realtime_previous_close = _number(quote.data.get("previous_close"))
        matches = (
            baostock_close is not None
            and realtime_previous_close is not None
            and math.isclose(baostock_close, realtime_previous_close, rel_tol=0.002, abs_tol=0.02)
        )
        quote.data["cross_check"] = {
            "status": "matched" if matches else "mismatch",
            "source": "Baostock",
            "date": history_row.get("date"),
            "close": baostock_close,
        }

    @staticmethod
    def _historical_fallback(
        symbol: str,
        row: dict[str, Any],
        started: float,
        realtime_error: str | None,
    ) -> ToolEnvelope:
        china_standard_time = timezone(timedelta(hours=8), name="Asia/Shanghai")
        trade_date = datetime.fromisoformat(str(row["date"])).date()
        as_of = datetime.combine(trade_date, time(15), tzinfo=china_standard_time)
        close = _number(row.get("close"))
        if close is None or close <= 0:
            raise ValueError("Baostock 最近收盘价无效")
        previous_close = _number(row.get("preclose"))
        change = close - previous_close if previous_close else None
        change_pct = _number(row.get("pctChg"))
        names = {stock_symbol: name for stock_symbol, name in KNOWN_SECURITIES.values()}
        return ToolEnvelope(
            ok=True,
            data={
                "symbol": symbol,
                "name": names.get(symbol, symbol),
                "price": close,
                "change": change,
                "change_pct": change_pct,
                "open": _number(row.get("open")),
                "high": _number(row.get("high")),
                "low": _number(row.get("low")),
                "previous_close": previous_close,
                "volume": _number(row.get("volume")),
                "amount": _number(row.get("amount")),
                "currency": "CNY",
                "fallback_reason": (
                    "AKShare 实时行情暂不可用，已自动使用 Baostock 最近日线"
                    if realtime_error
                    else None
                ),
            },
            source="Baostock 最近交易日日线（AKShare 不可用时降级）",
            as_of=as_of,
            is_delayed=True,
            latency_ms=int((perf_counter() - started) * 1000),
        )
