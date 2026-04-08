"""
RAG query engine.

Pipeline
--------
1. Classify the user's query to detect the likely namespace(s).
2. Embed the query with the same model used at index time.
3. Retrieve top-K chunks (using per-namespace index when possible).
4. Deduplicate and trim context to fit within the LLM context window.
5. Call the LLM with a structured prompt.
6. Return the answer + source citations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI

from app.core.config import (
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_TEMPERATURE,
    OPENAI_API_KEY,
    SCORE_THRESHOLD,
    TOP_K,
)
from app.core.embeddings import embed_query, _use_gemini

import os as _os
_OLLAMA_BASE_URL: str = _os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_LLM_MODEL: str = _os.getenv("OLLAMA_LLM_MODEL", "")
_GEMINI_API_KEY: str = _os.getenv("GEMINI_API_KEY", "")
_GEMINI_LLM_MODEL: str = _os.getenv("GEMINI_LLM_MODEL", "gemini-2.5-flash")
from app.core.embeddings import embed_query
from app.core.ingestion import Chunk
from app.core.vector_store import VectorStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    answer: str
    sources: list[str]                       # citation strings
    retrieved_chunks: list[tuple[Chunk, float]] = field(default_factory=list)
    namespace_used: Optional[str] = None


# ---------------------------------------------------------------------------
# Simple keyword-based namespace classifier
# ---------------------------------------------------------------------------

_NS_KEYWORDS: dict[str, list[str]] = {
    "stock_recommendations": [
        "recommendation", "buy", "sell", "hold", "target price",
        "upside", "rating", "analyst", "research report",
        "bbl", "kbank", "ptt", "delta",
    ],
    "company_profiles": [
        "company", "profile", "market cap", "sector", "employees",
        "founded", "headquarters", "npl", "roe", "business",
        "bangkok bank", "kasikornbank", "gulf", "pttep", "banpu", "scb", "ktb",
    ],
    "market_reports": [
        "market report", "set index", "foreign fund", "foreign flow",
        "net buy", "net sell", "top gainer", "top loser",
        "market outlook", "cpi", "inflation", "economy",
        "march 2026", "daily report",
    ],
    "regulations": [
        "rule", "regulation", "trading hour", "circuit breaker", "tick size",
        "settlement", "short selling", "lot size", "sec", "order type",
        "open auction", "pre-open", "morning session", "afternoon session",
        "trading session", "lunch break", "t+2",
    ],
}


def _detect_namespace(query: str) -> Optional[str]:
    """Return the most probable namespace for *query*, or None for global."""
    q = query.lower()
    scores: dict[str, int] = {ns: 0 for ns in _NS_KEYWORDS}
    for ns, keywords in _NS_KEYWORDS.items():
        for kw in keywords:
            if kw in q:
                scores[ns] += 1
    best_ns = max(scores, key=lambda k: scores[k])
    return best_ns if scores[best_ns] > 0 else None


_GREETING_PATTERNS = re.compile(
    r"^\s*("
    r"สวัสดี|หวัดดี|ดีครับ|ดีค่ะ|ขอบคุณ|ขอบใจ|thank(s| you)|hello|hi\b|hey\b|"
    r"good (morning|afternoon|evening)|greetings|howdy|yo\b"
    r")[ค่ะครับๆ!?.]*\s*$",
    re.IGNORECASE,
)


def _is_greeting(text: str) -> bool:
    """Return True if the input is purely a social greeting with no question."""
    return bool(_GREETING_PATTERNS.match(text.strip()))


def _detect_language(text: str) -> str:
    """Return 'th' if text contains Thai characters, else 'en'."""
    for ch in text:
        if '\u0e01' <= ch <= '\u0e5b':
            return "th"
    return "en"


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

_MAX_CONTEXT_WORDS = 1800   # conservative limit for gpt-4o-mini 8k context


def _build_context(chunks_with_scores: list[tuple[Chunk, float]]) -> str:
    """
    Deduplicate chunks by source file + section and build a numbered context
    block, stopping before exceeding the word budget.
    """
    seen: set[str] = set()
    selected: list[tuple[Chunk, float]] = []
    for chunk, score in chunks_with_scores:
        key = f"{chunk.source_file}|{chunk.section}|{chunk.chunk_index}"
        if key not in seen:
            seen.add(key)
            selected.append((chunk, score))

    context_parts: list[str] = []
    total_words = 0
    for i, (chunk, _) in enumerate(selected, start=1):
        words = chunk.text.split()
        if total_words + len(words) > _MAX_CONTEXT_WORDS:
            break
        context_parts.append(
            f"[{i}] Source: {chunk.citation}\n{chunk.text}"
        )
        total_words += len(words)

    return "\n\n".join(context_parts)


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a senior financial research assistant for Thai Securities Co., Ltd.
You answer questions about Thai securities documents — stock research reports, company profiles, market reports, and trading regulations.

## CRITICAL LANGUAGE RULE (HIGHEST PRIORITY)
You MUST reply in the SAME language the user used.
- If the user writes in Thai (ภาษาไทย) → You MUST answer entirely in Thai.
- If the user writes in English → You MUST answer entirely in English.
- NEVER mix languages. If the question is in Thai, every sentence of your answer must be in Thai (except proper nouns, stock tickers, and financial terms like THB, P/E, ROE).
- **NEVER output Chinese characters (中文).** You are NOT a Chinese assistant. Do NOT use 收入, 净利润, 每股收益, 市盈率, or ANY Chinese text.
- When writing tables in Thai, use Thai labels: รายได้ดอกเบี้ยสุทธิ, กำไรสุทธิ, กำไรต่อหุ้น (EPS), อัตราส่วนราคาต่อกำไร (P/E), อัตราส่วนราคาต่อมูลค่าทางบัญชี (P/BV), อัตราเงินปันผลตอบแทน, อัตราผลตอบแทนต่อส่วนผู้ถือหุ้น (ROE), อัตราส่วนหนี้เสีย (NPL Ratio).

## Behaviour rules

### 1 — Greetings and small talk
If the user greets you (e.g. "hello", "สวัสดี", "hi", "thanks") or sends a social message with no financial question, respond warmly and briefly, then remind them of your scope. Example:
"สวัสดีค่ะ! ฉันช่วยตอบคำถามเกี่ยวกับข้อมูลตลาดหุ้นไทยจากเอกสารที่ให้มาได้ เช่น ราคาเป้าหมาย คำแนะนำการลงทุน และกฎระเบียบการซื้อขาย"
Do NOT call this a "small talk" message or explain your reasoning.

### 2 — In-scope questions (answer found in documents)
- Answer using ONLY the provided context passages. Do not use outside knowledge.
- **Give a comprehensive, detailed answer** — include all relevant data from the context, not just the minimum.
- Cite every factual claim with the source number [1], [2], … exactly as given.
- Format numbers and percentages consistently (e.g. THB 42.00, +15.1%).

#### Formatting guidelines:
- Start with a **direct answer** to the question in the first sentence.
- Then expand with **supporting details** from the context: related financial metrics, key ratios, analyst opinion, risks, etc.
- Use **Markdown formatting** for readability:
  - Use **bold** for key numbers and names
  - Use bullet points (- ) for listing multiple items
  - Use tables (| col | col |) when comparing data across periods or stocks
  - Use headings (##, ###) to organize long answers
- Aim for **3–8 sentences minimum** for simple questions, and more for complex ones.
- Always end with a brief note about the source of data if relevant.

### 3 — Out-of-scope or insufficient evidence
If the provided context does not contain enough information to answer the question, do NOT fabricate or guess. Instead respond with a clear, polite message such as:
"ไม่พบข้อมูลเกี่ยวกับเรื่องนี้ในเอกสารที่ให้มา จากเอกสารที่มีอยู่ในระบบยังไม่สามารถยืนยันคำตอบนี้ได้"
or in English:
"I could not find information about this in the provided documents. Please consult additional sources."
Do NOT make up any figures, recommendations, or facts.
"""

