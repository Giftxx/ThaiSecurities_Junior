"""
Document ingestion layer.

Responsibilities
----------------
* Load every Markdown file from each data namespace.
* Split documents into section-level chunks (H2/H3 boundaries).
* Prepend section heading into chunk text for richer embedding context.
* Attach rich metadata (source file, namespace, section heading).

Chunking strategy
-----------------
Previous approach split on blank lines → small decontextualised fragments,
heading only in metadata (not embedded).

New approach: section-level chunking
* Parse document into sections at H2/H3 heading boundaries.
* Keep heading + all content (paragraphs, tables, bullet lists) as one unit.
* Prepend heading into the embedded text so the embedding captures context.
* Only apply sliding-window split when a section exceeds CHUNK_SIZE words.
  Each window also starts with the section heading for context continuity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from app.core.config import CHUNK_OVERLAP, CHUNK_SIZE, DOCUMENT_NAMESPACES


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """A single piece of text with provenance metadata."""

    text: str
    namespace: str          # e.g. "stock_recommendations"
    source_file: str        # relative path from data/
    section: str = ""       # nearest H2/H3 heading above this chunk
    chunk_index: int = 0

    # Convenience: full display label shown in citations
    @property
    def citation(self) -> str:
        label = self.source_file
        if self.section:
            # Strip doc-title prefix (everything before " — ") for brevity in UI
            display_section = self.section.split(" — ", 1)[-1]
            label += f" › {display_section}"
        return label


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

def _heading_level(line: str) -> int:
    """Return heading depth (1-6) or 0 if not a heading."""
    m = re.match(r"^(#{1,6})\s", line.strip())
    return len(m.group(1)) if m else 0


def _strip_heading_prefix(line: str) -> str:
    return re.sub(r"^#+\s*", "", line.strip())


def _is_noise(text: str) -> bool:
    """Return True for separator-only or empty blocks."""
    stripped = re.sub(r"[-*_|`\s]", "", text)
    return len(stripped) < 8


def _sliding_window(heading: str, body: str, size: int, overlap: int) -> Iterator[str]:
    """
    Yield overlapping windows over *body*.
    Each window is prefixed with *heading* so the section context
    is present in every chunk that the model eventually embeds.
    """
    words = body.split()
    if not words:
        return
    step = max(1, size - overlap)
    prefix = f"{heading}\n\n" if heading else ""
    prefix_words = len(prefix.split())
    effective_size = max(1, size - prefix_words)
    for start in range(0, len(words), max(1, effective_size - overlap)):
        chunk_words = words[start : start + effective_size]
        if chunk_words:
            yield prefix + " ".join(chunk_words)


def _load_sections(path: Path) -> list[tuple[str, str]]:
    """
    Parse a Markdown file into (heading, body_text) pairs.

    Strategy
    --------
    * Split at H1/H2/H3 boundaries (not at every blank line).
    * All content between two headings becomes the body of the earlier heading.
    * The document title (H1) is prepended to every H2/H3 section heading so
      that e.g. "Investment Recommendation" for PTT becomes
      "Stock Research Report: PTT — Investment Recommendation".
      This ensures ticker/company name is present in every section chunk,
      which is critical for BM25 exact-match retrieval.
    * Horizontal rules (---) and front-matter bold lines are included in body.

    This keeps tables, bullet lists, and paragraphs together with their
    section heading — critical for financial documents.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    sections: list[tuple[str, str]] = []
    doc_title = ""          # H1 title — prepended to all sub-sections
    current_heading = ""
    body_lines: list[str] = []

    def flush() -> None:
        body = "\n".join(body_lines).strip()
        # Strip leading/trailing horizontal rules and blank lines
        body = re.sub(r"^\s*-{3,}\s*\n?", "", body).strip()
        body = re.sub(r"\n?\s*-{3,}\s*$", "", body).strip()
        if body and not _is_noise(body):
            sections.append((current_heading, body))
        body_lines.clear()

    for raw in lines:
        lvl = _heading_level(raw)
        if lvl == 1:
            flush()
            doc_title = _strip_heading_prefix(raw)
            current_heading = doc_title
        elif lvl in (2, 3):
            flush()
            section_name = _strip_heading_prefix(raw)
            # Prepend doc title so every chunk carries the company/document context
            current_heading = f"{doc_title} — {section_name}" if doc_title else section_name
        else:
            body_lines.append(raw)

    flush()
    return sections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_all_chunks() -> list[Chunk]:
    """
    Ingest every document from every namespace and return flat list of Chunks.

    Strategy
    --------
    * Section-level split (H2/H3 boundaries) — preserves tables + bullets together.
    * Heading prepended into chunk text for richer embedding.
    * Sliding-window fallback for oversized sections (heading on every window).
    """
    all_chunks: list[Chunk] = []

    for namespace, folder in DOCUMENT_NAMESPACES.items():
        if not folder.exists():
            continue
        for md_file in sorted(folder.glob("*.md")):
            rel_path = str(md_file.relative_to(md_file.parent.parent.parent))
            sections = _load_sections(md_file)

            chunk_idx = 0
            for heading, body in sections:
                # Prepend heading into text for embedding context
                full_text = f"{heading}\n\n{body}" if heading else body
                words = full_text.split()

                if len(words) <= CHUNK_SIZE:
                    all_chunks.append(
                        Chunk(
                            text=full_text,
                            namespace=namespace,
                            source_file=rel_path,
                            section=heading,
                            chunk_index=chunk_idx,
                        )
                    )
                    chunk_idx += 1
                else:
                    for window_text in _sliding_window(heading, body, CHUNK_SIZE, CHUNK_OVERLAP):
                        all_chunks.append(
                            Chunk(
                                text=window_text,
                                namespace=namespace,
                                source_file=rel_path,
                                section=heading,
                                chunk_index=chunk_idx,
                            )
                        )
                        chunk_idx += 1

    return all_chunks
