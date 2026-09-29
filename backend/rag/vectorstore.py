"""
Vector store for the fashion knowledge base (RAG).

Uses ChromaDB with a persistent local database and local Sentence Transformers
embeddings. No external embedding API is needed.

The knowledge comes from the Markdown files in data/fashion_knowledge/.
Splitting those files into chunks and loading them is done elsewhere; this
file only provides simple helpers to store and search chunks.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions

# Project root = the folder that contains backend/ (this file is backend/rag/vectorstore.py).
# Resolving from __file__ means the path is correct no matter where the app is started from.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DB_PATH = PROJECT_ROOT / "chroma_db"

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "fashion_knowledge"


@lru_cache(maxsize=1)
def _get_embedding_function():
    """Load the local embedding model once and reuse it."""
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL_NAME
    )


@lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.ClientAPI:
    """Return the persistent ChromaDB client (data is saved in chroma_db/)."""
    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DB_PATH))


def get_collection() -> chromadb.Collection:
    """Return the fashion_knowledge collection, creating it if needed."""
    return get_chroma_client().get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=_get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )


def add_documents(
    ids: List[str],
    documents: List[str],
    metadatas: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Add document chunks to the collection.

    Args:
        ids: A unique ID for each chunk, e.g. "color_theory.md::0".
        documents: The text of each chunk.
        metadatas: Optional metadata for each chunk, e.g. {"source": "color_theory.md"}.

    Uses upsert, so running it again with the same IDs updates the chunks
    instead of raising a duplicate-ID error.
    """
    collection = get_collection()
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def query_collection(
    query_text: str,
    n_results: int = 4,
    where: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Find the chunks most similar to query_text.

    Args:
        query_text: The question or search text.
        n_results: How many chunks to return.
        where: Optional metadata filter, e.g. {"source": "footwear.md"}.

    Returns:
        A list of dicts with "id", "text", "metadata" and "distance"
        (a smaller distance means a closer match).
    """
    collection = get_collection()
    result = collection.query(
        query_texts=[query_text],
        n_results=n_results,
        where=where,
    )

    matches: List[Dict[str, Any]] = []
    for i, chunk_id in enumerate(result["ids"][0]):
        matches.append(
            {
                "id": chunk_id,
                "text": result["documents"][0][i],
                "metadata": result["metadatas"][0][i],
                "distance": result["distances"][0][i],
            }
        )
    return matches