_USER_PROMPT_TEMPLATE = """{lang_directive}

Context passages:
{context}

---
User question: {question}

Instructions:
1. Give a **comprehensive and detailed** answer — do not be brief.
2. Cite sources with [1], [2], … for every factual claim.
3. Include ALL relevant supporting data from context: financial metrics, ratios, growth rates, risks, analyst opinions, etc.
4. You MUST use Markdown tables when the context contains numerical data across years or multiple items. Example:

| Metric | 2024A | 2025E | 2026E |
|--------|-------|-------|-------|
| Revenue | 100 | 110 | 120 |

5. Also use **bold**, bullet points (- ), and headings (##) for readability.
6. If the context is insufficient, say so clearly without fabricating.

Remember: {lang_reminder}

Answer:"""


# ---------------------------------------------------------------------------
# Rule-based financial data extractor (used as LLM fallback)
# ---------------------------------------------------------------------------

def _extract_financial_data(question: str, context: str) -> str:
    """
    Extract structured financial data from context using regex patterns.
    Returns a formatted answer string, or empty string if nothing matched.
    """
    lines = context.splitlines()

    # ── Investment recommendation / rating ─────────────────────────────
    if any(kw in question for kw in ["recommendation", "rating", "buy", "sell", "hold"]):
        results = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # Look for table rows with BUY/SELL/HOLD
            m = re.search(r"\*{0,2}(BUY|SELL|HOLD)\*{0,2}", line, re.IGNORECASE)
            if m:
                # Try to grab target price and current price from same row
                prices = re.findall(r"THB\s*[\d,]+\.?\d*", line)
                upside = re.search(r"[+-][\d.]+%", line)
                # Find source from nearby [N] Source: line
                source = ""
                for j in range(max(0, i - 10), i):
                    sm = re.match(r"\[(\d+)\] Source: (.+)", lines[j])
                    if sm:
                        source = sm.group(2).split("›")[-1].strip()
                entry = f"**{m.group(1)}**"
                if len(prices) >= 2:
                    entry += f" — Target: {prices[0]}, Current: {prices[1]}"
                elif prices:
                    entry += f" — {prices[0]}"
                if upside:
                    entry += f" (Upside: {upside.group()})"
                if source:
                    entry += f"\n  *Source: {source}*"
                results.append(entry)
            i += 1
        if results:
            return "**Investment Ratings found:**\n\n" + "\n\n".join(results)

    # ── Target price ────────────────────────────────────────────────────
    if any(kw in question for kw in ["target price", "target"]):
        results = []
        for line in lines:
            if re.search(r"target\s*price", line, re.IGNORECASE):
                prices = re.findall(r"THB\s*[\d,]+\.?\d*", line)
                if prices:
                    results.append(f"Target Price: **{prices[0]}**")
        if results:
            return "\n".join(results[:4])

    # ── P/E ratio ────────────────────────────────────────────────────────
    if any(kw in question for kw in ["p/e", "pe ratio", "price to earnings"]):
        results = []
        for i, line in enumerate(lines):
            if re.search(r"P/E", line, re.IGNORECASE):
                # Table row: find year and P/E value
                values = re.findall(r"[\d.]+", line)
                if values:
                    # Find source from preceding [N] Source: line
                    src = next(
                        (lines[j].split("Source:")[-1].strip()
                         for j in range(max(0, i - 15), i)
                         if "Source:" in lines[j]),
                        ""
                    )
                    entry = f"P/E ratio row: `{line.strip()}`"
                    if src:
                        entry += f"\n  *from {src.split('›')[-1].strip()}*"
                    results.append(entry)
        if results:
            return "\n\n".join(results[:3])

    # ── Gainers / losers ────────────────────────────────────────────────
    if any(kw in question for kw in ["gainer", "loser", "top gain", "top los"]):
        want_gainers = "loser" not in question
        want_losers = "loser" in question

        results: list[str] = []
        capture = False

        for line in lines:
            # Check both the raw line and the section name after › in Source headers
            # e.g. "[11] Source: ...market_report.md › Top Gainers"
            section_from_source = ""
            source_match = re.match(r"\[\d+\]\s*Source:[^›]+›\s*(.+)", line)
            if source_match:
                section_from_source = source_match.group(1).strip()

            search_target = section_from_source or line

            heading_match = re.search(r"top\s+(gainer|loser)", search_target, re.IGNORECASE)
            if heading_match:
                kind = heading_match.group(1).lower()
                if (kind == "gainer" and want_gainers) or (kind == "loser" and want_losers):
                    capture = True
                    results.append(f"\n**Top {kind.capitalize()}s:**")
                else:
                    capture = False
                continue

            if capture:
                stripped = line.strip()
                if re.match(r"\d+\.", stripped):          # "1. **DELTA** ..."
                    results.append(stripped)
                elif stripped.startswith("[") or stripped.startswith("##") or stripped == "---":
                    capture = False

        if results:
            return "\n".join(r for r in results if r.strip())

    # ── Circuit breaker / trading rules ─────────────────────────────────
    if any(kw in question for kw in ["circuit breaker", "halt", "suspend", "trading halt"]):
        results = []
        capture = False
        for line in lines:
            if re.search(r"circuit\s*breaker|market.wide", line, re.IGNORECASE):
                capture = True
            if capture and "|" in line and re.search(r"%|halt|suspend", line, re.IGNORECASE):
                results.append(line.strip())
            elif capture and line.strip().startswith("##"):
                capture = False
        if results:
            header = "| SET Index Drop | Action |\n|---|---|"
            rows = [r for r in results if "---" not in r]
            return "**Market-Wide Circuit Breaker Rules:**\n\n" + header + "\n" + "\n".join(rows[:5])

    # ── Tick size ────────────────────────────────────────────────────────
    if any(kw in question for kw in ["tick", "tick size"]):
        # Extract price from question
        price_match = re.search(r"thb\s*([\d,]+)|(\d+)\s*thb|([\d,]+)\s*baht", question)
        price_val = None
        if price_match:
            raw = next(g for g in price_match.groups() if g)
            price_val = float(raw.replace(",", ""))

        results = []
        for line in lines:
            if "|" in line and re.search(r"\d+.*\d+\.\d+", line):
                results.append(line.strip())

        if price_val and results:
            for row in results:
                nums = re.findall(r"[\d.]+", row)
                if len(nums) >= 2:
                    try:
                        lo, hi = float(nums[0]), float(nums[1])
                        if lo <= price_val < hi:
                            return f"For a stock priced at THB {price_val:.0f}, the **tick size is THB {nums[-1]}**\n\n*(Price range: THB {lo} – {hi})*"
                    except ValueError:
                        pass
        if results:
            return "**Tick Size Table:**\n\n| Price Range (THB) | Tick Size |\n|---|---|\n" + "\n".join(results[:10])

    return ""

