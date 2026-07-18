# Docent — Backend

AI Document Teaching System backend. Upload a PDF, pick a learning goal, and the system produces a chapter roadmap, grounded Feynman-style lessons, 2-question quizzes, grounded Q&A, and progress tracking.

- **Framework:** FastAPI + Uvicorn
- **Database:** PostgreSQL 16 (source of truth for all structured data)
- **Vector store:** ChromaDB (embedded, local, file-based — no separate vector DB)
- **Embeddings:** local CPU model `all-MiniLM-L6-v2` (384-dim, runs via Chroma's ONNX default)
- **LLM:** Groq (OpenAI-compatible API)

## Requirements

- Python 3.11+
- PostgreSQL 16 running locally (already running, or set up your own)
- A Groq API key

## Setup

### 1. Clone and create venv

```bash
git clone <repo-url>
cd Docent
python -m venv venv
```

### 2. Activate and install dependencies

**Windows:**
```bash
venv\Scripts\activate
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Set up PostgreSQL

The app connects to a local PostgreSQL instance using the `postgres` superuser (password `root`) and a database named `docent`.

**Prerequisites:** PostgreSQL 16 installed and running locally on port `5432`.

**Create the database** — connect to Postgres as a superuser (e.g. via `psql -U postgres`) and run:

```sql
CREATE DATABASE docent;
```

The `docent` database must exist before running migrations. The app does NOT create users or the database itself — it only connects to what's already there.

> **Credentials:** The app uses `postgres` / `root` as configured in `.env` (`DATABASE_URL=postgresql+asyncpg://postgres:root@localhost:5432/docent`). Adjust `DATABASE_URL` if your local Postgres uses different credentials.

### 4. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Minimal `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:root@localhost:5432/docent
LLM_PROVIDER=groq
LLM_API_KEY=your_groq_api_key_here
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIM=384
CHROMA_PERSIST_DIR=./data/chroma
UPLOAD_DIR=./data/uploads
MAX_PDF_MB=50
MAX_PAGES=100
TRUNCATE_PAGES=50
```

### 5. Run database migrations

```bash
venv\Scripts\alembic.exe upgrade head
```

### 6. Start the server

```bash
python run.py
```

Or with uvicorn directly:

```bash
venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.
Swagger docs: `http://127.0.0.1:8000/docs`

## What the Backend Can Do

Docent is an **AI Document Teaching System**. You upload a PDF and the backend:

- **Ingests & understands documents** — parses PDF text (PyMuPDF), detects chapter headings by font size, strips headers/footers, de-hyphenates, and splits into 800-token chunks (tiktoken). Chunks are embedded with a local CPU model (`all-MiniLM-L6-v2`) and stored in ChromaDB for semantic search, with metadata in PostgreSQL.
- **Generates a chapter roadmap** — the LLM reads the first portion of the document and produces an ordered list of chapters with summaries.
- **Teaches with Feynman-style lessons** — for any chapter and learning goal (`exam` / `understand` / `implement` / `research`), it generates a plain-language explanation, a real-world analogy, key points, and verbatim source citations (page + chunk). Lessons are cached per (chapter, goal).
- **Quizzes the learner** — every lesson gets 2 MCQs with document-grounded distractors. A separate "final quiz" produces 10 mixed questions from weak-area chapters.
- **Answers questions grounded in the document** — `/ask` embeds your question, retrieves the top-k relevant chunks from ChromaDB, and the LLM answers with citations. Falls back to keyword search if vectors are missing. Never hallucinates outside the document.
- **Tracks progress** — scores quiz attempts, marks lessons complete, computes weak areas (chapters averaging <60%), and reports overall progress.
- **Lists all ingested documents** — see every uploaded PDF and its status at a glance.

Edge cases handled: PDFs <2 pages rejected, scanned PDFs (too little text) rejected, PDFs >100 pages truncated to first 50, concurrent uploads rate-limited (max 2 per IP), embedding failures degrade to keyword fallback, LLM JSON errors retried with repair prompts.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/documents/upload` | Upload a PDF (max 50MB), starts async ingestion |
| `GET` | `/api/documents` | List all ingested documents (id, status, etc.) |
| `GET` | `/api/documents/{id}` | Poll document ingestion status |
| `GET` | `/api/documents/{id}/roadmap` | Get generated chapter roadmap |
| `GET` | `/api/documents/{id}/lessons/{chapterId}?goal=` | Get a lesson + quiz for a chapter (goal: `exam`/`understand`/`implement`/`research`) |
| `POST` | `/api/documents/{id}/ask` | Ask a grounded question about the document |
| `POST` | `/api/documents/{id}/lessons/{lessonId}/quiz/submit` | Submit quiz answers, get score + weak areas + next lesson |
| `GET` | `/api/documents/{id}/progress` | Get completed lessons, scores, weak areas, overall progress |
| `POST` | `/api/documents/{id}/quiz/final` | Generate 10 mixed MCQs from weak-area chapters |

## How it works

1. **Upload** → PDF saved, `processing` row created, ingestion launched as a background task
2. **Ingestion** → parse (PyMuPDF) → clean headers/footers → chunk (800 tokens, tiktoken) → embed (local CPU) → store in ChromaDB + Postgres → `ready` → roadmap auto-generated
3. **Teaching** → roadmap → per-chapter lessons + quizzes cached per goal
4. **Q&A** → embed question → ChromaDB top-k retrieval → LLM answer with citations
5. **Progress** → quiz submissions scored → weak areas + overall progress tracked

## Frontend API Tester

A zero-build HTML tool lives in `frontend/`. Open `frontend/index.html` in a browser (works via `file://`) while the server runs on `:8000`. It has a panel for every endpoint with state carry-over (doc id → chapter id → lesson id) so you can click through the full flow.

## Project Structure

```
app/
├── main.py              # App factory, routers, CORS
├── config.py            # pydantic-settings
├── db.py               # Async engine/session
├── core/               # errors.py, ids.py
├── models/             # SQLAlchemy ORM
├── schemas/            # Pydantic v2 schemas (API contract)
├── api/               # routers: documents, ask, teaching
└── services/
    ├── ingestion/     # parser, cleaner, chunker, embedder, pipeline
    ├── pedagogy/      # goal_router, roadmap, lessons, quiz
    └── llm/          # client, prompts, orchestrator
```

## Testing

```bash
venv\Scripts\pytest.exe
```
