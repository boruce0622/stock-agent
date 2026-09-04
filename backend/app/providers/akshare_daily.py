from __future__ import annotations

import asyncio
import threading
import time
from datetime import date
from time import monotonic
from typing import Any

MIN_REQUEST_INTERVAL_SECONDS = 1.2
_request_lock = threading.Lock()
_last_request_started = 0.0


def _vendor_symbol(symbol: str) -> str:
    code, exchange = symbol.split(".", maxsplit=1)
    prefixes = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    if exchange not in prefixes:
        raise ValueError(f"AKShare 日线不支持该市场：{exchange}")
    return f"{prefixes[exchange]}{code}"


def _value(value: Any) -> float | None:
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


def _fetch_sync(symbol: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    global _last_request_started

    import akshare as ak

    with _request_lock:
        remaining = MIN_REQUEST_INTERVAL_SECONDS - (monotonic() - _last_request_started)
        if remaining > 0:
            time.sleep(remaining)
        _last_request_started = monotonic()
        frame = ak.stock_zh_a_daily(
            symbol=_vendor_symbol(symbol),
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            adjust="qfq",
        )
    if frame is None or frame.empty:
        raise ValueError("AKShare 新浪日线未返回数据")
    return [
        {
            "time": str(row.get("date")),
            "open": _value(row.get("open")),
            "close": _value(row.get("close")),
            "high": _value(row.get("high")),
            "low": _value(row.get("low")),
            "volume": _value(row.get("volume")),
            "amount": _value(row.get("amount")),
            "turnover_pct": (
                round(float(row.get("turnover")) * 100, 4)
                if _value(row.get("turnover")) is not None
                else None
            ),
        }
        for _index, row in frame.iterrows()
    ]


class AKShareDailyProvider:
    def __init__(self, timeout_seconds: float = 25) -> None:
        self.timeout_seconds = timeout_seconds

    async def get_daily(
        self, symbol: str, *, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_sync, symbol, start_date, end_date),
            timeout=self.timeout_seconds,
        )
