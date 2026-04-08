"""
FAISS vector store — one flat index per namespace + a global merged index.
Hybrid search via Reciprocal Rank Fusion (RRF) with BM25 keyword search.

Architecture
------------
1. Per-namespace HNSW-flat indexes (vector, fast ANN)
2. A global IVF-flat index (vector, full-corpus)
3. Per-namespace + global BM25Okapi indexes (keyword)

Hybrid search (RRF)
-------------------
Both vector results and BM25 results are ranked independently.
Final score = α·(1/(k+r_v)) + (1-α)·(1/(k+r_bm25))
  α   = 0.60 (vector weight)  — semantic query understanding
  1-α = 0.40 (BM25 weight)    — exact term matching (tickers, numbers, ratings)
  k   = 60                    — standard RRF constant

Why 60/40 vector/BM25 for financial documents:
* Financial queries often contain exact terms: "PTT", "BUY", "42.00", "P/E"
* BM25 excels at finding these exact tokens reliably
* Vector handles semantic equivalence: "recommendation" ≈ "investment rating"
* 60/40 balances both signals without over-relying on either
"""

from __future__ import annotations

import json
import logging
import pickle
import re
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from app.core.config import EMBEDDING_DIM, FAISS_INDEX_DIR, TOP_K
from app.core.ingestion import Chunk

# Hybrid search constants
_RRF_K: int = 60          # RRF constant — higher = less rank-sensitive
_RRF_ALPHA: float = 0.60  # weight for vector results (1-alpha for BM25)


def _tokenize(text: str) -> list[str]:
    """Lowercase word-tokenise, keeping numbers and financial abbreviations."""
    tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9./%]*", text.lower())
    return tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hnsw_index(dim: int) -> faiss.IndexHNSWFlat:
    """Create an HNSW index with sensible defaults."""
    index = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
    index.hnsw.efConstruction = 200
    index.hnsw.efSearch = 64
    return index


