"""
build_index.py — offline script to pre-build the FAISS index.

Run this once before starting the server:
    python scripts/build_index.py

The index is saved to vector_store/ and loaded automatically by the app.
"""

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    from app.core.ingestion import load_all_chunks
    from app.core.vector_store import VectorStore

    logger.info("Loading documents …")
    chunks = load_all_chunks()
    logger.info("Total chunks: %d", len(chunks))

    by_ns: dict[str, int] = {}
    for c in chunks:
        by_ns[c.namespace] = by_ns.get(c.namespace, 0) + 1
    for ns, count in by_ns.items():
        logger.info("  %-28s %d chunks", ns, count)

    store = VectorStore()
    store.build(chunks)
    store.save()
    logger.info("✅ Index built and saved successfully.")


if __name__ == "__main__":
    main()
