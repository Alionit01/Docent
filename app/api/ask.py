from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.core.errors import AppError
from app.schemas.schemas import AskRequest, AskResponse, Citation
from app.models.models import Document, Chunk
from app.services.ingestion.embedder import Embedder
from app.services.llm.client import llm_complete
from app.services.llm.prompts import ASK_PROMPT
from app.config import settings

router = APIRouter(prefix="/api/documents", tags=["ask"])


def _build_chunks_formatted(chunks: list) -> str:
    lines = []
    for ch in chunks:
        lines.append(f"[chunk_id: {ch['id']}, Page {ch['page']}] {ch['content']}")
    return "\n".join(lines)


async def _keyword_fallback(document_id: str, question: str, db: AsyncSession) -> list[dict]:
    """ILIKE search on chunks.content when ChromaDB has no entries."""
    result = await db.execute(
        select(Chunk).where(
            Chunk.document_id == document_id,
            Chunk.content.ilike(f"%{question}%"),
        ).limit(6)
    )
    rows = result.scalars().all()
    return [{"id": r.id, "page": r.page_number, "content": r.content} for r in rows]


@router.post("/{document_id}/ask", response_model=AskResponse)
async def ask_document(
    document_id: str,
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise AppError(detail="Document not found.", code="DOCUMENT_NOT_FOUND", status=404)
    if doc.status != "ready":
        raise AppError(detail="Document is not ready yet.", code="DOCUMENT_NOT_READY", status=409)

    embedder = Embedder(model_name=settings.embedding_model, persist_dir=settings.chroma_persist_dir)

    # Try ChromaDB
    chroma_results = embedder.query(query_text=body.question, top_k=6, document_id=document_id)

    if chroma_results:
        chunks = [{"id": r["id"], "page": r["metadata"].get("page_number", 0), "content": r["content"]} for r in chroma_results]
    else:
        # Keyword fallback
        chunks = await _keyword_fallback(document_id, body.question, db)

    if not chunks:
        raise AppError(detail="No relevant content found in the document.", code="NO_CONTENT_FOUND", status=404)

    chunks_formatted = _build_chunks_formatted(chunks)

    prompt = ASK_PROMPT.format(chunks_formatted=chunks_formatted, question=body.question)
    messages = [
        {"role": "system", "content": "You are a helpful assistant. Respond only in JSON."},
        {"role": "user", "content": prompt},
    ]

    result = await llm_complete(messages, temperature=0.2, json_mode=True)

    if result is None:
        raise AppError(detail="Failed to generate answer.", code="LLM_ERROR", status=500)

    citations = [
        Citation(page=c.get("page", 0), chunk_id=c.get("chunk_id", ""), snippet=c.get("snippet", ""))
        for c in result.get("citations", [])
    ]

    return AskResponse(
        answer=result.get("answer", "Not covered in document."),
        citations=citations if citations else [
            Citation(page=chunks[0]["page"], chunk_id=chunks[0]["id"], snippet=chunks[0]["content"][:100])
        ],
        follow_up_questions=result.get("follow_up_questions", []),
    )
