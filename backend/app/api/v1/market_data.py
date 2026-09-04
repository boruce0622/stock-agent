from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.providers.akshare_minute import AKShareMinuteProvider
from app.providers.baostock_history import BaoStockHistoryProvider
from app.providers.eastmoney_history import EastmoneyHistoryProvider
from app.providers.public_realtime import PublicRealtimeMarketDataProvider
from app.providers.stock_sentiment import StockSentimentProvider
from app.providers.symbol_resolver import resolve_symbols

router = APIRouter(prefix="/api/v1/market-data", tags=["Market data"])


@router.get("/resolve")
async def resolve_stock(q: str = Query(min_length=1, max_length=80)):
    try:
        matches = await PublicRealtimeMarketDataProvider().resolve_stock(q)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not matches:
        raise HTTPException(status_code=404, detail="未找到匹配的 A 股")
    return {"query": q, "matches": matches}


def _normalize_symbol(value: str) -> str:
    matches = resolve_symbols(value)
    if len(matches) != 1:
        raise HTTPException(status_code=422, detail="请提供唯一的沪深京股票代码")
    return matches[0]["symbol"]


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


async def _baostock_kline_fallback(
    symbol: str,
    period: str,
    begin: str,
    end: str,
    limit: int,
):
    if period not in {"daily", "weekly", "monthly"}:
        records = await AKShareMinuteProvider().get_minutes(symbol, period)
        return {
            "symbol": symbol,
            "name": symbol,
            "period": period,
            "adjust": "none",
            "source": "AKShare 新浪分钟线（push2his 不可用时降级）",
            "records": records[-limit:],
        }
    end_date = (
        date.today()
        if end == "20500101"
        else date.fromisoformat(f"{end[:4]}-{end[4:6]}-{end[6:]}")
    )
    start_date = (
        end_date - timedelta(days=max(limit * 2, 60))
        if begin == "0"
        else date.fromisoformat(f"{begin[:4]}-{begin[4:6]}-{begin[6:]}")
    )
    frequency = {"daily": "d", "weekly": "w", "monthly": "m"}[period]
    rows = await BaoStockHistoryProvider().get_history(
        symbol,
        start_date=start_date,
        end_date=end_date,
        frequency=frequency,
    )
    records = [
        {
            "time": row["date"],
            "open": _number(row.get("open")),
            "close": _number(row.get("close")),
            "high": _number(row.get("high")),
            "low": _number(row.get("low")),
            "volume": _number(row.get("volume")),
            "amount": _number(row.get("amount")),
            "change_pct": _number(row.get("pctChg")),
        }
        for row in rows[-limit:]
    ]
    return {
        "symbol": symbol,
        "name": symbol,
        "period": period,
        "adjust": "none",
        "source": "Baostock（东方财富 push2his 不可用时降级）",
        "records": records,
    }


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    quote = await PublicRealtimeMarketDataProvider().get_stock_quote(_normalize_symbol(symbol))
    if not quote.ok:
        raise HTTPException(status_code=502, detail=quote.error or "实时行情暂不可用")
    return quote


@router.get("/kline/{symbol}")
async def get_kline(
    symbol: str,
    period: Literal["daily", "weekly", "monthly", "1", "5", "15", "30", "60"] = "daily",
    adjust: Literal["none", "forward", "backward"] = "none",
    begin: str = Query(default="0", pattern=r"^(0|\d{8})$"),
    end: str = Query(default="20500101", pattern=r"^\d{8}$"),
    limit: int = Query(default=200, ge=1, le=1000),
):
    try:
        return await EastmoneyHistoryProvider().get_klines(
            _normalize_symbol(symbol),
            period=period,
            adjust=adjust,
            begin=begin,
            end=end,
            limit=limit,
        )
    except Exception as primary_error:
        try:
            return await _baostock_kline_fallback(
                _normalize_symbol(symbol), period, begin, end, limit
            )
        except Exception as fallback_error:
            raise HTTPException(
                status_code=502,
                detail=f"push2his: {primary_error}; Baostock: {fallback_error}",
            ) from fallback_error


@router.get("/intraday/{symbol}")
async def get_intraday(symbol: str, days: int = Query(default=1, ge=1, le=5)):
    try:
        return await EastmoneyHistoryProvider().get_intraday(_normalize_symbol(symbol), days=days)
    except Exception as primary_error:
        try:
            normalized = _normalize_symbol(symbol)
            records = await AKShareMinuteProvider().get_minutes(normalized, "1")
            available_dates = sorted({item["time"][:10] for item in records})[-days:]
            return {
                "symbol": normalized,
                "name": normalized,
                "days": days,
                "source": "AKShare 新浪分钟线（push2his 不可用时降级）",
                "records": [item for item in records if item["time"][:10] in available_dates],
            }
        except Exception as fallback_error:
            raise HTTPException(
                status_code=502,
                detail=f"push2his: {primary_error}; AKShare: {fallback_error}",
            ) from fallback_error


@router.get("/sentiment/{symbol}")
async def get_sentiment(symbol: str, limit: int = Query(default=12, ge=1, le=30)):
    try:
        return await StockSentimentProvider().get_sentiment(
            _normalize_symbol(symbol), limit=limit
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
