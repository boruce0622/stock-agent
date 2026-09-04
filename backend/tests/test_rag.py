import pytest

from app.agent.graph import StockAgentGraph
from app.llm.gateway import LangChainLLMGateway
from app.providers.fake_market_data import FakeMarketDataProvider
from app.rag.knowledge_retriever import LocalKnowledgeRetriever


class RAGPlanningLLM:
    model_label = "rag-test-model"

    def __init__(self):
        self.evidence = None

    async def plan(self, _query, _candidates):
        return {
            "intent": "explanation",
            "stock_query": None,
            "tools": ["knowledge"],
            "focus": ["解释口径和局限"],
        }

    async def generate(self, state):
        self.evidence = state["evidence"]
        return "市盈率需要区分具体口径，亏损企业可能不适用。[知识库1]"


@pytest.mark.asyncio
async def test_retriever_returns_relevant_citations_and_rejects_no_match():
    retriever = LocalKnowledgeRetriever()

    matched = await retriever.search("市盈率怎么理解")
    unmatched = await retriever.search("量子香蕉天气")

    assert matched["ok"] is True
    assert matched["hits"][0]["section"] == "市盈率 PE"
    assert matched["hits"][0]["citation"] == "[知识库1]"
    assert unmatched["ok"] is False
    assert unmatched["hits"] == []


@pytest.mark.asyncio
async def test_retriever_handles_multi_topic_stock_research_query():
    result = await LocalKnowledgeRetriever().search(
        "分析301489创业板股票的K线、舆情和风险"
    )

    sections = {hit["section"] for hit in result["hits"]}
    assert {"市场和代码识别", "K线分析边界", "新闻舆情边界"}.issubset(sections)


@pytest.mark.asyncio
async def test_agent_passes_rag_hits_to_model_without_internal_diagnostics():
    llm = RAGPlanningLLM()
    graph = StockAgentGraph(FakeMarketDataProvider(), llm=llm).graph

    result = await graph.ainvoke(
        {"query": "市盈率怎么理解？", "conversation_id": "test"}
    )

    assert llm.evidence["knowledge"]["ok"] is True
    assert "[知识库1]" in result["answer"]
    assert "知识库命中" not in result["answer"]
    assert "RAG 引用校验" not in result["answer"]


def test_llm_evidence_compaction_derives_open_direction():
    compact = LangChainLLMGateway._compact_evidence(
        {
            "quote": {
                "ok": True,
                "source": "test",
                "data": {
                    "open": 120.12,
                    "previous_close": 117.0,
                    "price": 140.4,
                    "high": 140.4,
                },
            }
        }
    )

    assert compact["quote"]["citation"] == "[行情]"
    assert compact["quote"]["data"]["open_direction"] == "高开"
    assert compact["quote"]["data"]["open_gap_pct"] == 2.67
    assert compact["quote"]["data"]["closed_at_high"] is True
