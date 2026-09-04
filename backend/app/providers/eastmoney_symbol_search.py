from __future__ import annotations

from app.providers.resilient_http import ResilientHttpClient
from app.providers.symbol_resolver import classify_a_share_board, enrich_security, infer_exchange

EASTMONEY_SUGGEST_URL = "https://searchapi.eastmoney.com/api/suggest/get"
EASTMONEY_SUGGEST_TOKEN = "D43BF722C8E33BE4945601EA248D5DB"


class EastmoneySymbolSearch:
    """Search Eastmoney's security directory, including current Beijing-board codes."""

    def __init__(self, client: ResilientHttpClient | None = None) -> None:
        self.client = client or ResilientHttpClient(timeout_seconds=6, retries=1)

    async def search(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        payload = await self.client.get_json(
            EASTMONEY_SUGGEST_URL,
            params={
                "input": query.strip(),
                "type": "14",
                "token": EASTMONEY_SUGGEST_TOKEN,
                "count": limit,
            },
            headers={
                "Referer": "https://quote.eastmoney.com/",
                "User-Agent": "Mozilla/5.0 (compatible; StockPilot/0.1)",
            },
        )
        table = payload.get("QuotationCodeTable") or {}
        results: list[dict[str, str]] = []
        for item in table.get("Data") or []:
            code = str(item.get("UnifiedCode") or item.get("Code") or "").strip()
            name = str(item.get("Name") or "").strip()
            security_type = str(item.get("SecurityTypeName") or "").upper()
            exchange = infer_exchange(code)
            if not code or not name or "A" not in security_type or exchange is None:
                continue
            symbol = f"{code}.{exchange}"
            if classify_a_share_board(symbol) is None:
                continue
            security = enrich_security(symbol, name)
            if not any(existing["symbol"] == symbol for existing in results):
                results.append(security)
        results.sort(key=lambda item: (item["name"] != query.strip(), item["symbol"]))
        return results[:limit]
