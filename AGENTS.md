# AGENTS.md — Docent Backend

Single source of truth for the implementing agent. Read this fully before writing any code.
The full product spec (readable extraction) is in `spec_text.txt` — consult it for anything not covered here.

---

## 1. What we are building

**Docent** is an AI Document Teaching System: a user uploads a PDF, picks a learning goal (`exam` | `understand` | `implement` | `research`), and the system produces a chapter roadmap, grounded lessons (Feynman-style explanation + analogy + key points + page citations), 2-question quizzes per lesson, grounded Q&A, and progress/weak-area tracking.

**This repo is the BACKEND ONLY**: FastAPI + PostgreSQL (relational store) + ChromaDB (local vector store, no separate vector DB) + a **local CPU embedding model** + an LLM served by **Groq** (OpenAI-compatible API via the `openai` SDK pointed at Groq's base URL). The frontend (Next.js) lives in a separate repo — we only expose the REST API defined in §7.

---

## 2. Team workflow (read carefully)

| Role | Agent | Responsibility |
|---|---|---|
| Planner / Reviewer | Kimi K2 (terminal 1) | Owns this file, reviews code via `git diff`, writes fix prompts |
| Implementer | DeepSeek (terminal 2) | Implements the phases in §8, one task at a time |
| Environment owner | The user | Creates venv, installs pip/uv packages, runs servers, owns API keys |

### Hard rules for the implementer

1. **NEVER create a venv or install packages.** Add every new dependency to `requirements.txt`. If an import fails, stop and tell the user what to install.
2. **One task at a time, in order.** Do not start task N+1 until task N's acceptance criteria pass.
3. **Commit after every completed task** with message format: `p<phase>.<task>: <short description>` (e.g. `p1.3: pdf parser with heading detection`). Small commits are mandatory — the reviewer inspects `git diff` per commit.
4. **If any `plans/PLAN_*.md` file exists, those fixes take priority** over new phase work. After fixing, commit with `fix(PLAN_<NNN>): <description>`.
5. **Pydantic schemas (§6, §7) are the contract.** Match field names and constraints exactly — the frontend mirrors them with Zod.
6. **No auth, single tenant, one document at a time.** Do not build users, login, or multi-tenancy.
7. When the spec is silent, pick the simplest option and record the decision in the commit body.

### Review loop

User asks Kimi to review → Kimi inspects `git log` / `git diff` → if bugs or spec deviations are found, Kimi writes `plans/PLAN_<NNN>.md` (zero-padded, incrementing) containing a self-contained fix prompt → user pastes it to DeepSeek → DeepSeek fixes and commits. If review passes, DeepSeek proceeds to the next task.

---

## 3. Tech stack (fixed — no substitutions)

- **Python 3.11+**, FastAPI, Uvicorn
- **Pydantic v2** + pydantic-settings
- **SQLAlchemy 2.0 async** (asyncpg) + Alembic
- **PostgreSQL 16** (relational store only — already running locally; no extensions needed)
- **ChromaDB** (embedded, file-based local vector store; no separate vector DB process). Stores chunk vectors + metadata; Postgres remains the source of truth for documents/chapters/lessons/quiz/progress.
- **Local CPU embedding model** via Chroma's built-in ONNX default (`all-MiniLM-L6-v2`, 384-dim, runs on CPU, no torch/GPU needed). Model is auto-downloaded on first run. Override with `sentence-transformers` + a HuggingFace model if a different dim is required.
- **PyMuPDF** (fitz) for PDF parsing; pdfplumber only as fallback for tables
- **tiktoken** (`cl100k_base`) for token counting
- **openai** python SDK — pointed at Groq's OpenAI-compatible endpoint (`https://api.groq.com/openai/v1`); models like `llama-3.3-70b-versatile`
- **pytest** + pytest-asyncio + httpx (AsyncClient) for tests

## 4. Target repo layout

```
.
├── AGENTS.md                  # this file
├── spec_text.txt              # full readable product spec
├── requirements.txt
├── .env.example
├── alembic.ini
├── alembic/                   # migrations
├── app/
│   ├── main.py                # app factory, routers, exception handlers, CORS
│   ├── config.py              # pydantic-settings
│   ├── db.py                  # async engine/session
│   ├── models/                # SQLAlchemy ORM models
│   ├── schemas/               # Pydantic v2 schemas (source of truth)
│   ├── api/                   # routers: documents, lessons, ask, quiz, progress
│   ├── core/                  # errors.py (ErrorResponse envelope + codes), ids.py
│   └── services/
│       ├── ingestion/         # parser.py, cleaner.py, chunker.py, embedder.py, vectorstore.py, pipeline.py
│       ├── pedagogy/          # goal_router.py, roadmap.py, lessons.py, quiz.py
│       ├── llm/               # client.py (provider adapter), prompts.py, orchestrator.py
│       └── progress.py
├── data/uploads/              # uploaded PDFs (gitignored)
├── data/chroma/               # ChromaDB persistent storage (gitignored)
└── tests/                     # pytest, mirrors app/ structure
```

## 5. Configuration (`.env`)

```
DATABASE_URL=postgresql+asyncpg://docent:docent@localhost:5432/docent
LLM_PROVIDER=groq
LLM_API_KEY=...
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=all-MiniLM-L6-v2     # Chroma built-in ONNX default; runs on CPU
EMBEDDING_DIM=384                    # must match the model above
CHROMA_PERSIST_DIR=./data/chroma
UPLOAD_DIR=./data/uploads
MAX_PDF_MB=50
MAX_PAGES=100                  # reject above
TRUNCATE_PAGES=50              # process first N pages when doc > MAX_PAGES... see edge cases
```

Note the spec's exact wording: PDFs up to 100 pages are accepted; if larger, process the **first 50 pages** and continue (banner is a frontend concern — backend stores `page_count` actually processed). Reject PDFs < 2 pages.

## 6. Data models (copy verbatim — contract)

### 6a. Pydantic schemas (`app/schemas/`)

```python
from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Optional
from datetime import datetime

GoalType = Literal['exam','understand','implement','research']

class Document(BaseModel):
    id: str
    filename: str
    status: Literal['processing','ready','failed']
    page_count: int = Field(ge=1)
    created_at: datetime

class Chunk(BaseModel):
    id: str
    document_id: str
    content: str = Field(min_length=20)
    embedding: Optional[List[float]] = None
    page_number: int
    chapter_hint: Optional[str] = None
    token_count: int

class Chapter(BaseModel):
    id: str
    document_id: str
    title: str
    order: int
    summary: str
    lesson_count: int = 1

class SourceRef(BaseModel):
    page: int
    chunk_id: str
    snippet: str = Field(max_length=300)

class Lesson(BaseModel):
    id: str
    chapter_id: str
    goal_type: GoalType
    title: str
    explanation: str
    analogy: str
    key_points: List[str] = Field(min_length=2, max_length=5)
    source_refs: List[SourceRef] = Field(min_length=1, max_length=4)

class QuizQuestion(BaseModel):
    id: str
    lesson_id: str
    question: str
    options: List[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str

class UserProgress(BaseModel):
    document_id: str
    completed_lessons: List[str] = []
    scores: Dict[str, int] = {}
    weak_areas: List[str] = []
    overall_progress: int = Field(ge=0, le=100)
```

API-level schemas (also contract):

```python
class UploadResponse(BaseModel):
    id: str
    filename: str
    status: Literal['processing'] = 'processing'
    page_count: int

class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    lesson_context_id: Optional[str] = None

class Citation(BaseModel):
    page: int
    chunk_id: str
    snippet: str

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(min_length=1)
    follow_up_questions: List[str] = Field(max_length=3)

class QuizSubmitRequest(BaseModel):
    answers: List[Dict]  # [{question_id, selected_index}]

class QuizSubmitResponse(BaseModel):
    score: int
    total: int
    results: List[Dict]  # [{question_id, correct, explanation}]
    weak_areas: List[str]
    next_lesson_id: Optional[str]

class ErrorResponse(BaseModel):
    detail: str
    code: str        # e.g. DOCUMENT_NOT_READY, INVALID_PDF
    meta: Optional[Dict] = None
```

### 6b. Database tables (SQLAlchemy + Alembic)

| Table | Columns |
|---|---|
| `documents` | id PK, filename, status (`processing`/`ready`/`failed`), page_count, error_code NULL, created_at |
| `chunks` | id PK, document_id FK, content, page_number, chapter_hint NULL, token_count |
| `chapters` | id PK, document_id FK, title, "order", summary, lesson_count |
| `lessons` | id PK, chapter_id FK, goal_type, title, explanation, analogy, key_points JSONB, source_refs JSONB, UNIQUE(chapter_id, goal_type) |
| `quiz_questions` | id PK, lesson_id FK, question, options JSONB, correct_index, explanation |
| `lesson_progress` | id PK, document_id FK, lesson_id FK, score INT (0–100), completed_at, UNIQUE(document_id, lesson_id) |

- **ID format**: `doc_`, `chk_`, `ch_`, `les_`, `q_` prefix + first 12 hex chars of uuid4 (`app/core/ids.py`).
- **Vectors live in ChromaDB**, not Postgres. The `chunks` table holds text + metadata only; the chunk vector + same metadata are stored in a Chroma collection keyed by `chunk_id`. Retrieval = Chroma query → `chunk_id`s → fetch content from Postgres.
- Lessons/quizzes are **generated once per (chapter, goal) and cached in DB** — regeneration only on explicit request.

## 7. API contract

Base path `/api`. All errors return `ErrorResponse` with the right HTTP status.

| # | Method & Path | Description | Success | Notes |
|---|---|---|---|---|
| 1 | `POST /api/documents/upload` | multipart `file` (pdf, <50MB). Validates, stores, starts async ingestion, returns immediately | `201 UploadResponse` | 400 `INVALID_PDF`, 400 `DOCUMENT_TOO_SHORT`, 422 `DOCUMENT_IS_SCANNED`, 429 `RATE_LIMITED` |
| 2 | `GET /api/documents/{id}` | Poll ingestion status | `200 Document` | 404 `DOCUMENT_NOT_FOUND` |
| 3 | `GET /api/documents/{id}/roadmap` | `{chapters: Chapter[]}` generated after ingestion | 200 | 409 `DOCUMENT_NOT_READY` |
| 4 | `GET /api/documents/{id}/lessons/{lessonId}?goal=` | `{lesson: Lesson, quiz: QuizQuestion[2]}`. `goal` defaults to `understand`; cached per goal | 200 | 404, 409 `DOCUMENT_NOT_READY` |
| 5 | `POST /api/documents/{id}/ask` | Body `AskRequest`. Grounded Q&A from document only, with citations | `200 AskResponse` | Out-of-scope question → answer says not covered + closest citation; never hallucinate |
| 6 | `POST /api/documents/{id}/lessons/{lessonId}/quiz/submit` | Body `QuizSubmitRequest` | `200 QuizSubmitResponse` | Computes score, weak_areas, next_lesson_id |
| 7 | `GET /api/documents/{id}/progress` | `{completed_lessons, score_by_lesson, weak_areas, overall_progress}` | 200 | weak = chapter avg score < 60% |
| 8 | `POST /api/documents/{id}/quiz/final` | Generates 10 mixed MCQs from weak-area chapters (completion screen "final quiz") | `200 {questions: QuizQuestion[]}` | If no weak areas, sample across all chapters |

## 8. Phases — implement in this exact order

> Context: this backend corresponds to spec Phases 0–2 and the backend half of Phase 4. Phase numbering here matches the spec.

### Phase 0 — Foundation
- **0.1** Repo skeleton: folder layout above, `app/main.py` with `GET /health` → `{"status":"ok"}`, config via pydantic-settings, `.env.example`.
- **0.2** `requirements.txt` (fastapi, uvicorn[standard], pydantic, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic, chromadb, PyMuPDF, pdfplumber, tiktoken, openai, python-multipart, pytest, pytest-asyncio, httpx). **Hand to user to install.**
- **0.3** Postgres is already running locally — create a `docent` database/user (or point `DATABASE_URL` at an existing one). No docker-compose needed for the DB; skip it unless you want one for portability.
- **0.4** Alembic init (async template), `db.py` engine/session, base migration (no `CREATE EXTENSION vector` — vectors live in ChromaDB).
- **0.5** `app/core/errors.py`: `AppError(detail, code, status, meta)` + exception handler returning `ErrorResponse`; 404/409/422 handlers; CORS open to localhost.

**Done when:** app boots, `/health` 200, `alembic upgrade head` runs clean against docker Postgres.

### Phase 1 — Ingestion
- **1.1** ORM models + migration for all 7 tables (§6b). No vector columns or HNSW indexes — vectors live in ChromaDB.
- **1.2** `POST /upload`: MIME + size validation (<50MB), save to `UPLOAD_DIR`, create `documents` row (`processing`), launch ingestion as an in-process `asyncio` background task (no Celery), return 201 immediately. Max 2 concurrent ingestions per IP → else 429 `RATE_LIMITED` with `Retry-After`.
- **1.3** `parser.py`: PyMuPDF extract per page; heading detection via font-size heuristic (lines whose font size is in the top tier → `chapter_hint`). Page rules: <2 pages → fail `DOCUMENT_TOO_SHORT`; >100 pages → truncate to first 50; avg chars/page < 50 → fail `DOCUMENT_IS_SCANNED`. Failures set `status=failed` + `error_code`.
- **1.4** `cleaner.py`: drop lines repeated on >70% of pages (headers/footers), de-hyphenate line-break hyphenation, normalize whitespace.
- **1.5** `chunker.py`: tiktoken `cl100k_base`, 800-token chunks, 100 overlap, prefer splitting on heading boundaries, keep `page_number` + `chapter_hint` + `token_count` per chunk. Min content length 20 chars.
- **1.6** `embedder.py` + `vectorstore.py`: local CPU embedding via Chroma's built-in `all-MiniLM-L6-v2` ONNX function (384-dim), batches of 64, retry 3x with backoff. Persist vectors to Chroma (`CHROMA_PERSIST_DIR`) in a collection keyed by `chunk_id` with metadata `{document_id, page_number, chapter_hint}`. On persistent failure: store chunks in Postgres with no Chroma entry and flag document for keyword fallback — do not crash the pipeline.
- **1.7** `pipeline.py`: orchestrate parse→clean→chunk→embed→store, then set `status=ready` (+ roadmap generation trigger from Phase 2 once it exists; stub it for now).
- **1.8** `GET /api/documents/{id}` status endpoint.
- **1.9** `POST /ask`: embed question via the same local model → Chroma cosine top-k (k=6; `lesson_context_id` biases retrieval to that lesson's chunks via metadata filter) → LLM answer with JSON mode → `AskResponse`. Keyword fallback (ILIKE on `chunks.content`) when a document has no Chroma entries. Out-of-document question → respond that it isn't covered + closest citation.

**Done when:** uploading a real text PDF ends in `status=ready` with embedded chunks in DB; `/ask` returns answers with ≥1 real citation; scanned/short/oversized PDFs fail with the exact error codes; tests for parser/chunker/upload validation pass.

### Phase 2 — Teaching Engine
- **2.1** `llm/client.py`: OpenAI SDK pointed at Groq base URL, JSON-mode helper, retry with exponential backoff (tenacity or hand-rolled), token-usage logging.
- **2.2** `llm/prompts.py`: verbatim `GOAL_PROMPTS` + `LESSON_PROMPT` from §9 + quiz-generation + repair prompts.
- **2.3** `goal_router.py`: map `GoalType` → system prompt. Pure function, trivially testable.
- **2.4** `roadmap.py`: LLM call with first 5k tokens of document → JSON chapters `[{title, order, summary}]` (temperature 0.2) → store chapters (lesson_count defaults 1). Wire into pipeline end + `GET /roadmap`.
- **2.5** `lessons.py`: per chapter, retrieve top-6 chunks filtered by `chapter_hint`, include previous lesson titles for continuity, generate lesson JSON → validate with Pydantic → store keyed (chapter_id, goal_type). Verify every `source_refs.snippet` is a verbatim substring of the cited chunk; drop invalid refs. Serve `GET /lessons/{lessonId}?goal=` (generate-on-miss, then cache).
- **2.6** `quiz.py`: from the same chunks, exactly 2 MCQs; distractors must come from the document (not generic); explanation must cite a page. Store with lesson.
- **2.7** `orchestrator.py` hardening: on JSON parse/validation failure, retry 2x with a repair prompt; final fallback → raw-text lesson without quiz (never 500 on the learner).

**Done when:** full flow upload → roadmap → lesson+quiz works for all 4 goals; all LLM JSON validates against §6a; tests for goal router, snippet-verbatim check, and quiz schema pass.

### Phase 4 — Progress & Polish (backend tasks)
- **4.1** `POST quiz/submit`: score answers, upsert `lesson_progress`, return results + explanations, recompute weak areas, determine `next_lesson_id` (next incomplete lesson in roadmap order).
- **4.2** `GET /progress`: completed_lessons, score_by_lesson, weak_areas (chapter avg < 60%), overall_progress (% lessons completed).
- **4.3** `POST /quiz/final`: 10 mixed MCQs grounded in weak-area chunks (all chapters if none weak).
- **4.4** Rate limiting middleware for upload (from 1.2, if deferred) + global request logging.
- **4.5** Test sweep: async endpoint tests for all 8 routes with a seeded fake document; edge-case tests from §10.

**Done when:** all endpoints work against a seeded DB, pytest suite is green, and a manual run through the demo script (upload → goal → roadmap → lesson → fail quiz → ask → progress) succeeds.

## 9. Prompts (verbatim — do not reword)

```python
GOAL_PROMPTS = {
  "exam": "You are a tutor helping a student pass an exam. Focus on definitions, key formulas, and common trap questions. Use mnemonics.",
  "understand": "You are a tutor helping a student understand deeply. Use simple language, analogies, and build intuition. Avoid jargon.",
  "implement": "You are a senior engineer teaching implementation. Focus on APIs, code snippets, edge cases, performance. Be practical.",
  "research": "You are a research mentor. Focus on mathematical rigor, proofs, assumptions, and open problems. Cite limitations."
}

LESSON_PROMPT = """
{goal_instruction}

Context:
- Previous lessons: {prev_lessons}
- Document chunks (with page numbers):
{chunks_formatted}
  Each chunk: [Page {{page}}] {{content}}

Task: Generate a lesson for chapter "{chapter_title}" - {chapter_summary}
Goal: {goal_type}

Return JSON exactly:
{{
  "title": "string, <60 chars",
  "explanation": "150-250 words, Feynman style, grounded in chunks",
  "analogy": "1 analogy, real-world, <40 words",
  "key_points": ["3-4 bullets, each <20 words"],
  "source_refs": [{{"page": int, "chunk_id": str, "snippet": "exact 10-20 words from chunk"}}],
  "used_chunk_ids": ["ids actually used"]
}}

Rules:
- Every factual claim must be in provided chunks.
- source_refs must be verbatim snippets.
- If chunk missing info, say "Not covered in document" - do not hallucinate.
- Keep reading level grade 10-12 unless goal=research.
"""
```

## 10. Edge cases (must all be handled)

| Case | Behavior |
|---|---|
| PDF > 100 pages | Process first 50 pages only |
| PDF < 2 pages | 400 `DOCUMENT_TOO_SHORT` |
| Scanned PDF (avg chars/page < 50) | Fail `DOCUMENT_IS_SCANNED` |
| LLM JSON parse fail | Retry 2x with repair prompt → fallback raw-text lesson, no quiz |
| Concurrent uploads | Max 2 processing per IP → 429 + `Retry-After` |
| Embedding failure | Retry batch; if still failing store chunks in Postgres with no Chroma entry, keyword fallback for that doc |
| Ask outside document | Never hallucinate: "not covered" + closest related citation |
| Goal switch mid-course | Allowed; lessons are cached per goal, progress is kept |

## 11. Definition of done (every task)

1. Code + tests written, acceptance criteria met (tests may be run by the user if the env isn't active in your terminal — say so explicitly).
2. `requirements.txt` updated if deps changed.
3. Committed as `p<phase>.<task>: ...`.
4. No placeholder/TODO code left behind.
