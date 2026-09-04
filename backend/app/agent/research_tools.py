from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.providers.akshare_daily import AKShareDailyProvider
from app.providers.akshare_minute import AKShareMinuteProvider
from app.providers.baostock_history import BaoStockHistoryProvider
from app.providers.base import MarketDataProvider
from app.providers.eastmoney_history import EastmoneyHistoryProvider
from app.providers.stock_sentiment import StockSentimentProvider
from app.rag.knowledge_retriever import LocalKnowledgeRetriever


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


class StockResearchTools:
    """Executes factual tools selected by the model and returns compact evidence."""

    def __init__(self, market: MarketDataProvider) -> None:
        self.market = market
        self.history = EastmoneyHistoryProvider()
        self.baostock = BaoStockHistoryProvider()
        self.minute = AKShareMinuteProvider()
        self.akshare_daily = AKShareDailyProvider()
        self.sentiment = StockSentimentProvider()
        self.knowledge = LocalKnowledgeRetriever()

    async def execute(
        self, name: str, symbol: str | None, *, query: str | None = None
    ) -> dict[str, Any]:
        if name == "knowledge":
            return await self.knowledge.search(query or "")
        if not symbol:
            raise ValueError(f"工具 {name} 需要先识别股票")
        if name == "quote":
            result = await self.market.get_stock_quote(symbol)
            return result.model_dump(mode="json")
        if name == "kline":
            return await self._kline(symbol)
        if name == "intraday":
            return await self._intraday(symbol)
        if name == "sentiment":
            return await self.sentiment.get_sentiment(symbol, limit=10)
        raise ValueError(f"未知研究工具：{name}")

    async def _kline(self, symbol: str) -> dict[str, Any]:
        try:
            result = await self.history.get_klines(
                symbol, period="daily", adjust="forward", limit=90
            )
        except Exception as primary_error:
            end = date.today()
            start = end - timedelta(days=200)
            try:
                rows = await self.baostock.get_history(
                    symbol,
                    start_date=start,
                    end_date=end,
                    frequency="d",
                )
                records = [
                    {
                        "time": row.get("date"),
                        "open": _number(row.get("open")),
                        "close": _number(row.get("close")),
                        "high": _number(row.get("high")),
                        "low": _number(row.get("low")),
                        "volume": _number(row.get("volume")),
                        "amount": _number(row.get("amount")),
                        "change_pct": _number(row.get("pctChg")),
                    }
                    for row in rows[-90:]
                ]
                source = "Baostock（push2his 不可用时降级）"
                fallback_reason = str(primary_error)
            except Exception as baostock_error:
                records = (
                    await self.akshare_daily.get_daily(
                        symbol, start_date=start, end_date=end
                    )
                )[-90:]
                source = "AKShare 新浪日线（push2his/Baostock 不可用时降级）"
                fallback_reason = f"push2his: {primary_error}; Baostock: {baostock_error}"
            result = {
                "symbol": symbol,
                "period": "daily",
                "source": source,
                "fallback_reason": fallback_reason,
                "records": records,
            }
        result["summary"] = self._summarize_kline(result.get("records", []))
        result["records"] = result.get("records", [])[-20:]
        return result

    async def _intraday(self, symbol: str) -> dict[str, Any]:
        try:
            result = await self.history.get_intraday(symbol, days=1)
        except Exception as primary_error:
            records = await self.minute.get_minutes(symbol, "1")
            result = {
                "symbol": symbol,
                "source": "AKShare 新浪分钟线（push2his 不可用时降级）",
                "fallback_reason": str(primary_error),
                "records": records,
            }
        records = result.get("records", [])
        result["summary"] = {
            "points": len(records),
            "first": records[0] if records else None,
            "last": records[-1] if records else None,
        }
        result["records"] = records[-30:]
        return result

    @staticmethod
    def _summarize_kline(records: list[dict[str, Any]]) -> dict[str, Any]:
        valid = [row for row in records if _number(row.get("close")) is not None]
        if not valid:
            return {"bars": 0}
        closes = [float(row["close"]) for row in valid]
        latest = closes[-1]

        def change(window: int) -> float | None:
            if len(closes) <= window or closes[-window - 1] == 0:
                return None
            return round((latest / closes[-window - 1] - 1) * 100, 2)

        return {
            "bars": len(valid),
            "from": valid[0].get("time"),
            "to": valid[-1].get("time"),
            "latest_close": latest,
            "change_5d_pct": change(5),
            "change_20d_pct": change(20),
            "change_60d_pct": change(60),
            "range_20d_high": max(closes[-20:]),
            "range_20d_low": min(closes[-20:]),
            "average_20d": round(sum(closes[-20:]) / min(len(closes), 20), 3),
        }
