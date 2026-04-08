"""
Index management service.

Provides a single application-level VectorStore instance that is built
once and reused.  The index is persisted to disk so subsequent startups
skip the (slow) embedding step.
"""

from __future__ import annotations

import logging

from app.core.ingestion import load_all_chunks
from app.core.vector_store import VectorStore
from app.core.config import FAISS_INDEX_DIR

logger = logging.getLogger(__name__)

_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """
    Return the singleton VectorStore, loading from disk if available
    or building from scratch otherwise.
    """
    global _store
    if _store is not None:
        return _store

    store = VectorStore()
    manifest_path = FAISS_INDEX_DIR / "manifest.json"

    if manifest_path.exists():
        logger.info("Loading existing FAISS index from disk …")
        store.load()
    else:
        logger.info("No existing index found — building from documents …")
        chunks = load_all_chunks()
        store.build(chunks)
        store.save()

    _store = store
    return _store


def rebuild_index() -> int:
    """Force-rebuild the index and return the number of chunks indexed."""
    global _store
    chunks = load_all_chunks()
    store = VectorStore()
    store.build(chunks)
    store.save()
    _store = store
    return len(chunks)
