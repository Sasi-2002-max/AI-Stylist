"""
Fashion knowledge retrieval tool, exposed to the Stylist Agent's LLM.

Architecture:

    stylist_agent.py
          |
          v
    retrieve_fashion_knowledge()   <-- this file
          |
          v
    backend.rag.retriever.retrieve_relevant_chunks()
          |
          v
    ChromaDB

This file does not open a second ChromaDB connection: it only calls the
existing, already-tested retriever. It never modifies ingest.py,
vectorstore.py, or retriever.py.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from backend.rag.retriever import retrieve_relevant_chunks

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5


def retrieve_fashion_knowledge(query: str, top_k: int = DEFAULT_TOP_K) -> List[str]:
    """
    Retrieve fashion knowledge passages relevant to a query.

    This is the function the Stylist Agent's LLM calls as a tool. It never
    exposes ChromaDB objects, embeddings, or metadata structures to the
    caller -- only clean text.

    Args:
        query: A natural-language fashion knowledge question, e.g.
            "colors that suit warm skin tone".
        top_k: Maximum number of passages to retrieve (default 5).

    Returns:
        A list of formatted strings, each like:
            "[Source 1]\\n<passage text>"
        Returns an empty list if the query is empty or nothing was found.
    """
    query = (query or "").strip()
    if not query:
        logger.warning("retrieve_fashion_knowledge called with an empty query.")
        return []

    if not isinstance(top_k, int) or top_k < 1:
        top_k = DEFAULT_TOP_K

    results = retrieve_relevant_chunks(query, top_k=top_k)

    formatted: List[str] = []
    for item in results:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        formatted.append(f"[Source {len(formatted) + 1}]\n{text}")

    return formatted


# ---------------------------------------------------------------------------
# Tool schema (Groq / OpenAI-style "tools" format)
# ---------------------------------------------------------------------------

RETRIEVE_FASHION_KNOWLEDGE_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "retrieve_fashion_knowledge",
        "description": (
            "Retrieve relevant fashion knowledge from the StyleAI fashion "
            "knowledge base.\n\n"
            "Use this tool when you need additional fashion knowledge to "
            "make the outfit recommendation, such as:\n"
            "- color coordination\n"
            "- skin tone and color compatibility\n"
            "- body-shape styling\n"
            "- occasion-specific dressing\n"
            "- formality\n"
            "- fit and silhouette\n"
            "- seasonal or environmental styling\n"
            "- fashion coordination\n\n"
            "Do not use this tool to search for or rank real products, "
            "shopping websites, or retailers."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A natural-language fashion knowledge question, e.g. "
                        "'colors that suit warm skin tone' or 'rectangle body "
                        "shape flattering silhouettes'."
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of knowledge passages to retrieve.",
                    "default": DEFAULT_TOP_K,
                },
            },
            "required": ["query"],
        },
    },
}