class RAGEngine:
    """
    Stateless query engine.  Requires a loaded VectorStore and an OpenAI key.
    """

    def __init__(self, vector_store: VectorStore) -> None:
        self._vs = vector_store
        # Ollama LLM (highest priority when configured)
        self._ollama_llm: bool = bool(_OLLAMA_LLM_MODEL)
        # Gemini client (secondary)
        if _GEMINI_API_KEY and not self._ollama_llm:
            from google import genai
            self._gemini = genai.Client(
                api_key=_GEMINI_API_KEY,
                http_options={"api_version": "v1beta"},
            )
        else:
            self._gemini = None
        # OpenAI client (tertiary)
        self._client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and not _GEMINI_API_KEY and not self._ollama_llm else None

    # ------------------------------------------------------------------

    def query(self, question: str, top_k: int = TOP_K, chat_id: Optional[str] = None) -> QueryResult:
        """
        End-to-end RAG pipeline.

        1. Classify namespace
        2. Embed question
        3. Retrieve chunks  (+uploaded docs if chat_id given)
        4. Filter low-confidence chunks
        5. Build context
        6. Generate answer
        """
        # Step 0 — greeting detection (skip retrieval entirely)
        if _is_greeting(question):
            lang = _detect_language(question)
            if lang == "th":
                greeting_resp = (
                    "สวัสดีค่ะ! ฉันเป็นผู้ช่วยตอบคำถามเกี่ยวกับข้อมูลตลาดหุ้นไทย "
                    "สามารถช่วยตอบเรื่องคำแนะนำการลงทุน ราคาเป้าหมาย ผลการดำเนินงานของบริษัท "
                    "รายงานตลาด และกฎระเบียบการซื้อขายได้ค่ะ มีอะไรให้ช่วยไหมคะ?"
                )
            else:
                greeting_resp = (
                    "Hello! I'm a research assistant for Thai Securities. "
                    "I can help with stock recommendations, target prices, company profiles, "
                    "market reports, and trading regulations. How can I help you?"
                )
            return QueryResult(
                answer=greeting_resp,
                sources=[],
                retrieved_chunks=[],
                namespace_used=None,
            )

        # Step 1 — classify
        namespace = _detect_namespace(question)
        logger.debug("Detected namespace: %s", namespace)

        # Step 2 — embed
        q_vec = embed_query(question)

        # Step 3 — retrieve
        # For small namespaces (≤ 20 chunks), retrieve everything so narrow
        # sections like "Top Gainers" are never missed by approximate search.
        ns_size = len(self._vs._ns_chunks.get(namespace or "", []))
        effective_k = ns_size if 0 < ns_size <= 20 else top_k
        results = self._vs.search(q_vec, top_k=effective_k, namespace=namespace, query_text=question)

        # If namespace search returns few results, fall back to global
        if len(results) < 2 and namespace:
            logger.debug("Namespace search insufficient; falling back to global.")
            results = self._vs.search(q_vec, top_k=top_k, namespace=None, query_text=question)
            namespace = None

        # Step 4 — filter by score threshold (inner-product cosine similarity)
        filtered = [(c, s) for c, s in results if s >= (1.0 - SCORE_THRESHOLD)]
        if not filtered:
            filtered = results  # keep all if all below threshold

        # Step 4.5 — merge uploaded-file results for this chat session
        if chat_id:
            from app.core.ingestion import Chunk as _IngChunk
            from app.services.chat_store_service import search as _chat_search
            for text, source, score in _chat_search(chat_id, q_vec, top_k=top_k):
                fake = _IngChunk(
                    text=text,
                    namespace="uploaded",
                    source_file=source,
                    section="Uploaded File",
                    chunk_index=0,
                )
                filtered.append((fake, score))
            # Keep best results at the top
            filtered.sort(key=lambda x: -x[1])

        # Step 5 — build context
        context = _build_context(filtered)
        if not context.strip():
            return QueryResult(
                answer="I could not find relevant information in the knowledge base.",
                sources=[],
                retrieved_chunks=filtered,
                namespace_used=namespace,
            )

        # Step 6 — generate
        answer = self._generate(question, context)
        # Strip any "[N] Source: ..." lines the LLM may echo from context
        answer = re.sub(r"^\[\d+\]\s*Source:.*$", "", answer, flags=re.MULTILINE).strip()

        # Only show sources that the LLM actually cited in its answer
        sources = self._extract_cited_sources(answer, filtered)

        return QueryResult(
            answer=answer,
            sources=sources,
            retrieved_chunks=filtered,
            namespace_used=namespace,
        )

    # ------------------------------------------------------------------

    def _generate(self, question: str, context: str) -> str:
        # ── Ollama (priority 0) ──────────────────────────────────────────────
        if self._ollama_llm:
            import urllib.request
            import json as _json
            lang = _detect_language(question)
            if lang == "th":
                lang_directive = "## คำสั่งบังคับ: ตอบเป็นภาษาไทยทั้งหมดเท่านั้น ห้ามตอบเป็นภาษาอังกฤษหรือภาษาจีน"
                lang_reminder = "ตอบเป็นภาษาไทยเท่านั้น (Thai only)"
                sys_lang_prefix = "CRITICAL INSTRUCTION: The user is writing in Thai. You MUST answer ENTIRELY in Thai (ภาษาไทย). Do NOT answer in English or Chinese.\n\n"
            else:
                lang_directive = "## MANDATORY: Answer entirely in English. Do NOT answer in Thai or Chinese."
                lang_reminder = "Answer in English only"
                sys_lang_prefix = "CRITICAL INSTRUCTION: The user is writing in English. You MUST answer ENTIRELY in English. Do NOT answer in Thai or Chinese.\n\n"
            prompt = _USER_PROMPT_TEMPLATE.format(context=context, question=question, lang_directive=lang_directive, lang_reminder=lang_reminder)
            messages = [
                {"role": "system", "content": sys_lang_prefix + _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            body = _json.dumps({
                "model": _OLLAMA_LLM_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.0},
            }).encode()
            req = urllib.request.Request(
                f"{_OLLAMA_BASE_URL}/api/chat",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=600) as resp:
                    data = _json.loads(resp.read())
                return data["message"]["content"].strip()
            except Exception as exc:
                logger.error("Ollama LLM call failed: %s", exc)
                return self._fallback_answer(question, context)

        # ── Gemini (priority 1) ──────────────────────────────────────────────
        if self._gemini is not None:
            import time as _time
            lang = _detect_language(question)
            if lang == "th":
                lang_directive = "## คำสั่งบังคับ: ตอบเป็นภาษาไทยทั้งหมดเท่านั้น ห้ามตอบเป็นภาษาอังกฤษหรือภาษาจีน"
                lang_reminder = "ตอบเป็นภาษาไทยเท่านั้น (Thai only)"
                sys_lang_prefix = "CRITICAL INSTRUCTION: The user is writing in Thai. You MUST answer ENTIRELY in Thai (ภาษาไทย). Do NOT answer in English or Chinese.\n\n"
            else:
                lang_directive = "## MANDATORY: Answer entirely in English. Do NOT answer in Thai or Chinese."
                lang_reminder = "Answer in English only"
                sys_lang_prefix = "CRITICAL INSTRUCTION: The user is writing in English. You MUST answer ENTIRELY in English. Do NOT answer in Thai or Chinese.\n\n"
            prompt = _USER_PROMPT_TEMPLATE.format(context=context, question=question, lang_directive=lang_directive, lang_reminder=lang_reminder)
            full_prompt = sys_lang_prefix + _SYSTEM_PROMPT + "\n\n" + prompt
            for attempt in range(3):
                try:
                    response = self._gemini.models.generate_content(
                        model=_GEMINI_LLM_MODEL,
                        contents=full_prompt,
                    )
                    return response.text.strip()
                except Exception as exc:
                    msg = str(exc)
                    if ("503" in msg or "UNAVAILABLE" in msg) and attempt < 2:
                        wait = 20 * (attempt + 1)
                        logger.warning("Gemini LLM unavailable, retry %d/3 in %ds", attempt + 1, wait)
                        _time.sleep(wait)
                    else:
                        logger.error("Gemini LLM call failed: %s", exc)
                        return self._fallback_answer(question, context)

        # ── OpenAI (fallback) ───────────────────────────────────────────
        if self._client is None:
            return self._fallback_answer(question, context)

        try:
            lang = _detect_language(question)
            if lang == "th":
                lang_directive = "## คำสั่งบังคับ: ตอบเป็นภาษาไทยทั้งหมดเท่านั้น ห้ามตอบเป็นภาษาอังกฤษหรือภาษาจีน"
                lang_reminder = "ตอบเป็นภาษาไทยเท่านั้น (Thai only)"
            else:
                lang_directive = "## MANDATORY: Answer entirely in English. Do NOT answer in Thai or Chinese."
                lang_reminder = "Answer in English only"
            response = self._client.chat.completions.create(
                model=LLM_MODEL,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _USER_PROMPT_TEMPLATE.format(
                            context=context, question=question,
                            lang_directive=lang_directive, lang_reminder=lang_reminder,
                        ),
                    },
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("LLM call failed: %s", exc)
            return self._fallback_answer(question, context)

    @staticmethod
    def _fallback_answer(question: str, context: str) -> str:
        """
        Rule-based extraction fallback when no LLM is available.

        Attempts to extract structured financial data (ratings, prices, metrics)
        directly from retrieved passages to give a useful answer without an LLM.
        Falls back to showing all relevant passages if extraction yields nothing.
        """
        if not context:
            return (
                "ไม่พบข้อมูลเกี่ยวกับเรื่องนี้ในเอกสารที่ให้มา "
                "จากเอกสารที่มีอยู่ในระบบยังไม่สามารถยืนยันคำตอบนี้ได้"
            )

        q_lower = question.lower()

        # ── Try structured extraction first ────────────────────────────
        extracted = _extract_financial_data(q_lower, context)
        if extracted:
            footer = "> *Add GEMINI_API_KEY or OPENAI_API_KEY to .env for full AI-generated answers.*"
            if footer not in extracted:
                extracted += f"\n\n{footer}"
            return extracted

        # ── Out-of-scope detection: if passages look irrelevant, say so ──
        # Score relevance: count how many question keywords appear in context
        q_words = set(re.findall(r'[a-zA-Z0-9฀-๿]+', q_lower))
        ctx_lower = context.lower()
        overlap = sum(1 for w in q_words if len(w) > 2 and w in ctx_lower)
        if len(q_words) > 2 and overlap == 0:
            return (
                "ไม่พบข้อมูลเกี่ยวกับเรื่องนี้ในเอกสารที่ให้มา "
                "จากเอกสารที่มีอยู่ในระบบยังไม่สามารถยืนยันคำตอบนี้ได้"
            )

        # ── Fallback: show all retrieved passages (not just the first) ──
        passages = [p.strip() for p in context.split("\n\n") if p.strip()]
        shown = "\n\n---\n\n".join(passages[:3])
        return (
            f"{shown}\n\n"
            "> *Add GEMINI_API_KEY or OPENAI_API_KEY to .env for full AI-generated answers.*"
        )

    @staticmethod
    def _extract_sources(results: list[tuple[Chunk, float]]) -> list[str]:
        seen: set[str] = set()
        sources: list[str] = []
        for chunk, _ in results:
            # Deduplicate by source file so the same document doesn't appear multiple times
            key = chunk.source_file
            if key not in seen:
                seen.add(key)
                sources.append(chunk.citation)
        return sources

    @staticmethod
    def _extract_cited_sources(answer: str, results: list[tuple[Chunk, float]]) -> list[str]:
        """Return only sources that the LLM actually cited as [1], [2], … in *answer*.
        Falls back to all unique sources if no citations are detected."""
        # Build ordered list of chunks as numbered by _build_context
        seen_ctx: set[str] = set()
        ordered: list[Chunk] = []
        for chunk, _ in results:
            key = f"{chunk.source_file}|{chunk.section}|{chunk.chunk_index}"
            if key not in seen_ctx:
                seen_ctx.add(key)
                ordered.append(chunk)

        # Find which [N] numbers appear in the answer
        cited_nums = {int(m) for m in re.findall(r"\[(\d+)\]", answer)}

        if not cited_nums:
            # LLM didn't cite anything — fall back to all unique sources
            seen: set[str] = set()
            sources: list[str] = []
            for c in ordered:
                if c.source_file not in seen:
                    seen.add(c.source_file)
                    sources.append(c.citation)
            return sources

        # Collect cited sources, deduplicated by citation (file + section)
        seen_cites: set[str] = set()
        sources: list[str] = []
        for idx, chunk in enumerate(ordered, start=1):
            if idx in cited_nums and chunk.citation not in seen_cites:
                seen_cites.add(chunk.citation)
                sources.append(chunk.citation)
        return sources
