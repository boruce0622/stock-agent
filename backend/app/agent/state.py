from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    query: str
    conversation_id: str
    conversation_history: list[dict[str, str]]
    current_symbol: str | None
    intent: str
    symbol: str | None
    stock_name: str | None
    plan: dict[str, Any]
    evidence: dict[str, Any]
    analysis_mode: str
    tool_result: dict[str, Any] | None
    answer: str
    risk_level: str
    error: str | None
