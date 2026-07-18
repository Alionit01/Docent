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

### 3. Create the database

Connect to your local Postgres as a superuser and run:

```sql
CREATE USER docent WITH PASSWORD 'docent';
CREATE DATABASE docent OWNER docent;
GRANT ALL PRIVILEGES ON DATABASE docent TO docent;
```

If your Postgres already has a `docent` database/user, skip this.

### 4. Configure environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Minimal `.env`:

```env
DATABASE_URL=postgresql+asyncpg://docent:docent@localhost:5432/docent
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

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/documents/upload` | Upload a PDF (max 50MB), starts async ingestion |
| `GET` | `/api/documents/{id}` | Poll document ingestion status |
| `GET` | `/api/documents/{id}/roadmap` | Get generated chapter roadmap |
| `GET` | `/api/documents/{id}/lessons/{chapterId}?goal=` | Get a lesson + quiz for a chapter (goal: `exam`/`understand`/`implement`/`research`) |
| `POST` | `/api/documents/{id}/ask` | Ask a grounded question about the document |

## How it works

1. **Upload** → PDF saved, `processing` row created, ingestion launched as a background task
2. **Ingestion** → parse (PyMuPDF) → clean headers/footers → chunk (800 tokens, tiktoken) → embed (local CPU) → store in ChromaDB + Postgres → `ready`
3. **Teaching** → roadmap generated via LLM → per-chapter lessons + quizzes cached per goal
4. **Q&A** → embed question → ChromaDB top-k retrieval → LLM answer with citations

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
