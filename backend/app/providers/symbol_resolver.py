import re

KNOWN_SECURITIES = {
    "贵州茅台": ("600519.SH", "贵州茅台"),
    "茅台": ("600519.SH", "贵州茅台"),
    "平安银行": ("000001.SZ", "平安银行"),
    "宁德时代": ("300750.SZ", "宁德时代"),
    "中国平安": ("601318.SH", "中国平安"),
    "中国平安A股": ("601318.SH", "中国平安"),
    "中国平安港股": ("02318.HK", "中国平安"),
}


def classify_a_share_board(symbol: str) -> dict[str, str] | None:
    """Return exchange/board metadata for supported mainland listed stocks."""
    try:
        code, exchange = symbol.upper().split(".", maxsplit=1)
    except ValueError:
        return None
    if exchange == "SH" and code.startswith(("688", "689")):
        return {"exchange_name": "上海证券交易所", "board": "科创板"}
    if exchange == "SH" and code.startswith(("600", "601", "603", "605")):
        return {"exchange_name": "上海证券交易所", "board": "沪市主板"}
    if exchange == "SZ" and code.startswith(("300", "301")):
        return {"exchange_name": "深圳证券交易所", "board": "创业板"}
    if exchange == "SZ" and code.startswith(("000", "001", "002", "003")):
        return {"exchange_name": "深圳证券交易所", "board": "深市主板"}
    if exchange == "BJ" and code.startswith(("4", "8", "920")):
        return {"exchange_name": "北京证券交易所", "board": "北交所"}
    return None


def enrich_security(symbol: str, name: str) -> dict[str, str]:
    result = {"symbol": symbol, "name": name}
    board = classify_a_share_board(symbol)
    if board:
        result.update(board)
    return result


def infer_exchange(code: str) -> str | None:
    if len(code) == 5:
        return "HK"
    if code.startswith(("4", "8", "9")):
        return "BJ"
    if code.startswith(("5", "6", "9")):
        return "SH"
    if code.startswith(("0", "1", "2", "3")):
        return "SZ"
    return None


def resolve_symbols(query: str) -> list[dict[str, str]]:
    normalized = query.upper()
    results: list[dict[str, str]] = []

    explicit_pattern = r"(?<!\d)(\d{4,6})(?:\.(SH|SZ|BJ|HK))?(?!\d)"
    for code, exchange in re.findall(explicit_pattern, normalized):
        resolved_exchange = exchange or infer_exchange(code)
        if not resolved_exchange:
            continue
        normalized_code = code.zfill(5) if resolved_exchange == "HK" else code.zfill(6)
        symbol = f"{normalized_code}.{resolved_exchange}"
        if resolved_exchange != "HK" and classify_a_share_board(symbol) is None:
            continue
        if not any(item["symbol"] == symbol for item in results):
            results.append(enrich_security(symbol, symbol))

    for alias, (symbol, name) in sorted(KNOWN_SECURITIES.items(), key=lambda item: -len(item[0])):
        if alias in query and not any(item["symbol"] == symbol for item in results):
            results.append(enrich_security(symbol, name))
            break
    return results
