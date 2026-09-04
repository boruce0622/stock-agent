from __future__ import annotations

import asyncio
import threading
import time
from time import monotonic
from typing import Any

MIN_REQUEST_INTERVAL_SECONDS = 1.2

_request_lock = threading.Lock()
_last_request_started = 0.0


def _fetch_minute_sync(symbol: str, period: str) -> list[dict[str, Any]]:
    global _last_request_started

    import akshare as ak

    code, exchange = symbol.split(".", maxsplit=1)
    prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(exchange)
    if not prefix:
        raise ValueError(f"AKShare 分钟线不支持该市场：{exchange}")
    with _request_lock:
        remaining = MIN_REQUEST_INTERVAL_SECONDS - (monotonic() - _last_request_started)
        if remaining > 0:
            time.sleep(remaining)
        _last_request_started = monotonic()
        frame = ak.stock_zh_a_minute(symbol=f"{prefix}{code}", period=period, adjust="")
    if frame is None or frame.empty:
        raise ValueError("AKShare 未返回分钟线")
    return [
        {
            "time": str(row["day"]),
            "open": float(row["open"]),
            "close": float(row["close"]),
            "price": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
            "amount": float(row["amount"]),
        }
        for _, row in frame.iterrows()
    ]


class AKShareMinuteProvider:
    def __init__(self, timeout_seconds: float = 15) -> None:
        self.timeout_seconds = timeout_seconds

    async def get_minutes(self, symbol: str, period: str = "1") -> list[dict[str, Any]]:
        return await asyncio.wait_for(
            asyncio.to_thread(_fetch_minute_sync, symbol, period),
            timeout=self.timeout_seconds,
        )
