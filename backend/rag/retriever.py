"""
Retriever for the fashion knowledge base (RAG).

Searches the existing ChromaDB collection "fashion_knowledge" (filled by
backend/rag/ingest.py) and returns the most relevant Markdown chunks.

All database and embedding settings come from vectorstore.py, so search uses the
same collection, storage folder (chroma_db/) and embedding model
(sentence-transformers/all-MiniLM-L6-v2) as ingestion. This file never ingests
or modifies anything; it only reads.

Typical use by an agent:

    results = retrieve_relevant_chunks(
        "What colors suit a person with warm skin tone?", top_k=5
    )
    context = format_retrieved_context(results)
"""

import logging
from typing import Any, Dict, List, Optional

from backend.rag.vectorstore import COLLECTION_NAME, get_collection, query_collection

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5


def retrieve_relevant_chunks(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source: Optional[str] = None,
    max_distance: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Find the knowledge chunks most relevant to a natural-language query.

    Args:
        query: A fashion question, e.g. "What colors suit warm skin tone?".
        top_k: Maximum number of chunks to return (at least 1).
        source: Optional filename filter, e.g. "footwear.md".
        max_distance: Optional cutoff. Chunks with a larger distance are dropped.
            Distances use cosine distance, so smaller means more similar.

    Returns:
        A list of dicts, best match first. Each dict has:
            "text"        - the chunk text
            "source"      - Markdown filename, e.g. "skin_tone_colors.md"
            "heading"     - nearest Markdown heading ("" if unknown)
            "chunk_index" - position of the chunk inside its file (or None)
            "distance"    - similarity distance (smaller = closer)
            "id"          - the chunk's ChromaDB ID

        Returns an empty list if the query is empty, the collection is empty,
        nothing matches, or the database cannot be reached (the error is logged).
    """
    query = (query or "").strip()
    if not query:
        logger.warning("retrieve_relevant_chunks called with an empty query.")
        return []

    top_k = max(1, int(top_k))

    try:
        total_chunks = get_collection().count()
        if total_chunks == 0:
            logger.warning(
                "Collection '%s' is empty. Run: python -m backend.rag.ingest",
                COLLECTION_NAME,
            )
            return []

        matches = query_collection(
            query_text=query,
            n_results=min(top_k, total_chunks),
            where={"source": source} if source else None,
        )
    except Exception:
        logger.exception("Could not search the '%s' collection.", COLLECTION_NAME)
        return []

    results: List[Dict[str, Any]] = []
    for match in matches:
        distance = match["distance"]
        if max_distance is not None and distance > max_distance:
            continue
        metadata = match.get("metadata") or {}
        results.append(
            {
                "text": match["text"],
                "source": metadata.get("source", "unknown"),
                "heading": metadata.get("heading", ""),
                "chunk_index": metadata.get("chunk_index"),
                "distance": distance,
                "id": match["id"],
            }
        )
    return results


def format_retrieved_context(results: List[Dict[str, Any]]) -> str:
    """
    Turn retrieved chunks into one clean text block for an LLM prompt.

    Each chunk is numbered and labelled with its source file and heading.
    Returns an empty string when there are no results.
    """
    if not results:
        return ""

    parts: List[str] = []
    for number, item in enumerate(results, start=1):
        label = item["source"]
        if item.get("heading"):
            label += f" > {item['heading']}"
        parts.append(f"[{number}] Source: {label}\n{item['text']}")
    return "\n\n".join(parts)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    sample_query = "What colors suit a person with warm skin tone?"
    print(f"Query: {sample_query}\n")

    found = retrieve_relevant_chunks(sample_query, top_k=3)
    if not found:
        print("No results. Make sure you have run: python -m backend.rag.ingest")
    else:
        for item in found:
            print(
                f"- {item['source']} > {item['heading']} "
                f"(chunk {item['chunk_index']}, distance {item['distance']:.3f})"
            )
            print(f"  {item['text'][:150].replace(chr(10), ' ')}...\n")

        print("---- Context for an LLM ----")
        print(format_retrieved_context(found))