def _ivf_flat_index(dim: int, n_vectors: int) -> faiss.IndexIVFFlat:
    """Create an IVF-flat index sized for *n_vectors* vectors."""
    n_list = max(4, min(256, n_vectors // 10))
    quantizer = faiss.IndexFlatIP(dim)
    index = faiss.IndexIVFFlat(quantizer, dim, n_list, faiss.METRIC_INNER_PRODUCT)
    return index


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------

class VectorStore:
    """
    Manages FAISS indexes and their associated chunk metadata.

    Public methods
    --------------
    build(chunks)      — index a fresh list of Chunk objects
    save()             — persist indexes + metadata to disk
    load()             — restore from disk
    search(query_vec)  — hybrid search across namespaces + global
    """

    def __init__(self) -> None:
        # Per-namespace: {namespace: faiss.Index}
        self._ns_indexes: dict[str, faiss.IndexHNSWFlat] = {}
        # Per-namespace: {namespace: list[Chunk]}
        self._ns_chunks: dict[str, list[Chunk]] = {}

        # Global index + chunk list
        self._global_index: Optional[faiss.Index] = None
        self._global_chunks: list[Chunk] = []

        # BM25 keyword indexes
        self._bm25_ns: dict[str, BM25Okapi] = {}
        self._bm25_global: Optional[BM25Okapi] = None

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, chunks: list[Chunk]) -> None:
        """Index *chunks* into per-namespace HNSW, global IVF, and BM25 indexes."""
        from app.core.embeddings import embed_texts, fit_lsa, _use_openai, _use_ollama_embed, get_embedding_dim

        logger.info("Building FAISS indexes for %d chunks …", len(chunks))

        # If using TF-IDF mode (not Ollama, not OpenAI), fit the LSA pipeline on the full corpus first
        if not _use_openai() and not _use_ollama_embed():
            logger.info("TF-IDF mode: fitting LSA pipeline …")
            all_texts_for_fit = [c.text for c in chunks]
            fit_lsa(all_texts_for_fit)
        elif _use_ollama_embed():
            logger.info("Ollama embedding mode — using bge-m3")

        # Resolve actual embedding dim (may differ from config in TF-IDF mode)
        dim = get_embedding_dim()

        # Group by namespace
        ns_groups: dict[str, list[Chunk]] = {}
        for chunk in chunks:
            ns_groups.setdefault(chunk.namespace, []).append(chunk)

        # ── Per-namespace HNSW + BM25 ───────────────────────────────────
        for ns, ns_chunks in ns_groups.items():
            texts = [c.text for c in ns_chunks]
            vectors = embed_texts(texts)

            index = _hnsw_index(dim)
            index.add(vectors)

            self._ns_indexes[ns] = index
            self._ns_chunks[ns] = ns_chunks
            self._bm25_ns[ns] = BM25Okapi([_tokenize(t) for t in texts])
            logger.info("  [%s] %d chunks indexed (HNSW + BM25)", ns, len(ns_chunks))

        # ── Global IVF-flat + BM25 ─────────────────────────────────────
        all_texts = [c.text for c in chunks]
        all_vectors = embed_texts(all_texts)

        if len(chunks) < 40:
            # Too few vectors to train IVF — fall back to flat index
            global_index: faiss.Index = faiss.IndexFlatIP(dim)
        else:
            global_index = _ivf_flat_index(dim, len(chunks))
            global_index.train(all_vectors)  # type: ignore[attr-defined]
            global_index.nprobe = 10  # type: ignore[attr-defined]

        global_index.add(all_vectors)
        self._global_index = global_index
        self._global_chunks = chunks
        self._bm25_global = BM25Okapi([_tokenize(t) for t in all_texts])
        logger.info("  [global] %d chunks indexed (IVF + BM25)", len(chunks))

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------

    def save(self) -> None:
        FAISS_INDEX_DIR.mkdir(parents=True, exist_ok=True)

        # Save per-namespace indexes
        for ns, index in self._ns_indexes.items():
            faiss.write_index(index, str(FAISS_INDEX_DIR / f"{ns}.faiss"))
            with open(FAISS_INDEX_DIR / f"{ns}_chunks.pkl", "wb") as f:
                pickle.dump(self._ns_chunks[ns], f)
            with open(FAISS_INDEX_DIR / f"{ns}_bm25.pkl", "wb") as f:
                pickle.dump(self._bm25_ns[ns], f)

        # Save global index
        if self._global_index is not None:
            faiss.write_index(self._global_index, str(FAISS_INDEX_DIR / "global.faiss"))
            with open(FAISS_INDEX_DIR / "global_chunks.pkl", "wb") as f:
                pickle.dump(self._global_chunks, f)
        if self._bm25_global is not None:
            with open(FAISS_INDEX_DIR / "global_bm25.pkl", "wb") as f:
                pickle.dump(self._bm25_global, f)

        # Persist LSA pipeline if in TF-IDF mode
        from app.core.embeddings import _lsa_pipeline, _use_openai, _use_ollama_embed, get_embedding_dim
        lsa_path = FAISS_INDEX_DIR / "lsa_pipeline.pkl"
        if not _use_openai() and not _use_ollama_embed() and _lsa_pipeline is not None:
            with open(lsa_path, "wb") as f:
                pickle.dump(_lsa_pipeline, f)
            logger.info("LSA pipeline saved to %s", lsa_path)

        # Save namespace manifest
        from app.core.embeddings import _use_ollama_embed
        if _use_ollama_embed():
            mode = "ollama"
        elif _use_openai():
            mode = "openai"
        else:
            mode = "tfidf"
        manifest = {
            "namespaces": list(self._ns_indexes.keys()),
            "embedding_mode": mode,
            "embedding_dim": get_embedding_dim(),
        }
        (FAISS_INDEX_DIR / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        logger.info("VectorStore saved to %s", FAISS_INDEX_DIR)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> None:
        manifest_path = FAISS_INDEX_DIR / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                f"No FAISS index found at {FAISS_INDEX_DIR}. "
                "Run `python scripts/build_index.py` first."
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for ns in manifest["namespaces"]:
            self._ns_indexes[ns] = faiss.read_index(
                str(FAISS_INDEX_DIR / f"{ns}.faiss")
            )
            with open(FAISS_INDEX_DIR / f"{ns}_chunks.pkl", "rb") as f:
                self._ns_chunks[ns] = pickle.load(f)
            bm25_path = FAISS_INDEX_DIR / f"{ns}_bm25.pkl"
            if bm25_path.exists():
                with open(bm25_path, "rb") as f:
                    self._bm25_ns[ns] = pickle.load(f)

        self._global_index = faiss.read_index(str(FAISS_INDEX_DIR / "global.faiss"))
        with open(FAISS_INDEX_DIR / "global_chunks.pkl", "rb") as f:
            self._global_chunks = pickle.load(f)
        global_bm25_path = FAISS_INDEX_DIR / "global_bm25.pkl"
        if global_bm25_path.exists():
            with open(global_bm25_path, "rb") as f:
                self._bm25_global = pickle.load(f)

        # Restore LSA pipeline if the index was built in TF-IDF mode
        lsa_path = FAISS_INDEX_DIR / "lsa_pipeline.pkl"
        em = manifest.get("embedding_mode", "tfidf")
        if em == "tfidf" and lsa_path.exists():
            import app.core.embeddings as _emb_mod
            with open(lsa_path, "rb") as f:
                _emb_mod._lsa_pipeline = pickle.load(f)
            # Restore the actual dim that was used at build time
            if "embedding_dim" in manifest:
                _emb_mod._actual_dim = manifest["embedding_dim"]
            logger.info("LSA pipeline restored from %s", lsa_path)
        else:
            logger.info("Embedding mode: %s (dim=%s)", em, manifest.get("embedding_dim"))

        logger.info("VectorStore loaded from %s", FAISS_INDEX_DIR)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = TOP_K,
        namespace: Optional[str] = None,
        query_text: str = "",
    ) -> list[tuple[Chunk, float]]:
        """
        Hybrid search: RRF fusion of FAISS vector search + BM25 keyword search.

        Parameters
        ----------
        query_vector : (1, dim) float32 L2-normalised array
        top_k        : number of results to return
        namespace    : restrict to this namespace (None = global)
        query_text   : raw query string for BM25 (empty = skip BM25)

        Returns
        -------
        List of (Chunk, rrf_score) sorted descending.
        """
        # candidate pool for re-ranking — retrieve 3× to ensure coverage
        pool = min(top_k * 3, 50)

        if namespace and namespace in self._ns_indexes:
            faiss_index = self._ns_indexes[namespace]
            chunks = self._ns_chunks[namespace]
            bm25_index = self._bm25_ns.get(namespace)
        else:
            faiss_index = self._global_index
            chunks = self._global_chunks
            bm25_index = self._bm25_global

        vector_results = self._search_index(faiss_index, chunks, query_vector, pool)

        if query_text and bm25_index is not None:
            bm25_results = self._bm25_search(bm25_index, chunks, query_text, pool)
            fused = self._rrf_fusion(vector_results, bm25_results)
        else:
            fused = vector_results

        return fused[:top_k]

    @staticmethod
    def _search_index(
        index: faiss.Index,
        chunks: list[Chunk],
        query_vector: np.ndarray,
        top_k: int,
    ) -> list[tuple[Chunk, float]]:
        k = min(top_k, len(chunks))
        distances, indices = index.search(query_vector, k)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            results.append((chunks[idx], float(dist)))
        return results

    @staticmethod
    def _bm25_search(
        bm25: BM25Okapi,
        chunks: list[Chunk],
        query_text: str,
        top_k: int,
    ) -> list[tuple[Chunk, float]]:
        query_tokens = _tokenize(query_text)
        if not query_tokens:
            return []
        scores = bm25.get_scores(query_tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(chunks[i], float(scores[i])) for i in top_indices if scores[i] > 0]

    @staticmethod
    def _rrf_fusion(
        vector_results: list[tuple[Chunk, float]],
        bm25_results: list[tuple[Chunk, float]],
    ) -> list[tuple[Chunk, float]]:
        """
        Reciprocal Rank Fusion with per-signal weighting.
        score(d) = α·1/(k+rank_v) + (1-α)·1/(k+rank_bm25)
        """
        k, alpha = _RRF_K, _RRF_ALPHA
        scores: dict[int, float] = {}
        chunk_map: dict[int, Chunk] = {}

        for rank, (chunk, _) in enumerate(vector_results):
            cid = id(chunk)
            chunk_map[cid] = chunk
            scores[cid] = scores.get(cid, 0.0) + alpha / (k + rank)

        for rank, (chunk, _) in enumerate(bm25_results):
            cid = id(chunk)
            chunk_map[cid] = chunk
            scores[cid] = scores.get(cid, 0.0) + (1 - alpha) / (k + rank)

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(chunk_map[cid], score) for cid, score in ranked]
