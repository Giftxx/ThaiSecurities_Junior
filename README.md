# Thai Securities Q&A — Intelligent Research Assistant

> **Submission by:** Paewpairee  
> **Position:** Junior AI Engineer  
> **Date:** April 2026

ระบบถาม-ตอบอัจฉริยะสำหรับข้อมูลตลาดหุ้นไทย ใช้ RAG (Retrieval-Augmented Generation) รันบนเครื่อง **100% แบบ local** ผ่าน **Ollama** — ไม่ต้องใช้ API key ภายนอก, ไม่ต้องเชื่อมอินเทอร์เน็ตตอนใช้งาน

---

## สิ่งที่ระบบใช้ (Tech Stack)

| ส่วน | เทคโนโลยี | รายละเอียด |
|------|-----------|-----------|
| **LLM** | Ollama — `qwen2.5:7b` | โมเดลภาษา 7B สำหรับสร้างคำตอบ (4.7 GB) |
| **Embedding** | Ollama — `bge-m3` | สร้าง vector 1024 มิติ สำหรับค้นหาเอกสาร |
| **Vector DB** | FAISS (faiss-cpu) | HNSW per-namespace + IVF-flat global index |
| **Keyword Search** | BM25 (rank-bm25) | ค้นหาด้วย keyword แบบ exact match |
| **Hybrid Search** | RRF (Reciprocal Rank Fusion) | รวมผล Vector 60% + BM25 40% |
| **Backend** | FastAPI + Uvicorn | REST API server, port 8000 |
| **Frontend** | HTML / CSS / JavaScript | Web UI ดูแบบ Chat interface |
| **ภาษา** | Python 3.11+ | จัดการ dependency ด้วย uv |

---

## 🚀 วิธีติดตั้งและรันโปรเจค (ทีละขั้นตอน)

### ขั้นตอนที่ 0 — ติดตั้งโปรแกรมที่ต้องใช้

#### 0.1 ติดตั้ง Python

1. เปิดเว็บ https://www.python.org/downloads/
2. กดปุ่ม **Download Python** (เวอร์ชัน 3.11 ขึ้นไป)
3. **สำคัญมาก:** ตอนติดตั้ง ให้ **ติ๊กช่อง "Add Python to PATH"** ก่อนกด Install
4. ติดตั้งเสร็จแล้ว เปิด **Terminal** (Windows: กด `Win+R` พิมพ์ `cmd` แล้ว Enter) แล้วพิมพ์:
   ```
   python --version
   ```
   ถ้าขึ้นเลข version แสดงว่าติดตั้งสำเร็จ

#### 0.2 ติดตั้ง uv (ตัวจัดการ Python packages)

เปิด Terminal แล้วพิมพ์:

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

ตรวจสอบว่าติดตั้งสำเร็จ:
```
uv --version
```

#### 0.3 ติดตั้ง Ollama (สำหรับรัน AI model บนเครื่อง)

1. เปิดเว็บ https://ollama.com/download
2. กดดาวน์โหลดตาม OS ของคุณ (Windows / macOS / Linux)
3. ติดตั้งตามขั้นตอนที่หน้าจอแสดง
4. ตรวจสอบว่าติดตั้งสำเร็จ:
   ```
   ollama --version
   ```

#### 0.4 ติดตั้ง Git

1. เปิดเว็บ https://git-scm.com/downloads
2. กดดาวน์โหลดตาม OS ของคุณ
3. ติดตั้งตามขั้นตอนที่หน้าจอแสดง (กด Next ไปเรื่อยๆ ใช้ค่า default ได้)

---

### ขั้นตอนที่ 1 — Clone โปรเจคจาก GitHub

เปิด Terminal แล้วพิมพ์:

```bash
git clone https://github.com/Giftxx/ThaiSecurities_Junior.git
cd ysth-junior-ai-engineer-test-mar2026
```

---

### ขั้นตอนที่ 2 — ดาวน์โหลด AI Models ผ่าน Ollama

**เปิด Ollama ก่อน** (Windows: เปิดแอป Ollama จาก Start Menu ให้รันอยู่เบื้องหลัง)

จากนั้นเปิด Terminal อีกตัว แล้วพิมพ์คำสั่งนี้ **ทีละบรรทัด**:

```bash
ollama pull bge-m3
```
> รอโหลดเสร็จ (~1.7 GB) — นี่คือ **Embedding Model** ใช้แปลงข้อความเป็น vector สำหรับค้นหา

