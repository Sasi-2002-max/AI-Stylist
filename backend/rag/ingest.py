"""
Ingest the fashion knowledge Markdown files into ChromaDB.

Run from the project root with:

    python -m backend.rag.ingest

Steps:
  1. Find every .md file inside data/fashion_knowledge/
  2. Read each file (the files are never modified)
  3. Split the text into chunks of about 900 characters with 150 characters of overlap
  4. Store the chunks in the ChromaDB "fashion_knowledge" collection

Embeddings are created by ChromaDB through vectorstore.py, not here.
Chunk IDs are deterministic (for example "color_theory.md::chunk_0"), so running
this script again updates the same chunks instead of piling up duplicates.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple

from backend.rag.vectorstore import PROJECT_ROOT, add_documents, get_collection

KNOWLEDGE_DIR = PROJECT_ROOT / "data" / "fashion_knowledge"

CHUNK_SIZE = 900      # maximum characters per chunk (including the overlap)
CHUNK_OVERLAP = 150   # characters repeated from the end of the previous chunk


def find_markdown_files(directory: Path) -> List[Path]:
    """Return all .md files inside the directory (including subfolders), sorted."""
    return sorted(directory.rglob("*.md"))


def _split_into_blocks(text: str) -> List[str]:
    """
    Split Markdown text into blocks separated by blank lines.

    A block is a heading, a paragraph or a bullet list. Very long blocks are
    cut into pieces so that no block is larger than CHUNK_SIZE.
    """
    blocks: List[str] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        while len(block) > CHUNK_SIZE:
            cut = block.rfind(" ", 0, CHUNK_SIZE)
            if cut <= 0:
                cut = CHUNK_SIZE
            blocks.append(block[:cut].strip())
            block = block[cut:].strip()
        if block:
            blocks.append(block)
    return blocks


def _overlap_tail(chunk: str) -> str:
    """Return roughly the last CHUNK_OVERLAP characters of a chunk, starting at a word boundary."""
    if len(chunk) <= CHUNK_OVERLAP:
        return chunk
    tail = chunk[-CHUNK_OVERLAP:]
    first_space = tail.find(" ")
    if first_space != -1:
        tail = tail[first_space + 1:]
    return tail.strip()


def split_into_chunks(text: str) -> List[Tuple[str, str]]:
    """
    Split text into overlapping chunks.

    Returns a list of (chunk_text, heading) pairs, where heading is the most
    recent Markdown heading found before the chunk's new content started.
    """
    chunks: List[Tuple[str, str]] = []
    current = ""
    current_heading = ""      # latest heading seen while reading
    chunk_heading = ""        # heading that applies to the chunk being built
    has_new_content = False   # True once the chunk holds more than just the overlap

    for block in _split_into_blocks(text):
        if block.startswith("#"):
            current_heading = block.lstrip("#").strip()

        candidate = f"{current}\n\n{block}" if current else block

        if len(candidate) <= CHUNK_SIZE:
            if not has_new_content:
                chunk_heading = current_heading
            current = candidate
            has_new_content = True
        else:
            # The block does not fit: save the current chunk and start a new one
            # that begins with the overlap from the end of the saved chunk.
            if has_new_content:
                chunks.append((current, chunk_heading))
                current = _overlap_tail(current)
            candidate = f"{current}\n\n{block}" if current else block
            if len(candidate) > CHUNK_SIZE:
                candidate = block  # overlap + block too long, so drop the overlap
            current = candidate
            chunk_heading = current_heading
            has_new_content = True

    if has_new_content and current.strip():
        chunks.append((current, chunk_heading))

    return chunks


def build_chunk_records(
    source: str, text: str
) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    """Turn one file's text into the ids, documents and metadatas lists for ChromaDB."""
    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for index, (chunk_text, heading) in enumerate(split_into_chunks(text)):
        ids.append(f"{source}::chunk_{index}")
        documents.append(chunk_text)
        metadatas.append(
            {
                "source": source,
                "source_type": "markdown",
                "chunk_index": index,
                "heading": heading,
            }
        )
    return ids, documents, metadatas


def ingest() -> int:
    """Ingest all Markdown files and return the total number of chunks stored."""
    if not KNOWLEDGE_DIR.exists():
        print(f"Knowledge folder not found: {KNOWLEDGE_DIR}")
        return 0

    files = find_markdown_files(KNOWLEDGE_DIR)
    print(f"Found {len(files)} Markdown file(s) in {KNOWLEDGE_DIR}")
    if not files:
        return 0

    collection = get_collection()
    total_chunks = 0

    for path in files:
        source = path.relative_to(KNOWLEDGE_DIR).as_posix()
        print(f"Processing: {source}")

        text = path.read_text(encoding="utf-8")
        ids, documents, metadatas = build_chunk_records(source, text)
        print(f"  Created {len(ids)} chunk(s)")

        if not ids:
            continue

        # Remove old chunks of this file first, so chunks left over from an
        # earlier, longer version of the file do not stay in the database.
        collection.delete(where={"source": source})

        add_documents(ids=ids, documents=documents, metadatas=metadatas)
        total_chunks += len(ids)

    print(f"Done. Total chunks stored: {total_chunks}")
    return total_chunks


if __name__ == "__main__":
    ingest()