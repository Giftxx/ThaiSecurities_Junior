"""
Embedding layer — dual-mode design.

Priority
--------
1. OpenAI text-embedding-3-small (best semantic quality, requires API key)
2. TF-IDF + TruncatedSVD via scikit-learn (zero-install fallback, always works)

Both modes produce L2-normalised float32 vectors of EMBEDDING_DIM dimensions,
so the FAISS indexes are fully interchangeable between modes.

Architecture rationale
-----------------------
sentence-transformers requires PyTorch (~1 GB download) which is unavailable
offline.  TF-IDF + Latent Semantic Analysis (LSA) is a classical, proven
technique that works well for financial documents with domain-specific
terminology ("BUY", "P/E ratio", "target price …").
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from app.core.config import EMBEDDING_DIM, OPENAI_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mode detection  (priority: Gemini > OpenAI > TF-IDF)
# ---------------------------------------------------------------------------

import os as _os

# ---------------------------------------------------------------------------
# Ollama local embeddings (highest priority when configured)
# ---------------------------------------------------------------------------
_OLLAMA_BASE_URL: str = _os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_EMBEDDING_MODEL: str = _os.getenv("OLLAMA_EMBEDDING_MODEL", "")
_OLLAMA_EMBEDDING_DIM: int = int(_os.getenv("OLLAMA_EMBEDDING_DIM", "1024"))


def _use_ollama_embed() -> bool:
    return bool(_OLLAMA_EMBEDDING_MODEL)


# ---------------------------------------------------------------------------
# Gemini embeddings
# ---------------------------------------------------------------------------
_GEMINI_API_KEY: str = _os.getenv("GEMINI_API_KEY", "")
_GEMINI_EMBEDDING_MODEL: str = _os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-2-preview")
_GEMINI_EMBEDDING_DIM: int = int(_os.getenv("GEMINI_EMBEDDING_DIM", "3072"))


def _use_gemini() -> bool:
    return bool(_GEMINI_API_KEY) and not _use_ollama_embed()


def _use_openai() -> bool:
    return bool(OPENAI_API_KEY) and not _use_gemini() and not _use_ollama_embed()


# ---------------------------------------------------------------------------
# Mode 0 — Ollama local embeddings (bge-m3)
# ---------------------------------------------------------------------------


def _embed_ollama(texts: list[str]) -> np.ndarray:
    """Call Ollama /api/embed endpoint; returns L2-normalised (N, dim) array."""
    import urllib.request
    import json

    all_vecs: list[np.ndarray] = []
    for i in range(0, len(texts), 64):
        batch = texts[i : i + 64]
        body = json.dumps({"model": _OLLAMA_EMBEDDING_MODEL, "input": batch}).encode()
        req = urllib.request.Request(
            f"{_OLLAMA_BASE_URL}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        vecs = np.array(data["embeddings"], dtype=np.float32)
        all_vecs.append(vecs)
    vecs = np.vstack(all_vecs)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vecs / norms


# ---------------------------------------------------------------------------
# Mode 1 — Gemini embeddings
# ---------------------------------------------------------------------------

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client(api_key=_GEMINI_API_KEY)
    return _gemini_client


def _embed_gemini(texts: list[str]) -> np.ndarray:
    """Call Gemini Embedding API; returns L2-normalised (N, dim) array."""
    import re
    import time

    client = _get_gemini_client()
    all_vecs: list[np.ndarray] = []
    for i in range(0, len(texts), 64):
        batch = texts[i : i + 64]
        for attempt in range(5):
            try:
                result = client.models.embed_content(
                    model=_GEMINI_EMBEDDING_MODEL,
                    contents=batch,
                )
                break
            except Exception as exc:
                msg = str(exc)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    # Try to parse retry delay from the error message
                    m = re.search(r"retry[^\d]*(\d+(?:\.\d+)?)\s*s", msg, re.I)
                    wait = float(m.group(1)) + 5 if m else 65.0
                    logger.warning(
                        "Gemini embed quota exceeded — sleeping %.0fs (attempt %d/5)",
                        wait, attempt + 1,
                    )
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError("Gemini embed_content failed after 5 retries")
        vecs = np.array([e.values for e in result.embeddings], dtype=np.float32)
        all_vecs.append(vecs)
    vecs = np.vstack(all_vecs)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vecs / norms


# ---------------------------------------------------------------------------
# Mode 2 — OpenAI embeddings
# ---------------------------------------------------------------------------

_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def _embed_openai(texts: list[str]) -> np.ndarray:
    client = _get_openai_client()
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
        dimensions=EMBEDDING_DIM,
    )
    vecs = np.array([d.embedding for d in response.data], dtype=np.float32)
    # Already normalised by OpenAI, but re-normalise to be safe
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vecs / norms


# ---------------------------------------------------------------------------
# Mode 2 — TF-IDF + TruncatedSVD (Latent Semantic Analysis)
# ---------------------------------------------------------------------------

from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.decomposition import TruncatedSVD               # noqa: E402
from sklearn.pipeline import Pipeline                        # noqa: E402

_lsa_pipeline: Optional[Pipeline] = None
_corpus_texts: list[str] = []
_actual_dim: int = EMBEDDING_DIM   # updated by fit_lsa()


def get_embedding_dim() -> int:
    """Return the actual embedding dimension."""
    if _use_ollama_embed():
        return _OLLAMA_EMBEDDING_DIM
    if _use_gemini():
        return _GEMINI_EMBEDDING_DIM
    if _use_openai():
        return EMBEDDING_DIM
    return _actual_dim


def fit_lsa(corpus: list[str]) -> None:
    """
    Fit the TF-IDF → SVD pipeline on the full document corpus.
    Must be called once before embed_texts() in TF-IDF mode.

    The actual SVD output dimension is capped to min(EMBEDDING_DIM, n_samples - 1)
    to avoid rank deficiency errors on small corpora.
    """
    global _lsa_pipeline, _corpus_texts, _actual_dim
    _corpus_texts = corpus

    # Cap components: SVD cannot produce more dims than min(n_samples-1, n_features)
    n_components = min(EMBEDDING_DIM, len(corpus) - 1)
    _actual_dim = n_components

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
        )),
        ("svd", TruncatedSVD(n_components=n_components, n_iter=5, random_state=42)),
    ])
    pipeline.fit(corpus)
    _lsa_pipeline = pipeline
    logger.info(
        "LSA pipeline fitted on %d documents → %d-dim embeddings",
        len(corpus), n_components,
    )


def _embed_lsa(texts: list[str]) -> np.ndarray:
    if _lsa_pipeline is None:
        raise RuntimeError(
            "LSA pipeline not fitted. Call fit_lsa(corpus) before embedding."
        )
    vecs = _lsa_pipeline.transform(texts).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return vecs / norms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def embed_texts(texts: list[str], batch_size: int = 64) -> np.ndarray:
    """
    Return a float32 numpy array of shape (N, dim) for *texts*.
    Priority: Ollama > Gemini > OpenAI > TF-IDF+LSA
    """
    if _use_ollama_embed():
        return _embed_ollama(texts)
    if _use_gemini():
        return _embed_gemini(texts)
    if _use_openai():
        results = []
        for i in range(0, len(texts), batch_size):
            results.append(_embed_openai(texts[i : i + batch_size]))
        return np.vstack(results)
    return _embed_lsa(texts)


def embed_query(query: str) -> np.ndarray:
    """Return a (1, dim) float32 array for a single query string."""
    return embed_texts([query])


def embedding_mode() -> str:
    if _use_ollama_embed():
        return f"Ollama {_OLLAMA_EMBEDDING_MODEL}"
    if _use_gemini():
        return f"Gemini {_GEMINI_EMBEDDING_MODEL}"
    if _use_openai():
        return "OpenAI text-embedding-3-small"
    return "TF-IDF + LSA (scikit-learn)"
