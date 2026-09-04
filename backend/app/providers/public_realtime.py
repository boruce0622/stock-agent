from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from app.providers.akshare_market_data import AKShareMarketDataProvider
from app.providers.base import ToolEnvelope
from app.providers.eastmoney_symbol_search import EastmoneySymbolSearch
from app.providers.resilient_http import ResilientHttpClient
from app.providers.symbol_resolver import resolve_symbols
from app.providers.tencent_symbol_search import TencentSymbolSearch

TENCENT_URL = "https://qt.gtimg.cn/q="
SINA_URL = "https://hq.sinajs.cn/"
SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn/",
    "User-Agent": "Mozilla/5.0 (compatible; StockPilot/0.1)",
}


def _vendor_symbol(symbol: str) -> str:
    code, exchange = symbol.split(".", maxsplit=1)
    prefixes = {"SH": "sh", "SZ": "sz", "BJ": "bj"}
    try:
        return f"{prefixes[exchange]}{code}"
    except KeyError as exc:
        raise ValueError(f"公网实时行情暂不支持该市场：{exchange}") from exc


def _number(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _china_time(date_text: str, time_text: str | None = None) -> datetime:
    china_standard_time = timezone(timedelta(hours=8), name="Asia/Shanghai")
    value = f"{date_text} {time_text}" if time_text else date_text
    for pattern in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=china_standard_time)
        except ValueError:
            continue
    raise ValueError(f"无法解析行情时间：{value}")


class TencentQuoteProvider:
    def __init__(self, client: ResilientHttpClient | None = None) -> None:
        self.client = client or ResilientHttpClient(timeout_seconds=5, retries=1)

    async def resolve_stock(self, query: str) -> list[dict[str, str]]:
        return resolve_symbols(query)

    async def get_stock_quote(self, symbol: str) -> ToolEnvelope:
        started = perf_counter()
        now = datetime.now(UTC)
        try:
            vendor_symbol = _vendor_symbol(symbol)
            content = await self.client.get_bytes(f"{TENCENT_URL}{vendor_symbol}")
            text = content.decode("gb18030", errors="replace")
            match = re.search(r'="(.*)"', text)
            if not match:
                raise ValueError("腾讯行情返回格式异常")
            fields = match.group(1).split("~")
            if len(fields) < 35:
                raise ValueError("腾讯行情字段不完整")
            price = _number(fields[3])
            if price is None or price <= 0:
                raise ValueError("腾讯行情最新价无效")
            as_of = _china_time(fields[30])
            return ToolEnvelope(
                ok=True,
                data={
                    "symbol": symbol,
                    "name": fields[1] or symbol,
                    "price": price,
                    "change": _number(fields[31]),
                    "change_pct": _number(fields[32]),
                    "open": _number(fields[5]),
                    "high": _number(fields[33]),
                    "low": _number(fields[34]),
                    "previous_close": _number(fields[4]),
                    "volume": _number(fields[6]),
                    "currency": "CNY",
                },
                source="腾讯财经实时行情",
                as_of=as_of,
                is_delayed=False,
                latency_ms=int((perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolEnvelope(
                ok=False,
                data={},
                source="腾讯财经实时行情",
                as_of=now,
                is_delayed=True,
                latency_ms=int((perf_counter() - started) * 1000),
                error=str(exc),
            )


class SinaQuoteProvider:
    def __init__(self, client: ResilientHttpClient | None = None) -> None:
        self.client = client or ResilientHttpClient(timeout_seconds=5, retries=1)

    async def resolve_stock(self, query: str) -> list[dict[str, str]]:
        return resolve_symbols(query)

    async def get_stock_quote(self, symbol: str) -> ToolEnvelope:
        started = perf_counter()
        now = datetime.now(UTC)
        try:
            vendor_symbol = _vendor_symbol(symbol)
            content = await self.client.get_bytes(
                f"{SINA_URL}list={vendor_symbol}", headers=SINA_HEADERS
            )
            text = content.decode("gb18030", errors="replace")
            match = re.search(r'="(.*)"', text)
            if not match:
                raise ValueError("新浪行情返回格式异常")
            fields = match.group(1).split(",")
            if len(fields) < 32:
                raise ValueError("新浪行情字段不完整")
            price = _number(fields[3])
            previous_close = _number(fields[2])
            if price is None or price <= 0:
                raise ValueError("新浪行情最新价无效")
            change = price - previous_close if previous_close else None
            as_of = _china_time(fields[30], fields[31])
            return ToolEnvelope(
                ok=True,
                data={
                    "symbol": symbol,
                    "name": fields[0] or symbol,
                    "price": price,
                    "change": change,
                    "change_pct": change / previous_close * 100 if previous_close else None,
                    "open": _number(fields[1]),
                    "high": _number(fields[4]),
                    "low": _number(fields[5]),
                    "previous_close": previous_close,
                    "volume": _number(fields[8]),
                    "amount": _number(fields[9]),
                    "currency": "CNY",
                },
                source="新浪财经实时行情",
                as_of=as_of,
                is_delayed=False,
                latency_ms=int((perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolEnvelope(
                ok=False,
                data={},
                source="新浪财经实时行情",
                as_of=now,
                is_delayed=True,
                latency_ms=int((perf_counter() - started) * 1000),
                error=str(exc),
            )


class PublicRealtimeMarketDataProvider:
    def __init__(
        self,
        providers: list[Any] | None = None,
        symbol_search: TencentSymbolSearch | None = None,
        directory_search: EastmoneySymbolSearch | None = None,
    ) -> None:
        self.providers = providers or [
            TencentQuoteProvider(),
            SinaQuoteProvider(),
            AKShareMarketDataProvider(),
        ]
        self.symbol_search = symbol_search or TencentSymbolSearch()
        self.directory_search = directory_search or EastmoneySymbolSearch()

    async def resolve_stock(self, query: str) -> list[dict[str, str]]:
        local_matches = resolve_symbols(query)
        if local_matches:
            return local_matches
        search_errors: list[str] = []
        try:
            matches = await self.symbol_search.search(query)
            if matches:
                return matches
            resolve_temporary = getattr(self.symbol_search, "search_temporary_listing_name", None)
            matches = await resolve_temporary(query) if resolve_temporary else []
            if matches:
                return matches
        except Exception as exc:
            search_errors.append(f"腾讯证券搜索: {exc}")
        try:
            return await self.directory_search.search(query)
        except Exception as exc:
            search_errors.append(f"东方财富证券目录: {exc}")
            raise RuntimeError("; ".join(search_errors)) from exc

    async def get_stock_quote(self, symbol: str) -> ToolEnvelope:
        errors: list[str] = []
        last: ToolEnvelope | None = None
        for provider in self.providers:
            quote = await provider.get_stock_quote(symbol)
            last = quote
            if quote.ok:
                if errors:
                    quote.data["fallback"] = "实时主源不可用，已自动切换备用源"
                return quote
            errors.append(f"{quote.source}: {quote.error}")
        if last is None:
            raise RuntimeError("未配置实时行情供应商")
        last.error = "; ".join(errors)
        return last
