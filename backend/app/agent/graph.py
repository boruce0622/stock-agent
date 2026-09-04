import asyncio
import inspect
import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.research_tools import StockResearchTools
from app.agent.state import AgentState
from app.llm.gateway import LLMGateway
from app.providers.base import MarketDataProvider

RISK_NOTE = "以上内容仅用于信息与教育目的，不构成投资建议。市场有风险，请核验最新数据。"
LLM_PLAN_TIMEOUT_SECONDS = 25
LLM_RESPONSE_TIMEOUT_SECONDS = 70
ALLOWED_TOOLS = ("knowledge", "quote", "kline", "intraday", "sentiment")
logger = logging.getLogger(__name__)


class StockAgentGraph:
    def __init__(
        self,
        provider: MarketDataProvider,
        llm: LLMGateway | None = None,
        research_tools: StockResearchTools | None = None,
        resolver: MarketDataProvider | None = None,
    ):
        self.provider = provider
        self.resolver = resolver or provider
        self.llm = llm
        self.research_tools = research_tools or StockResearchTools(provider)
        builder = StateGraph(AgentState)
        builder.add_node("plan", self.plan)
        builder.add_node("execute_tools", self.execute_tools)
        builder.add_node("respond", self.respond)
        builder.add_edge(START, "plan")
        builder.add_conditional_edges(
            "plan", self.route_after_plan, {"execute_tools": "execute_tools", "respond": "respond"}
        )
        builder.add_edge("execute_tools", "respond")
        builder.add_edge("respond", END)
        self.graph = builder.compile()

    async def plan(self, state: AgentState) -> dict[str, Any]:
        query = state["query"].strip()
        candidates = await self.resolver.resolve_stock(query)
        current_symbol = state.get("current_symbol")
        if not candidates and current_symbol and self._is_contextual_follow_up(query):
            candidates = await self.resolver.resolve_stock(current_symbol)
        high_risk = any(word in query for word in ("稳赚", "保证收益", "梭哈", "全仓"))
        fallback = self._fallback_plan(query, candidates, high_risk)
        plan = fallback
        mode = "规则降级模式（未配置 AI 模型）"

        if self.llm is not None and not high_risk:
            try:
                raw_plan = await asyncio.wait_for(
                    self._plan_with_history(query, candidates, state),
                    timeout=LLM_PLAN_TIMEOUT_SECONDS,
                )
                plan = self._sanitize_plan(raw_plan, fallback)
                mode = f"AI 规划与综合（{self.llm.model_label}）"
            except Exception:
                logger.exception("LLM planning failed; using deterministic fallback plan")
                mode = "AI 规划失败，已使用规则规划"

        if plan.get("stock_query"):
            planned_candidates = await self.resolver.resolve_stock(str(plan["stock_query"]))
            if planned_candidates:
                candidates = planned_candidates
        symbol = candidates[0]["symbol"] if len(candidates) == 1 else None
        stock_name = candidates[0]["name"] if len(candidates) == 1 else None
        if len(candidates) == 1:
            plan["security"] = candidates[0]
        tools = list(plan.get("tools", []))
        if not symbol:
            tools = [name for name in tools if name == "knowledge"]
        if plan.get("intent") == "stock_research" and not symbol:
            plan["resolution_error"] = "未能唯一识别股票，请补充股票名称或代码"
        plan["tools"] = tools
        return {
            "intent": plan["intent"],
            "symbol": symbol,
            "stock_name": stock_name,
            "plan": plan,
            "risk_level": "high" if high_risk else "normal",
            "analysis_mode": mode,
        }

    async def _plan_with_history(
        self,
        query: str,
        candidates: list[dict[str, str]],
        state: AgentState,
    ) -> dict[str, Any]:
        """Pass history to modern gateways while keeping older custom gateways working."""
        history = state.get("conversation_history", [])
        if len(inspect.signature(self.llm.plan).parameters) >= 3:  # type: ignore[union-attr]
            return await self.llm.plan(query, candidates, history)  # type: ignore[union-attr]
        return await self.llm.plan(query, candidates)  # type: ignore[union-attr,call-arg]

    @staticmethod
    def _is_contextual_follow_up(query: str) -> bool:
        compact = query.strip().lower()
        references = (
            "它",
            "这只股",
            "该股",
            "该公司",
            "这个股票",
            "上面的",
            "刚才的",
            "那它",
        )
        follow_up_phrases = (
            "那呢",
            "这个呢",
            "风险呢",
            "走势呢",
            "怎么样",
            "继续分析",
            "再分析",
            "为什么",
        )
        return any(word in compact for word in (*references, *follow_up_phrases))

    @staticmethod
    def _fallback_plan(
        query: str, candidates: list[dict[str, str]], high_risk: bool
    ) -> dict[str, Any]:
        if high_risk:
            return {"intent": "high_risk_advice", "stock_query": None, "tools": [], "focus": []}
        if any(word in query.lower() for word in ("你好", "hello", "你能做什么")):
            return {"intent": "greeting", "stock_query": None, "tools": [], "focus": []}
        if candidates:
            tools = ["quote"]
            if any(word in query for word in ("走势", "趋势", "技术", "分析", "K线", "k线")):
                tools.append("kline")
            if any(word in query for word in ("盘中", "分时", "今日走势")):
                tools.append("intraday")
            if any(word in query for word in ("舆情", "新闻", "消息", "利好", "利空", "分析")):
                tools.append("sentiment")
            if any(word in query for word in ("分析", "风险", "规则", "指标")):
                tools.append("knowledge")
            return {
                "intent": "market_quote" if tools == ["quote"] else "stock_research",
                "stock_query": candidates[0]["name"],
                "tools": tools,
                "focus": ["按用户问题分析"],
                "reason": "规则降级规划",
            }
        return {
            "intent": "explanation",
            "stock_query": None,
            "tools": ["knowledge"],
            "focus": ["先检索知识库，再解释概念"],
        }

    @staticmethod
    def _sanitize_plan(raw: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        intents = {
            "greeting",
            "explanation",
            "market_quote",
            "stock_research",
            "high_risk_advice",
        }
        intent = raw.get("intent") if raw.get("intent") in intents else fallback["intent"]
        tools = []
        for name in raw.get("tools", []):
            if name in ALLOWED_TOOLS and name not in tools:
                tools.append(name)
        focus = [str(item)[:60] for item in raw.get("focus", [])[:4]]
        return {
            "intent": intent,
            "stock_query": raw.get("stock_query") or fallback.get("stock_query"),
            "tools": tools,
            "focus": focus,
            "reason": str(raw.get("reason") or "AI 根据用户问题制定取证计划")[:160],
        }

    @staticmethod
    def route_after_plan(state: AgentState) -> str:
        should_execute = bool(state.get("plan", {}).get("tools"))
        return "execute_tools" if should_execute else "respond"

    async def execute_tools(self, state: AgentState) -> dict[str, Any]:
        evidence: dict[str, Any] = {}
        for name in state.get("plan", {}).get("tools", []):
            try:
                if name == "knowledge":
                    evidence[name] = await self.research_tools.execute(
                        name, state.get("symbol"), query=state["query"]
                    )
                else:
                    evidence[name] = await self.research_tools.execute(name, state.get("symbol"))
            except Exception as exc:
                logger.exception("Research tool failed", extra={"tool": name})
                evidence[name] = {"ok": False, "error": str(exc)}
        return {
            "evidence": evidence,
            "tool_result": evidence.get("quote"),
            "error": (
                None
                if any(self._evidence_ok(item) for item in evidence.values())
                else "NO_EVIDENCE"
            ),
        }

    @staticmethod
    def _evidence_ok(item: Any) -> bool:
        return isinstance(item, dict) and item.get("ok", True) is not False

    async def respond(self, state: AgentState) -> dict[str, str]:
        if state["intent"] == "high_risk_advice":
            answer = "我不能承诺收益或替你作出全仓等高风险决定。我可以用模型梳理证据、情景与风险。"
        elif self.llm is not None:
            try:
                answer = await asyncio.wait_for(
                    self.llm.generate(state), timeout=LLM_RESPONSE_TIMEOUT_SECONDS
                )
            except Exception:
                logger.exception("LLM generation failed; using built-in evidence summary")
                answer = self._fallback_answer(state)
                state["analysis_mode"] = "AI 生成失败，已使用结构化摘要"
        else:
            answer = self._fallback_answer(state)

        answer, _ = self._validate_rag_grounding(answer, state)
        answer, _ = self._validate_tool_grounding(answer, state)

        if state["intent"] != "greeting" and "不构成投资建议" not in answer:
            answer += f"\n\n{RISK_NOTE}"
        return {"answer": answer}

    @staticmethod
    def _validate_tool_grounding(answer: str, state: AgentState) -> tuple[str, str | None]:
        if state.get("intent") != "stock_research":
            return answer, None
        tags = {
            "quote": "[行情]",
            "kline": "[K线]",
            "intraday": "[分时]",
            "sentiment": "[舆情]",
        }
        required = {
            tag
            for name, tag in tags.items()
            if isinstance(state.get("evidence", {}).get(name), dict)
            and state["evidence"][name].get("ok", True) is not False
        }
        missing = sorted(tag for tag in required if tag not in answer)
        if missing and state.get("analysis_mode", "").startswith("AI 规划与综合"):
            return (
                "模型回答未通过工具证据引用校验。为防止无法追溯的行情结论，本次已拦截，请重试。",
                f"未通过，缺少 {'、'.join(missing)}",
            )
        if missing:
            return answer, f"降级回答未使用 {'、'.join(missing)}"
        return answer, f"通过，已引用 {'、'.join(sorted(required))}"

    @staticmethod
    def _validate_rag_grounding(answer: str, state: AgentState) -> tuple[str, str | None]:
        knowledge = state.get("evidence", {}).get("knowledge")
        if not isinstance(knowledge, dict):
            return answer, None
        hits = knowledge.get("hits", [])
        if not hits:
            return answer, "无知识命中，不影响模型解释或其他工具取证"
        allowed = {str(hit.get("citation")) for hit in hits}
        cited = set(re.findall(r"\[知识库\d+\]", answer))
        valid = cited & allowed
        invalid = cited - allowed
        if not valid:
            return answer, "未使用可选的知识库引用"
        if invalid:
            return answer, "部分引用编号无效，请谨慎核验"
        return answer, f"通过，使用 {len(valid)}/{len(allowed)} 个命中文档"

    @staticmethod
    def _fallback_answer(state: AgentState) -> str:
        if state["intent"] == "greeting":
            return "你好！我可以先理解你的研究目标，再按需查询行情、K 线、分时与新闻并综合分析。"
        if state["intent"] == "stock_research" and not state.get("symbol"):
            return "我理解你想研究具体股票，但还不能唯一识别标的。请补充股票名称或代码。"
        evidence = state.get("evidence", {})
        quote = evidence.get("quote", {})
        if quote.get("ok"):
            data = quote.get("data", {})
            identity = f"{data.get('name', state.get('stock_name'))}（{state.get('symbol')}）"
            return f"{identity}现价 {data.get('price')} 元。AI 暂不可用，当前仅展示已核验事实。"
        if state["intent"] == "explanation":
            return (
                "我可以解释股票与指标概念，也可以基于行情、K 线和新闻进行分析。"
                f"你刚才的问题是：“{state['query']}”。AI 暂不可用，请稍后重试。"
            )
        return "本次可用证据不足，暂时无法形成可靠分析。"