```bash
ollama pull qwen2.5:7b
```
> รอโหลดเสร็จ (~4.7 GB) — นี่คือ **LLM Model** ใช้อ่านเอกสารแล้วสร้างคำตอบ

ตรวจสอบว่าโมเดลโหลดครบ:
```bash
ollama list
```
ต้องเห็น **bge-m3** และ **qwen2.5:7b** ในรายการ

---

### ขั้นตอนที่ 3 — ติดตั้ง Python Dependencies

เปิด Terminal ที่โฟลเดอร์โปรเจค แล้วพิมพ์:

```bash
uv sync
```

คำสั่งนี้จะ:
- สร้าง virtual environment (`.venv/`)
- ติดตั้ง library ทั้งหมดที่โปรเจคต้องใช้

> **ถ้าไม่มี uv** สามารถใช้ pip แทน:
> ```bash
> python -m venv .venv
> .venv\Scripts\activate      # Windows
> # source .venv/bin/activate  # macOS/Linux
> pip install -r requirements.txt
> ```

---

### ขั้นตอนที่ 4 — สร้างไฟล์ .env

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

> ไฟล์ `.env.example` มีค่าถูกต้องพร้อมใช้แล้ว (Ollama + bge-m3 + qwen2.5:7b) — **ไม่ต้องแก้ไขอะไรเพิ่ม**

---

### ขั้นตอนที่ 5 — สร้าง FAISS Index (ต้องทำครั้งแรกครั้งเดียว)

```bash
uv run python scripts/build_index.py
```

> **ถ้าไม่มี uv:** `.venv\Scripts\python.exe scripts\build_index.py`

จะเห็น output ประมาณนี้:
```
Loading documents …
Total chunks: 74
  stock_recommendations        28 chunks
  company_profiles             18 chunks
  market_reports               18 chunks
  regulations                  10 chunks
✅ Index built and saved successfully.
```

ระบบจะสร้างโฟลเดอร์ `vector_store/` เก็บ index ไว้ใช้ซ้ำได้เลย

---

### ขั้นตอนที่ 6 — เริ่มต้นเซิร์ฟเวอร์

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **ถ้าไม่มี uv:** `.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000`

จะเห็น:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

### ขั้นตอนที่ 7 — เปิดใช้งาน

เปิด browser แล้วไปที่:

```
http://localhost:8000
```

จะเจอหน้า Chat UI ที่สามารถพิมพ์คำถามเกี่ยวกับหุ้นไทยได้เลย เช่น:
- "คำแนะนำสำหรับหุ้น PTT?"
- "What is the P/E ratio of Bangkok Bank?"
- "เวลาซื้อขายหุ้นของ SET เป็นยังไง?"

> **หมายเหตุ:** คำถามแรกอาจใช้เวลาตอบนาน (~1-3 นาที) เพราะ Ollama ต้อง load โมเดลเข้า RAM ก่อน คำถามถัดไปจะเร็วขึ้น

---

## 📂 โครงสร้างโปรเจค

```
.
├── app/
│   ├── main.py                    # จุดเริ่มต้นแอป (import FastAPI app)
│   ├── api/
│   │   └── routes.py              # REST API endpoints (/query, /health, /upload, /namespaces)
│   ├── core/
│   │   ├── config.py              # อ่านค่าจาก .env
│   │   ├── ingestion.py           # โหลด Markdown → แบ่ง section-level chunks
│   │   ├── embeddings.py          # สร้าง vector ผ่าน Ollama bge-m3
│   │   ├── vector_store.py        # FAISS index + BM25 + hybrid RRF search
│   │   └── rag_engine.py          # RAG pipeline: ค้นหา → สร้าง prompt → เรียก LLM
│   └── services/
│       ├── index_service.py       # Singleton VectorStore lifecycle
│       └── chat_store_service.py  # In-memory store สำหรับไฟล์ที่ upload
├── ui/
│   ├── index.html                 # หน้าเว็บ Chat UI
│   ├── script.js                  # JavaScript logic
│   └── style.css                  # CSS styling
├── scripts/
│   └── build_index.py             # สร้าง FAISS index จากเอกสาร
├── data/                          # เอกสารต้นฉบับ (4 หมวด)
│   ├── stock_recommendations/     # รายงานวิเคราะห์หุ้น (BBL, DELTA, KBANK, PTT)
│   ├── company_profiles/          # ข้อมูลบริษัท (ธนาคาร, พลังงาน)
│   ├── market_reports/            # รายงานตลาดรายวัน
│   └── regulations/               # กฎระเบียบ SET
├── vector_store/                  # FAISS index (auto-generated, อยู่ใน .gitignore)
├── pyproject.toml                 # Python project config (ใช้กับ uv)
├── requirements.txt               # pip-compatible dependency list
├── .env.example                   # ตัวอย่างไฟล์ config
├── .env                           # ไฟล์ config จริง (อยู่ใน .gitignore)
└── README.md                      # ไฟล์นี้
```

