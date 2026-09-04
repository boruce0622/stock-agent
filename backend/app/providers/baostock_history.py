from __future__ import annotations

import asyncio
import threading
import time
from datetime import date, datetime, timedelta
from time import monotonic
from typing import Any

MIN_REQUEST_INTERVAL_SECONDS = 1.2

_request_lock = threading.Lock()
_last_request_started = 0.0


def _baostock_symbol(symbol: str) -> str:
    code, exchange = symbol.split(".", maxsplit=1)
    prefixes = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    try:
        return f"{prefixes[exchange]}.{code}"
    except KeyError as exc:
        raise ValueError(f"Baostock 不支持该市场：{exchange}") from exc


def _fetch_history_sync(
    symbol: str,
    start_date: date,
    end_date: date,
    frequency: str,
) -> list[dict[str, Any]]:
    global _last_request_started

    import baostock as bs

    with _request_lock:
        remaining = MIN_REQUEST_INTERVAL_SECONDS - (monotonic() - _last_request_started)
        if remaining > 0:
            time.sleep(remaining)
        _last_request_started = monotonic()

        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"Baostock 登录失败：{login.error_msg}")
        try:
            result = bs.query_history_k_data_plus(
                _baostock_symbol(symbol),
                "date,code,open,high,low,close,preclose,volume,amount,pctChg",
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                frequency=frequency,
                adjustflag="3",
            )
            if result.error_code != "0":
                raise RuntimeError(f"Baostock 查询失败：{result.error_msg}")
            rows: list[list[str]] = []
            while result.next():
                rows.append(result.get_row_data())
        finally:
            bs.logout()

    if not rows:
        raise ValueError("Baostock 未返回历史行情")
    return [dict(zip(result.fields, row, strict=False)) for row in rows]


class BaoStockHistoryProvider:
    def __init__(self, timeout_seconds: float = 15) -> None:
        self.timeout_seconds = timeout_seconds

    async def get_history(
        self,
        symbol: str,
        *,
        start_date: date,
        end_date: date,
        frequency: str = "d",
    ) -> list[dict[str, Any]]:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _fetch_history_sync,
                symbol,
                start_date,
                end_date,
                frequency,
            ),
            timeout=self.timeout_seconds,
        )

    async def get_recent_daily(self, symbol: str, end_date: date | None = None) -> dict[str, Any]:
        requested_end = end_date or (datetime.now().date() - timedelta(days=1))
        rows = await self.get_history(
            symbol,
            start_date=requested_end - timedelta(days=20),
            end_date=requested_end,
        )
        return rows[-1]
