"""
Application configuration — loaded from environment variables or .env file.
All settings are centralised here so nothing is hard-coded elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Resolve project root & load .env
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]  # project root
load_dotenv(BASE_DIR / ".env", override=False)

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
# Dual-mode: OpenAI text-embedding-3-small (if OPENAI_API_KEY is set)
#            or TF-IDF + TruncatedSVD via scikit-learn (offline, no torch)
EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "512"))

# ---------------------------------------------------------------------------
# FAISS / retrieval
# ---------------------------------------------------------------------------
FAISS_INDEX_DIR: Path = BASE_DIR / os.getenv("FAISS_INDEX_DIR", "vector_store")
TOP_K: int = int(os.getenv("TOP_K", "5"))           # chunks returned per query
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "64"))

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_DIR: Path = BASE_DIR / "data"

# Document category → subfolder mapping (used for per-namespace FAISS index)
DOCUMENT_NAMESPACES: dict[str, Path] = {
    "stock_recommendations": DATA_DIR / "stock_recommendations",
    "company_profiles": DATA_DIR / "company_profiles",
    "market_reports": DATA_DIR / "market_reports",
    "regulations": DATA_DIR / "regulations",
}

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))
API_RELOAD: bool = os.getenv("API_RELOAD", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Confidence / score threshold (cosine distance — lower is better)
# ---------------------------------------------------------------------------
SCORE_THRESHOLD: float = float(os.getenv("SCORE_THRESHOLD", "1.2"))

