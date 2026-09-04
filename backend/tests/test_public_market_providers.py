from app.providers.eastmoney_history import EastmoneyHistoryProvider
from app.providers.eastmoney_symbol_search import EastmoneySymbolSearch
from app.providers.public_realtime import (
    PublicRealtimeMarketDataProvider,
    SinaQuoteProvider,
    TencentQuoteProvider,
)
from app.providers.stock_sentiment import _classify
from app.providers.tencent_symbol_search import TencentSymbolSearch


class StubBytesClient:
    def __init__(self, content: bytes):
        self.content = content

    async def get_bytes(self, _url, **_kwargs):
        return self.content


class SequenceBytesClient:
    def __init__(self, contents):
        self.contents = iter(contents)

    async def get_bytes(self, _url, **_kwargs):
        return next(self.contents)


class StubJsonClient:
    def __init__(self, payload):
        self.payload = payload

    async def get_json(self, _url, **_kwargs):
        return self.payload


def test_sentiment_keyword_classification():
    assert _classify("净利润增长并回购股份")[0] == "positive"
    assert _classify("公司遭到处罚，业绩下降")[0] == "negative"
    assert _classify("公司召开年度股东大会")[0] == "neutral"


def test_parse_eastmoney_kline_and_trend():
    kline = EastmoneyHistoryProvider._parse_kline(
        "2026-09-02,10.1,10.3,10.5,10.0,1234,567890,4.85,1.98,0.2,2.1"
    )
    trend = EastmoneyHistoryProvider._parse_trend(
        "2026-09-03 09:31,10.31,10.25,10.35,10.20,321,330000,10.24"
    )

    assert kline["close"] == 10.3
    assert kline["change_pct"] == 1.98
    assert trend["price"] == 10.31
    assert trend["volume"] == 321


async def test_tencent_quote_normalization():
    fields = [""] * 35
    fields[1] = "贵州茅台"
    fields[2] = "600519"
    fields[3] = "1500.00"
    fields[4] = "1490.00"
    fields[5] = "1495.00"
    fields[6] = "12345"
    fields[30] = "20260903143005"
    fields[31] = "10.00"
    fields[32] = "0.67"
    fields[33] = "1510.00"
    fields[34] = "1488.00"
    content = f'v_sh600519="{"~".join(fields)}";'.encode("gb18030")

    result = await TencentQuoteProvider(StubBytesClient(content)).get_stock_quote("600519.SH")

    assert result.ok is True
    assert result.data["name"] == "贵州茅台"
    assert result.data["price"] == 1500.0
    assert result.as_of.hour == 14


async def test_sina_quote_normalization():
    fields = [""] * 32
    fields[0] = "贵州茅台"
    fields[1] = "1495.00"
    fields[2] = "1490.00"
    fields[3] = "1500.00"
    fields[4] = "1510.00"
    fields[5] = "1488.00"
    fields[8] = "1234500"
    fields[9] = "1850000000"
    fields[30] = "2026-09-03"
    fields[31] = "14:30:05"
    content = f'var hq_str_sh600519="{",".join(fields)}";'.encode("gb18030")

    result = await SinaQuoteProvider(StubBytesClient(content)).get_stock_quote("600519.SH")

    assert result.ok is True
    assert result.data["change"] == 10.0
    assert result.data["amount"] == 1850000000.0


async def test_tencent_symbol_search_filters_to_a_shares():
    content = (
        b'v_hint="sz~002594~\\u6bd4\\u4e9a\\u8fea~byd~GP-A^'
        b'hk~01211~\\u6bd4\\u4e9a\\u8fea\\u80a1\\u4efd~bydgf~GP"'
    )

    result = await TencentSymbolSearch(StubBytesClient(content)).search("比亚迪")

    assert result == [
        {
            "symbol": "002594.SZ",
            "name": "比亚迪",
            "exchange_name": "深圳证券交易所",
            "board": "深市主板",
        }
    ]


async def test_tencent_symbol_search_resolves_temporary_new_listing_name():
    no_direct_match = b'v_hint="N";'
    stem_matches = (
        b'v_hint="sz~002340~\\u683c\\u6797\\u7f8e~glm~GP-A^'
        b'sz~301688~\\u683c\\u6797\\u751f\\u7269~glsw~GP-A"'
    )
    first_quote = [""] * 3
    first_quote[1:3] = ["格林美", "002340"]
    second_quote = [""] * 3
    second_quote[1:3] = ["C格林生物", "301688"]
    quotes = (
        f'v_sz002340="{"~".join(first_quote)}";\nv_sz301688="{"~".join(second_quote)}";'
    ).encode("gb18030")
    search = TencentSymbolSearch(SequenceBytesClient([no_direct_match, stem_matches, quotes]))

    direct = await search.search("C格林")
    result = await search.search_temporary_listing_name("C格林")

    assert direct == []
    assert result == [
        {
            "symbol": "301688.SZ",
            "name": "C格林生物",
            "exchange_name": "深圳证券交易所",
            "board": "创业板",
        }
    ]


async def test_eastmoney_symbol_search_resolves_current_beijing_board_code():
    payload = {
        "QuotationCodeTable": {
            "Data": [
                {
                    "UnifiedCode": "920992",
                    "Name": "中科美菱",
                    "SecurityTypeName": "京A",
                }
            ]
        }
    }

    result = await EastmoneySymbolSearch(StubJsonClient(payload)).search("中科美菱")

    assert result == [
        {
            "symbol": "920992.BJ",
            "name": "中科美菱",
            "exchange_name": "北京证券交易所",
            "board": "北交所",
        }
    ]


class StubSymbolSearch:
    async def search(self, query):
        assert query == "宇树科技"
        return [
            {
                "symbol": "688836.SH",
                "name": "宇树科技W",
                "exchange_name": "上海证券交易所",
                "board": "科创板",
            }
        ]


class EmptySymbolSearch:
    async def search(self, _query):
        return []


class StubDirectorySearch:
    async def search(self, query):
        assert query == "中科美菱"
        return [
            {
                "symbol": "920992.BJ",
                "name": "中科美菱",
                "exchange_name": "北京证券交易所",
                "board": "北交所",
            }
        ]


async def test_public_provider_uses_dynamic_market_wide_name_search():
    provider = PublicRealtimeMarketDataProvider(
        providers=[object()], symbol_search=StubSymbolSearch()
    )

    result = await provider.resolve_stock("宇树科技")

    assert result[0]["symbol"] == "688836.SH"
    assert result[0]["board"] == "科创板"


async def test_public_provider_falls_back_to_eastmoney_security_directory():
    provider = PublicRealtimeMarketDataProvider(
        providers=[object()],
        symbol_search=EmptySymbolSearch(),
        directory_search=StubDirectorySearch(),
    )

    result = await provider.resolve_stock("中科美菱")

    assert result[0]["symbol"] == "920992.BJ"
