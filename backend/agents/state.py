from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    """
    AgentState is the shared state passed between agents in the AI Fashion
    Stylist workflow.

    Each agent reads the fields it needs from this state and writes its own
    results back, so information flows through the whole workflow:
    profile and query -> style understanding -> RAG -> outfit plan ->
    product search -> fitting room -> critic review.
    """

    user_profile: dict[str, Any]
    user_query: str
    style_context: dict[str, Any]
    rag_context: list[Any]
    outfit_plan: dict[str, Any]
    product_candidates: list[Any]
    selected_products: list[Any]
    fitting_room: dict[str, Any]
    critic_feedback: dict[str, Any]
    iteration: int
    status: str