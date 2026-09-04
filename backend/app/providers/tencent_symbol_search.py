from __future__ import annotations

import json
import re

from app.providers.resilient_http import ResilientHttpClient
from app.providers.symbol_resolver import classify_a_share_board, enrich_security

TENCENT_SMARTBOX_URL = "https://smartbox.gtimg.cn/s3/"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TEMPORARY_LISTING_NAME = re.compile(r"^[NC]([\u4e00-\u9fff]{1,8})$", re.I)


class TencentSymbolSearch:
    def __init__(self, client: ResilientHttpClient | None = None) -> None:
        self.client = client or ResilientHttpClient(timeout_seconds=5, retries=1)

    async def search(self, query: str, limit: int = 10) -> list[dict[str, str]]:
        content = await self.client.get_bytes(
            TENCENT_SMARTBOX_URL,
            params={"q": query.strip(), "t": "all"},
        )
        text = content.decode("gb18030", errors="replace")
        match = re.search(r'v_hint="(.*)"', text)
        if not match:
            return []
        decoded = json.loads(f'"{match.group(1)}"')
        results: list[dict[str, str]] = []
        exchanges = {"sh": "SH", "sz": "SZ", "bj": "BJ"}
        for item in decoded.split("^"):
            fields = item.split("~")
            if len(fields) < 5 or fields[0] not in exchanges:
                continue
            symbol = f"{fields[1]}.{exchanges[fields[0]]}"
            if classify_a_share_board(symbol) is None:
                continue
            result = enrich_security(symbol, fields[2])
            if result not in results:
                results.append(result)
        results.sort(key=lambda item: (item["name"] != query.strip(), item["symbol"]))
        return results[:limit]

    async def search_temporary_listing_name(
        self, query: str, limit: int = 10
    ) -> list[dict[str, str]]:
        """Resolve temporary N/C new-listing names against current quote names."""
        term = query.strip()
        match = TEMPORARY_LISTING_NAME.fullmatch(term)
        if not match:
            return []

        candidates = await self.search(match.group(1), limit=limit)
        if not candidates:
            return []
        vendor_symbols = []
        for item in candidates:
            code, exchange = item["symbol"].split(".", maxsplit=1)
            vendor_symbols.append(f"{exchange.lower()}{code}")
        content = await self.client.get_bytes(
            f"{TENCENT_QUOTE_URL}{','.join(vendor_symbols)}"
        )
        text = content.decode("gb18030", errors="replace")
        matched: list[dict[str, str]] = []
        by_code = {item["symbol"].split(".", maxsplit=1)[0]: item for item in candidates}
        for quote_match in re.finditer(r'="(.*?)";', text):
            fields = quote_match.group(1).split("~")
            if len(fields) < 3:
                continue
            live_name, code = fields[1].strip(), fields[2].strip()
            candidate = by_code.get(code)
            if candidate and live_name.upper().startswith(term.upper()):
                matched.append(enrich_security(candidate["symbol"], live_name))
        return matched
