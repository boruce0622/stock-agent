from __future__ import annotations

import asyncio
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from app.providers.base import ToolEnvelope
from app.providers.symbol_resolver import KNOWN_SECURITIES, resolve_symbols

MIN_REQUEST_INTERVAL_SECONDS = 1.2
SOURCE_NAME = "AKShare（东方财富公开行情）"

_request_lock = threading.Lock()
_last_request_started = 0.0


def _number(value: Any) -> float | None:
    if value in (None, "", "--", "-"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fetch_quote_sync(code: str) -> dict[str, Any]:
    """Call AKShare off the event loop and rate-limit all provider instances."""
    global _last_request_started

    import akshare as ak

    with _request_lock:
        remaining = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_started)
        if remaining > 0:
            time.sleep(remaining)
        _last_request_started = time.monotonic()
        frame = ak.stock_bid_ask_em(symbol=code)

    if frame is None or frame.empty:
        raise ValueError("AKShare 返回空行情")
    if not {"item", "value"}.issubset(frame.columns):
        raise ValueError("AKShare 行情字段格式异常")
    return dict(zip(frame["item"], frame["value"], strict=False))


class AKShareMarketDataProvider:
    def __init__(self, timeout_seconds: float = 15) -> None:
        self.timeout_seconds = timeout_seconds

    async def resolve_stock(self, query: str) -> list[dict[str, str]]:
        return resolve_symbols(query)

    async def get_stock_quote(self, symbol: str) -> ToolEnvelope:
        started = perf_counter()
        china_standard_time = timezone(timedelta(hours=8), name="Asia/Shanghai")
        fetched_at = datetime.now(china_standard_time)
        try:
            if symbol.endswith(".HK"):
                raise ValueError("当前 AKShare 行情源仅支持沪深京 A 股")
            code = symbol.split(".", maxsplit=1)[0]
            values = await asyncio.wait_for(
                asyncio.to_thread(_fetch_quote_sync, code),
                timeout=self.timeout_seconds,
            )
            fetched_at = datetime.now(china_standard_time)
            data = self._normalize_quote(values, symbol)
            return ToolEnvelope(
                ok=True,
                data=data,
                source=SOURCE_NAME,
                as_of=fetched_at,
                # stock_bid_ask_em does not expose an exchange timestamp.
                is_delayed=True,
                latency_ms=int((perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolEnvelope(
                ok=False,
                data={},
                source=SOURCE_NAME,
                as_of=fetched_at,
                is_delayed=True,
                latency_ms=int((perf_counter() - started) * 1000),
                error=str(exc),
            )

    @staticmethod
    def _normalize_quote(values: dict[str, Any], symbol: str) -> dict[str, Any]:
        latest = _number(values.get("最新"))
        if latest is None or latest <= 0:
            raise ValueError("AKShare 最新价无效")

        high = _number(values.get("最高"))
        low = _number(values.get("最低"))
        if high is not None and low is not None and low > high:
            raise ValueError("AKShare 行情高低价关系异常")

        previous_close = _number(values.get("昨收"))
        change = _number(values.get("涨跌"))
        change_pct = _number(values.get("涨幅"))
        if change is None and previous_close is not None:
            change = latest - previous_close
        if change_pct is None and previous_close and change is not None:
            change_pct = change / previous_close * 100

        names = {stock_symbol: name for stock_symbol, name in KNOWN_SECURITIES.values()}
        return {
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "price": latest,
            "change": change,
            "change_pct": change_pct,
            "open": _number(values.get("今开")),
            "high": high,
            "low": low,
            "previous_close": previous_close,
            "volume": _number(values.get("总手")),
            "amount": _number(values.get("金额")),
            "currency": "CNY",
        }
