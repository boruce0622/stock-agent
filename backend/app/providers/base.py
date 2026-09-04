from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel


class ToolEnvelope(BaseModel):
    ok: bool
    data: dict[str, Any]
    source: str
    as_of: datetime
    is_delayed: bool = False
    latency_ms: int = 0
    error: str | None = None


class MarketDataProvider(Protocol):
    async def resolve_stock(self, query: str) -> list[dict[str, str]]: ...

    async def get_stock_quote(self, symbol: str) -> ToolEnvelope: ...
