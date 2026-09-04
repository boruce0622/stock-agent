from __future__ import annotations

from typing import Any, Literal

from app.providers.resilient_http import ResilientHttpClient

EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_TRENDS_URL = "https://push2his.eastmoney.com/api/qt/stock/trends2/get"
FIELDS1 = "f1,f2,f3,f4,f5,f6"
TREND_FIELDS1 = "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
KLINE_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
TREND_FIELDS2 = "f51,f52,f53,f54,f55,f56,f57,f58"
KLINE_PERIODS = {
    "daily": 101,
    "weekly": 102,
    "monthly": 103,
    "1": 1,
    "5": 5,
    "15": 15,
    "30": 30,
    "60": 60,
}
ADJUSTMENTS = {"none": 0, "forward": 1, "backward": 2}


def _secid(symbol: str) -> str:
    code, exchange = symbol.split(".", maxsplit=1)
    markets = {"SH": "1", "SZ": "0", "BJ": "0"}
    try:
        return f"{markets[exchange]}.{code}"
    except KeyError as exc:
        raise ValueError(f"东方财富历史行情暂不支持该市场：{exchange}") from exc


def _number(value: str) -> float | None:
    if value in ("", "-"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


class EastmoneyHistoryProvider:
    def __init__(self, client: ResilientHttpClient | None = None) -> None:
        self.client = client or ResilientHttpClient(timeout_seconds=6, retries=1)

    async def get_klines(
        self,
        symbol: str,
        *,
        period: Literal["daily", "weekly", "monthly", "1", "5", "15", "30", "60"] = "daily",
        adjust: Literal["none", "forward", "backward"] = "none",
        begin: str = "0",
        end: str = "20500101",
        limit: int = 200,
    ) -> dict[str, Any]:
        payload = await self.client.get_json(
            EASTMONEY_KLINE_URL,
            params={
                "secid": _secid(symbol),
                "fields1": FIELDS1,
                "fields2": KLINE_FIELDS2,
                "klt": KLINE_PERIODS[period],
                "fqt": ADJUSTMENTS[adjust],
                "beg": begin,
                "end": end,
                "lmt": limit,
            },
        )
        data = payload.get("data")
        if not data or not data.get("klines"):
            raise ValueError("东方财富未返回 K 线数据")
        records = [self._parse_kline(item) for item in data["klines"][-limit:]]
        return {
            "symbol": symbol,
            "name": data.get("name") or symbol,
            "period": period,
            "adjust": adjust,
            "source": "东方财富 push2his",
            "records": records,
        }

    async def get_intraday(self, symbol: str, *, days: int = 1) -> dict[str, Any]:
        payload = await self.client.get_json(
            EASTMONEY_TRENDS_URL,
            params={
                "secid": _secid(symbol),
                "fields1": TREND_FIELDS1,
                "fields2": TREND_FIELDS2,
                "ndays": days,
                "iscr": 0,
            },
        )
        data = payload.get("data")
        if not data or not data.get("trends"):
            raise ValueError("东方财富未返回分时数据")
        records = [self._parse_trend(item) for item in data["trends"]]
        return {
            "symbol": symbol,
            "name": data.get("name") or symbol,
            "previous_close": data.get("preClose"),
            "days": days,
            "source": "东方财富 push2his",
            "records": records,
        }

    @staticmethod
    def _parse_kline(item: str) -> dict[str, Any]:
        fields = item.split(",")
        if len(fields) < 11:
            raise ValueError("东方财富 K 线字段不完整")
        return {
            "time": fields[0],
            "open": _number(fields[1]),
            "close": _number(fields[2]),
            "high": _number(fields[3]),
            "low": _number(fields[4]),
            "volume": _number(fields[5]),
            "amount": _number(fields[6]),
            "amplitude_pct": _number(fields[7]),
            "change_pct": _number(fields[8]),
            "change": _number(fields[9]),
            "turnover_pct": _number(fields[10]),
        }

    @staticmethod
    def _parse_trend(item: str) -> dict[str, Any]:
        fields = item.split(",")
        if len(fields) < 8:
            raise ValueError("东方财富分时字段不完整")
        price = _number(fields[1])
        average = _number(fields[2])
        return {
            "time": fields[0],
            "price": price if price not in (None, 0) else average,
            "average_price": average,
            "high": _number(fields[3]),
            "low": _number(fields[4]),
            "volume": _number(fields[5]),
            "amount": _number(fields[6]),
        }
