"""Per-chat in-memory document store.

When a user uploads a file inside a chat session the text is chunked,
embedded, and stored here keyed by chat_id.  The same embedding pipeline
used for the main FAISS index is reused so scores are comparable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class _Chunk(NamedTuple):
    text: str
    vec: np.ndarray   # L2-normalised, shape (dim,)
    source: str       # original filename


# chat_id → list of chunks
_stores: dict[str, list[_Chunk]] = {}


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text(filename: str, content: bytes) -> str:
    """Return UTF-8 text from file bytes.  Supports txt/md/csv/pdf."""
    ext = Path(filename).suffix.lower()

    if ext in (".txt", ".md", ".csv", ".py", ".js", ".ts",
               ".json", ".yaml", ".yml", ".xml", ".html"):
        return content.decode("utf-8", errors="replace")

    if ext == ".pdf":
        try:
            import pypdf
            from io import BytesIO
            reader = pypdf.PdfReader(BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(p for p in pages if p.strip())
        except ImportError:
            # PDF dep not installed — try raw decode as best-effort
            return content.decode("utf-8", errors="replace")

    # Generic fallback
    return content.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """Split text into ~chunk_size-word chunks with overlap."""
    words = text.split()
    step = max(1, chunk_size - overlap)
    chunks = []
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Store / search / list
# ---------------------------------------------------------------------------

def store_chunks(chat_id: str, filename: str, content: bytes) -> int:
    """Extract, chunk, embed, and store content for *chat_id*.  Returns chunk count."""
    from app.core.embeddings import embed_texts  # imported late to avoid circular

    text = extract_text(filename, content)
    if not text.strip():
        return 0

    raw_chunks = chunk_text(text)
    if not raw_chunks:
        return 0

    vecs = embed_texts(raw_chunks)  # (N, dim), L2-normalised

    entries = [
        _Chunk(text=raw_chunks[i], vec=vecs[i].copy(), source=filename)
        for i in range(len(raw_chunks))
    ]

    if chat_id not in _stores:
        _stores[chat_id] = []
    _stores[chat_id].extend(entries)
    return len(entries)


def search(chat_id: str, query_vec: np.ndarray, top_k: int = 5) -> list[tuple[str, str, float]]:
    """Return [(text, source, score)] sorted descending."""
    entries = _stores.get(chat_id, [])
    if not entries:
        return []
    q = query_vec.flatten()
    results = [
        (c.text, c.source, float(np.dot(q, c.vec)))
        for c in entries
    ]
    results.sort(key=lambda x: -x[2])
    return results[:top_k]


def list_files(chat_id: str) -> list[str]:
    """Return unique filenames uploaded to this chat."""
    seen: set[str] = set()
    out: list[str] = []
    for c in _stores.get(chat_id, []):
        if c.source not in seen:
            seen.add(c.source)
            out.append(c.source)
    return out


def remove_file(chat_id: str, filename: str) -> bool:
    """Remove all chunks belonging to *filename* from a chat. Returns True if anything was removed."""
    entries = _stores.get(chat_id)
    if not entries:
        return False
    before = len(entries)
    _stores[chat_id] = [c for c in entries if c.source != filename]
    if not _stores[chat_id]:
        del _stores[chat_id]
    return len(_stores.get(chat_id, [])) < before


def clear_chat(chat_id: str) -> None:
    _stores.pop(chat_id, None)
