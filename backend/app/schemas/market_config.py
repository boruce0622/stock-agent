from typing import Literal

from pydantic import BaseModel


class MarketConfigPayload(BaseModel):
    provider: Literal["hybrid"] = "hybrid"
    enabled: bool = True


class MarketConfigOut(BaseModel):
    configured: bool
    provider: str = "hybrid"
    provider_name: str = "多源公网行情"
    enabled: bool = False
    source: str = "akshare-baostock"


class MarketConnectionTestOut(BaseModel):
    ok: bool
    provider: str
    latency_ms: int
    sample_symbol: str
    data_as_of: str
    message: str
