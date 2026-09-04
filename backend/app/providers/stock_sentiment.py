from __future__ import annotations

import asyncio
import threading
import time
from time import monotonic
from typing import Any

MIN_REQUEST_INTERVAL_SECONDS = 1.2
POSITIVE_WORDS = ("增长", "上涨", "增持", "突破", "盈利", "创新高", "超预期", "回购", "改善")
NEGATIVE_WORDS = ("下降", "下跌", "减持", "亏损", "处罚", "风险", "违约", "不及预期", "调查")

_request_lock = threading.Lock()
_last_request_started = 0.0


def _classify(text: str) -> tuple[str, int]:
    score = sum(word in text for word in POSITIVE_WORDS) - sum(
        word in text for word in NEGATIVE_WORDS
    )
    if score > 0:
        return "positive", score
    if score < 0:
        return "negative", score
    return "neutral", 0


def _fetch_news_sync(code: str, limit: int) -> list[dict[str, Any]]:
    global _last_request_started

    import akshare as ak

    with _request_lock:
        remaining = MIN_REQUEST_INTERVAL_SECONDS - (monotonic() - _last_request_started)
        if remaining > 0:
            time.sleep(remaining)
        _last_request_started = monotonic()
        frame = ak.stock_news_em(symbol=code)
    if frame is None or frame.empty:
        raise ValueError("AKShare 未返回个股新闻")

    news: list[dict[str, Any]] = []
    for _, row in frame.head(limit).iterrows():
        title = str(row.get("新闻标题") or "")
        summary = str(row.get("新闻内容") or "")
        sentiment, score = _classify(f"{title} {summary}")
        news.append(
            {
                "title": title,
                "summary": summary[:240],
                "published_at": str(row.get("发布时间") or ""),
                "source": str(row.get("文章来源") or "公开网络"),
                "url": str(row.get("新闻链接") or ""),
                "sentiment": sentiment,
                "score": score,
            }
        )
    return news


class StockSentimentProvider:
    def __init__(self, timeout_seconds: float = 15) -> None:
        self.timeout_seconds = timeout_seconds

    async def get_sentiment(self, symbol: str, limit: int = 12) -> dict[str, Any]:
        code = symbol.split(".", maxsplit=1)[0]
        items = await asyncio.wait_for(
            asyncio.to_thread(_fetch_news_sync, code, limit),
            timeout=self.timeout_seconds,
        )
        counts = {
            label: sum(item["sentiment"] == label for item in items)
            for label in ("positive", "neutral", "negative")
        }
        total_score = sum(item["score"] for item in items)
        overall = "positive" if total_score > 0 else "negative" if total_score < 0 else "neutral"
        return {
            "symbol": symbol,
            "overall": overall,
            "counts": counts,
            "items": items,
            "source": "AKShare 个股新闻（东方财富公开资讯）",
            "method": "关键词规则统计，仅表示新闻文本倾向，不代表投资评级",
        }
