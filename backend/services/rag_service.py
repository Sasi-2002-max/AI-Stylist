"""
RAG service layer.

Flow:  Query -> retrieve_relevant_chunks() -> formatted context string.

Only formats what backend/rag/retriever.py returns. No LLM, no web search,
no direct access to the vector store.
"""

from typing import List

from backend.rag.retriever import DEFAULT_TOP_K, retrieve_relevant_chunks

EMPTY_QUERY_MESSAGE = "No query provided. Please enter a fashion question."
NO_RESULTS_MESSAGE = "No relevant fashion knowledge found."


def get_fashion_context(query: str, top_k: int = DEFAULT_TOP_K) -> str:
    """
    Retrieve fashion knowledge for a query and return it as formatted text.

    Args:
        query: Natural-language fashion question.
        top_k: Number of chunks to retrieve (default 5). Values below 1
            fall back to the default.

    Returns:
        A string like:

            [Fashion Knowledge 1]
            Source: skin_tone_colors.md
            Section: Warm Skin Tones
            ...chunk text...

        or a short message if the query is empty or nothing was found.
    """
    if not isinstance(query, str) or not query.strip():
        return EMPTY_QUERY_MESSAGE

    if not isinstance(top_k, int) or top_k < 1:
        top_k = DEFAULT_TOP_K

    results = retrieve_relevant_chunks(query.strip(), top_k=top_k)

    blocks: List[str] = []
    for number, item in enumerate(results, start=1):
        lines = [f"[Fashion Knowledge {number}]", f"Source: {item['source']}"]
        if item.get("heading"):
            lines.append(f"Section: {item['heading']}")
        lines.append(item["text"].strip())
        blocks.append("\n".join(lines))

    if not blocks:
        return NO_RESULTS_MESSAGE

    return "\n\n".join(blocks)


if __name__ == "__main__":
    test_query = (
        "What colors and outfit styles suit warm skin tone and rectangle body shape?"
    )
    print(f"Query: {test_query}\n")
    print(get_fashion_context(test_query, top_k=5))