---

## 🏗️ Architecture & แนวคิด

### ภาพรวม RAG Pipeline

```
คำถามผู้ใช้
    │
    ▼
[1] Greeting detection ─── ตรวจว่าเป็นคำทักทายหรือไม่
    │                       ถ้าใช่ → ตอบทักทายกลับ (ไม่ค้นหา)
    ▼
[2] Namespace classifier ── จัดหมวดคำถามจาก keyword
    │                       เช่น "PTT" + "buy" → stock_recommendations
    ▼
[3] Embed query ─────────── แปลงคำถามเป็น vector 1024 มิติ (bge-m3)
    │
    ▼
[4] Hybrid search ─────────
    │  ├─ FAISS HNSW (vector similarity, 60%)
    │  └─ BM25 (exact keyword match, 40%)
    │  └─ รวมผลด้วย Reciprocal Rank Fusion (RRF)
    ▼
[5] Context assembly ────── เรียงและจัดชิ้นเอกสาร ≤ 1800 words
    │                       ใส่เลข [1], [2], ... สำหรับอ้างอิง
    ▼
[6] LLM generation ──────── ส่ง prompt + context ให้ qwen2.5:7b
    │                       สร้างคำตอบพร้อม citation [1], [2]
    ▼
[7] Source extraction ───── ดึงเฉพาะ sources ที่ LLM อ้างอิงจริงในคำตอบ
    │
    ▼
ส่งคำตอบ + sources กลับให้ผู้ใช้
```

### Design Decisions

| การตัดสินใจ | เลือกใช้ | เหตุผล |
|------------|---------|--------|
| **Embedding** | Ollama `bge-m3` (1024-dim) | รัน local ฟรี, รองรับ multilingual (ไทย+อังกฤษ), คุณภาพสูง |
| **LLM** | Ollama `qwen2.5:7b` | รัน local ฟรี, รองรับภาษาไทยดี, ขนาดพอดีกับ RAM 8GB+ |
| **Vector Index** | FAISS HNSW per-namespace | O(log N) approximate nearest neighbor, เร็วมากสำหรับ corpus เล็ก |
| **Global Index** | FAISS IVF-flat | Fallback สำหรับคำถามข้าม namespace |
| **Keyword Search** | BM25 (rank-bm25) | จับ exact terms ได้ดี: ticker "PTT", rating "BUY", ราคา "42.00" |
| **Hybrid** | RRF 60/40 (vector/BM25) | Balance ระหว่าง semantic understanding กับ exact match |
| **Chunking** | Section-level (H2/H3) | เก็บตาราง + bullet list ไว้ด้วยกัน, prepend heading ทุก chunk |
| **Namespace routing** | Keyword classifier | Zero-latency pre-filter, fallback ไป global ถ้าไม่ match |
| **Frontend** | Vanilla HTML/JS/CSS | ไม่ต้องลง Node.js, ไม่มี build step, เรียบง่าย |
| **Backend** | FastAPI | Auto-docs, Pydantic validation, serve static files ได้ |

### Hybrid Search — ทำไมต้อง BM25 + Vector

เอกสารการเงินมีคำเฉพาะ exact ที่สำคัญมาก เช่น ชื่อหุ้น "PTT", rating "BUY", ราคา "THB 42.00" — BM25 จับคำเหล่านี้ได้แม่นยำ

ขณะเดียวกัน คำถามอาจใช้คำที่ความหมายใกล้เคียงแต่ไม่ตรง เช่น "recommendation" ≈ "investment rating" — Vector search จับ semantic ได้ดีกว่า

การรวมทั้งสองแบบด้วย RRF (k=60, α=0.60) ให้ผลลัพธ์ที่ดีกว่าใช้อย่างใดอย่างหนึ่ง

---

## 📡 API Endpoints

