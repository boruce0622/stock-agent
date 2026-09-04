import asyncio
import re
from datetime import datetime, timedelta, timezone

from app.providers.base import ToolEnvelope


class FakeMarketDataProvider:
    """Deterministic offline provider for development and tests."""

    stocks = {
        "600519.SH": {"name": "贵州茅台", "price": 1488.88, "change": 12.36, "change_pct": 0.84},
        "000001.SZ": {"name": "平安银行", "price": 11.42, "change": -0.08, "change_pct": -0.70},
        "300750.SZ": {"name": "宁德时代", "price": 326.50, "change": 4.20, "change_pct": 1.30},
    }

    async def resolve_stock(self, query: str) -> list[dict[str, str]]:
        compact = query.upper().replace(" ", "")
        matches = []
        for symbol, data in self.stocks.items():
            plain_code = symbol.split(".")[0]
            code_matches = re.search(rf"\b{plain_code}\b", compact)
            if data["name"] in query or symbol in compact or code_matches:
                matches.append({"symbol": symbol, "name": str(data["name"])})
        return matches

    async def get_stock_quote(self, symbol: str) -> ToolEnvelope:
        await asyncio.sleep(0.08)
        china_standard_time = timezone(timedelta(hours=8), name="Asia/Shanghai")
        now = datetime.now(china_standard_time)
        stock = self.stocks.get(symbol)
        if stock is None:
            return ToolEnvelope(
                ok=False,
                data={},
                source="fake-market-data",
                as_of=now,
                is_delayed=True,
                latency_ms=80,
                error="SYMBOL_NOT_FOUND",
            )
        price = float(stock["price"])
        return ToolEnvelope(
            ok=True,
            data={
                "symbol": symbol,
                **stock,
                "open": round(price - float(stock["change"]) / 2, 2),
                "high": round(price * 1.012, 2),
                "low": round(price * 0.991, 2),
                "volume": 1_234_500,
                "currency": "CNY",
            },
            source="fake-market-data",
            as_of=now,
            is_delayed=True,
            latency_ms=80,
        )
