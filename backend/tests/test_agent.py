import pytest

from app.agent.graph import StockAgentGraph
from app.providers.fake_market_data import FakeMarketDataProvider


class StubLLM:
    async def generate(self, state):
        return f"真实模型回答：{state['query']} [知识库1]"


class StubLLMWithRiskNotice:
    async def generate(self, _state):
        return "暂时没有行情数据。以上内容不构成投资建议。"


class FailingLLM:
    async def generate(self, _state):
        raise RuntimeError("model unavailable")


class PlanningLLM:
    model_label = "test-planner-model"

    def __init__(self):
        self.received_evidence = None

    async def plan(self, _query, _candidates):
        return {
            "intent": "stock_research",
            "stock_query": "贵州茅台",
            "tools": ["quote", "kline", "sentiment"],
            "focus": ["趋势", "新闻驱动"],
            "reason": "需要综合价格、趋势和新闻",
        }

    async def generate(self, state):
        self.received_evidence = state["evidence"]
        return "AI 已综合趋势与新闻证据。[行情][K线][舆情]"


class HistoryAwareLLM:
    model_label = "history-aware-model"

    def __init__(self):
        self.received_history = None

    async def plan(self, _query, _candidates, conversation_history):
        self.received_history = conversation_history
        return {
            "intent": "greeting",
            "stock_query": None,
            "tools": [],
            "focus": [],
            "reason": "根据上下文回答",
        }

    async def generate(self, state):
        return f"我记得上一轮有 {len(state['conversation_history'])} 条消息。"


class ExactCodePlanningLLM:
    model_label = "exact-code-planner"

    async def plan(self, _query, _candidates):
        return {
            "intent": "stock_research",
            "stock_query": "920992",
            "tools": ["quote"],
            "focus": ["今日行情"],
            "reason": "根据证券名称确定当前交易代码",
        }

    async def generate(self, state):
        return f"已识别 {state['stock_name']}（{state['symbol']}）。[行情]"


class PlannedCodeResolver:
    def __init__(self):
        self.queries = []

    async def resolve_stock(self, query):
        self.queries.append(query)
        if query == "920992":
            return [
                {
                    "symbol": "920992.BJ",
                    "name": "中科美菱",
                    "exchange_name": "北京证券交易所",
                    "board": "北交所",
                }
            ]
        return []


class FakeResearchTools:
    def __init__(self):
        self.calls = []

    async def execute(self, name, symbol):
        self.calls.append((name, symbol))
        return {"source": f"fake-{name}", "data": {"symbol": symbol}}


@pytest.mark.asyncio
async def test_quote_flow_uses_fake_provider():
    graph = StockAgentGraph(FakeMarketDataProvider()).graph
    result = await graph.ainvoke({"query": "贵州茅台今天涨了多少？", "conversation_id": "test"})

    assert result["intent"] == "market_quote"
    assert result["symbol"] == "600519.SH"
    assert "1488.88" in result["answer"]
    assert "分析方式：" not in result["answer"]
    assert "取证来源：" not in result["answer"]


@pytest.mark.asyncio
async def test_high_risk_advice_is_rejected():
    graph = StockAgentGraph(FakeMarketDataProvider()).graph
    result = await graph.ainvoke({"query": "告诉我哪只股票可以全仓稳赚", "conversation_id": "test"})

    assert result["intent"] == "high_risk_advice"
    assert "不能承诺收益" in result["answer"]


@pytest.mark.asyncio
async def test_configured_llm_generates_answer():
    graph = StockAgentGraph(FakeMarketDataProvider(), llm=StubLLM()).graph
    result = await graph.ainvoke({"query": "什么是市盈率？", "conversation_id": "test"})

    assert "真实模型回答" in result["answer"]
    assert "不构成投资建议" in result["answer"]


@pytest.mark.asyncio
async def test_existing_risk_notice_is_not_duplicated():
    graph = StockAgentGraph(FakeMarketDataProvider(), llm=StubLLMWithRiskNotice()).graph
    result = await graph.ainvoke({"query": "中国平安今天走势？", "conversation_id": "test"})

    assert result["answer"].count("不构成投资建议") == 1


@pytest.mark.asyncio
async def test_llm_failure_falls_back_without_failing_the_agent_run():
    graph = StockAgentGraph(FakeMarketDataProvider(), llm=FailingLLM()).graph
    result = await graph.ainvoke({"query": "什么是市盈率？", "conversation_id": "test"})

    assert "AI 暂不可用" in result["answer"]
    assert "RAG 引用校验：" not in result["answer"]
    assert "不构成投资建议" in result["answer"]


@pytest.mark.asyncio
async def test_llm_plan_controls_tools_and_receives_all_evidence():
    llm = PlanningLLM()
    tools = FakeResearchTools()
    graph = StockAgentGraph(FakeMarketDataProvider(), llm=llm, research_tools=tools).graph

    result = await graph.ainvoke({"query": "分析贵州茅台的走势和舆情", "conversation_id": "test"})

    assert [name for name, _symbol in tools.calls] == ["quote", "kline", "sentiment"]
    assert set(llm.received_evidence) == {"quote", "kline", "sentiment"}
    assert result["analysis_mode"] == "AI 规划与综合（test-planner-model）"
    assert "AI 已综合趋势与新闻证据" in result["answer"]
    assert "工具证据校验：" not in result["answer"]


@pytest.mark.asyncio
async def test_llm_planned_stock_code_overrides_failed_initial_resolution():
    resolver = PlannedCodeResolver()
    tools = FakeResearchTools()
    graph = StockAgentGraph(
        FakeMarketDataProvider(),
        llm=ExactCodePlanningLLM(),
        research_tools=tools,
        resolver=resolver,
    ).graph

    result = await graph.ainvoke({"query": "研究一下中科美菱", "conversation_id": "test"})

    assert resolver.queries == ["研究一下中科美菱", "920992"]
    assert tools.calls == [("quote", "920992.BJ")]
    assert result["symbol"] == "920992.BJ"
    assert "中科美菱（920992.BJ）" in result["answer"]


@pytest.mark.asyncio
async def test_follow_up_reuses_current_conversation_symbol():
    graph = StockAgentGraph(FakeMarketDataProvider()).graph

    result = await graph.ainvoke(
        {
            "query": "它现在多少钱？",
            "conversation_id": "test",
            "current_symbol": "600519.SH",
            "conversation_history": [
                {"role": "user", "content": "帮我看看贵州茅台"},
                {"role": "assistant", "content": "好的。"},
            ],
        }
    )

    assert result["symbol"] == "600519.SH"
    assert "1488.88" in result["answer"]


@pytest.mark.asyncio
async def test_conversation_history_is_passed_to_planner_and_responder():
    llm = HistoryAwareLLM()
    history = [
        {"role": "user", "content": "我想看贵州茅台"},
        {"role": "assistant", "content": "好的。"},
    ]
    graph = StockAgentGraph(FakeMarketDataProvider(), llm=llm).graph

    result = await graph.ainvoke(
        {
            "query": "继续",
            "conversation_id": "test",
            "conversation_history": history,
        }
    )

    assert llm.received_history == history
    assert "2 条消息" in result["answer"]
