from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.providers.base import MarketDataProvider


class QuoteInput(BaseModel):
    symbol: str = Field(description="规范股票代码，例如 600519.SH")


def build_quote_tool(provider: MarketDataProvider) -> StructuredTool:
    async def get_stock_quote(symbol: str) -> dict:
        result = await provider.get_stock_quote(symbol)
        return result.model_dump(mode="json")

    return StructuredTool.from_function(
        coroutine=get_stock_quote,
        name="get_stock_quote",
        description="查询指定股票的最新价格、涨跌幅、OHLC、成交量、来源和数据时间。",
        args_schema=QuoteInput,
    )
