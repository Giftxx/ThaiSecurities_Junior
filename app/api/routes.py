"""
FastAPI application — REST API layer.

Endpoints
---------
GET  /health          — liveness check
GET  /namespaces      — list available document namespaces
POST /query           — ask a question, get an answer with citations
POST /admin/reindex   — trigger a full index rebuild (protected by key)
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.core.config import DOCUMENT_NAMESPACES, TOP_K
from app.core.rag_engine import RAGEngine
from app.services.index_service import get_vector_store, rebuild_index
from app.services import chat_store_service as _css

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Thai Securities Q&A API",
    description=(
        "Intelligent Q&A system for Thai securities market information. "
        "Powered by FAISS + sentence-transformers + GPT."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the HTML/CSS/JS UI from the ui/ folder at /ui
_UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if _UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    """Redirect root to the UI."""
    return RedirectResponse(url="/ui/index.html")


# ---------------------------------------------------------------------------
# Dependency — initialise vector store on first request
# ---------------------------------------------------------------------------

def _rag_engine() -> RAGEngine:
    vs = get_vector_store()
    return RAGEngine(vs)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, example="What is the recommendation for PTT stock?")
    top_k: int = Field(default=TOP_K, ge=1, le=20)
    namespace: Optional[str] = Field(
        default=None,
        example="stock_recommendations",
        description="Restrict search to a specific namespace (optional)",
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="Chat session ID — enables search in uploaded documents for this chat",
    )


class UploadRequest(BaseModel):
    chat_id: str = Field(..., description="Chat session ID to attach the document to")
    filename: str = Field(..., description="Original filename including extension")
    content_b64: str = Field(..., description="Base64-encoded file content")


class SourceItem(BaseModel):
    citation: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[str]
    namespace_used: Optional[str]
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    index_ready: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Liveness + readiness probe."""
    try:
        vs = get_vector_store()
        ready = vs._global_index is not None
    except Exception:
        ready = False
    return HealthResponse(status="ok", index_ready=ready)


@app.get("/namespaces", tags=["System"])
def list_namespaces():
    """Return available document namespaces."""
    return {"namespaces": list(DOCUMENT_NAMESPACES.keys())}


@app.post("/query", response_model=QueryResponse, tags=["Q&A"])
def query(req: QueryRequest, engine: RAGEngine = Depends(_rag_engine)):
    """
    Ask a financial question and receive an AI-generated answer with source citations.
    Pass chat_id to also search documents uploaded to that chat session.
    """
    t0 = time.perf_counter()
    result = engine.query(req.question, top_k=req.top_k, chat_id=req.chat_id)
    latency_ms = (time.perf_counter() - t0) * 1000

    return QueryResponse(
        answer=result.answer,
        sources=result.sources,
        namespace_used=result.namespace_used,
        latency_ms=round(latency_ms, 1),
    )


@app.post("/upload", tags=["Upload"])
def upload_file(req: UploadRequest):
    """Upload a document (base64-encoded) and index it for the specified chat session."""
    import base64

    # Ensure LSA pipeline is loaded before embedding
    get_vector_store()

    try:
        content = base64.b64decode(req.content_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64 content: {exc}")

    try:
        n = _css.store_chunks(req.chat_id, req.filename, content)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if n == 0:
        raise HTTPException(status_code=422, detail="Could not extract any text from the file.")

    return {"chunks_added": n, "filename": req.filename, "chat_id": req.chat_id}


@app.get("/upload/files", tags=["Upload"])
def list_uploaded_files(chat_id: str):
    """List files uploaded to a specific chat session."""
    return {"chat_id": chat_id, "files": _css.list_files(chat_id)}


@app.delete("/upload/files", tags=["Upload"])
def clear_uploaded_files(chat_id: str):
    """Remove all uploaded documents for a chat session."""
    _css.clear_chat(chat_id)
    return {"status": "cleared", "chat_id": chat_id}


@app.delete("/upload/file", tags=["Upload"])
def remove_uploaded_file(chat_id: str, filename: str):
    """Remove a single uploaded file from a chat session."""
    removed = _css.remove_file(chat_id, filename)
    if not removed:
        raise HTTPException(status_code=404, detail="File not found in chat session")
    return {"status": "removed", "chat_id": chat_id, "filename": filename}


@app.post("/admin/reindex", tags=["Admin"])
def reindex(x_admin_key: str = Header(...)):
    """
    Rebuild the FAISS index from raw documents.
    Requires X-Admin-Key header matching ADMIN_KEY env var.
    """
    expected = os.getenv("ADMIN_KEY", "changeme")
    if x_admin_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")
    n = rebuild_index()
    return {"status": "ok", "chunks_indexed": n}