| Endpoint | Method | คำอธิบาย |
|----------|--------|---------|
| `/` | GET | Redirect ไป Web UI |
| `/health` | GET | ตรวจสถานะ server + index |
| `/namespaces` | GET | ดูหมวดเอกสารทั้งหมด |
| `/query` | POST | ถามคำถาม → รับคำตอบ |
| `/upload` | POST | อัปโหลดเอกสารเพิ่มเข้า chat session |
| `/upload/files` | GET | ดูไฟล์ที่ upload ใน session |
| `/upload/file` | DELETE | ลบไฟล์ที่ upload |
| `/admin/reindex` | POST | Rebuild index (ต้องใส่ X-Admin-Key header) |

**ตัวอย่างเรียก API:**

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "คำแนะนำหุ้น PTT?", "top_k": 5}'
```

**Response:**
```json
{
  "answer": "หุ้น PTT ได้รับคำแนะนำ **ซื้อ (BUY)** พร้อมราคาเป้าหมาย **THB 42.00** [1] ...",
  "sources": ["data/stock_recommendations/ptt_research_report.md › Investment Recommendation"],
  "namespace_used": "stock_recommendations",
  "latency_ms": 45200.5
}
```

---

## ⚙️ ตัวแปรใน .env

| ตัวแปร | ค่าที่ใช้ | คำอธิบาย |
|--------|----------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL ของ Ollama server |
| `OLLAMA_LLM_MODEL` | `qwen2.5:7b` | โมเดล LLM สำหรับสร้างคำตอบ |
| `OLLAMA_EMBEDDING_MODEL` | `bge-m3` | โมเดล Embedding สำหรับสร้าง vector |
| `OLLAMA_EMBEDDING_DIM` | `1024` | มิติของ embedding vector |

---

## สมมติฐานที่ใช้ (Assumptions)

1. **เอกสารเป็น Markdown (.md)** — ระบบ parse heading H1/H2/H3 เพื่อแบ่ง section
2. **เอกสารเป็นภาษาไทยและอังกฤษ** — ใช้ bge-m3 ที่รองรับ multilingual
3. **ผู้ใช้ถามทีละคำถาม (single-turn)** — ไม่มี conversation memory ข้ามคำถาม
4. **Corpus มีขนาดเล็ก** (~74 chunks จาก 8 เอกสาร) — ใช้ HNSW ที่ดีกับ corpus เล็ก
5. **รันบนเครื่อง local** — ไม่ต้องเชื่อมต่ออินเทอร์เน็ตตอนใช้งาน (ต้องใช้ตอนติดตั้ง)
6. **มี RAM ≥ 8 GB** — qwen2.5:7b ต้องใช้ RAM ~5-6 GB ตอน inference

---

## ⚠️ ข้อจำกัดของระบบ (Limitations)

1. **ความเร็ว CPU** — ถ้าไม่มี GPU, qwen2.5:7b ใช้เวลาตอบ ~30-120 วินาทีต่อคำถาม (ขึ้นกับ CPU)
2. **Single-turn only** — ไม่มี conversation memory, ทุกคำถามเป็นอิสระจากกัน
3. **ไฟล์ Upload อยู่ใน memory** — ถ้า restart server ไฟล์ที่ upload จะหายไป
4. **Corpus เล็ก** — มีแค่ 8 เอกสาร (74 chunks), ความแม่นยำจะเพิ่มขึ้นถ้ามีเอกสารมากขึ้น
5. **Keyword namespace classifier** — ใช้ keyword matching เท่านั้น, อาจจัดหมวดผิดสำหรับคำถามที่คลุมเครือ
6. **ไม่มี authentication** — ทุกคนที่เข้าถึง URL ได้สามารถใช้งานได้เลย

---

## 💡 แนวทางพัฒนาต่อในอนาคต (Future Improvements)

- **GPU acceleration** — ใช้ GPU กับ Ollama เพื่อลดเวลาตอบจากนาทีเหลือวินาที
- **Streaming response** — ส่งคำตอบกลับเป็น token stream (SSE) เพื่อแสดงผลแบบ real-time
- **Multi-turn conversation** — เก็บ history เพื่อให้ถามต่อเนื่องได้
- **Persistent upload storage** — เก็บไฟล์ที่ upload ลง disk ไม่หายเมื่อ restart
- **Cross-encoder re-ranking** — ใช้ cross-encoder เช่น ms-marco-MiniLM เพื่อ re-rank ผลลัพธ์ให้แม่นยำขึ้น
- **Auto-reindex** — ตรวจจับเมื่อเอกสารเปลี่ยนแปลงแล้ว rebuild index อัตโนมัติ
- **Authentication & rate limiting** — เพิ่ม JWT/API key สำหรับ production