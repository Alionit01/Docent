import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Document, Chunk
from app.services.ingestion.parser import parse_pdf, detect_headings
from app.services.ingestion.cleaner import clean_pages
from app.services.ingestion.chunker import chunk_pages
from app.services.ingestion.embedder import Embedder
from app.config import settings


async def run_pipeline(document_id: str, filepath: str, db_session_factory):
    embedder = Embedder(model_name=settings.embedding_model, persist_dir=settings.chroma_persist_dir)

    try:
        # Parse
        pages, page_count = parse_pdf(filepath, settings.max_pages, settings.truncate_pages)
        detect_headings(pages)

        # Clean
        cleaned = clean_pages(pages)

        # Chunk
        chunks_data = chunk_pages(cleaned)

        # Tag chunks with document_id
        for ch in chunks_data:
            ch["document_id"] = document_id

        # Store chunks in Postgres
        async with db_session_factory() as session:
            doc = await session.get(Document, document_id)
            if not doc:
                return
            doc.page_count = page_count

            for ch_data in chunks_data:
                chunk = Chunk(
                    id=ch_data["id"],
                    document_id=document_id,
                    content=ch_data["content"],
                    page_number=ch_data["page_number"],
                    chapter_hint=ch_data.get("chapter_hint"),
                    token_count=ch_data["token_count"],
                )
                session.add(chunk)

            await session.commit()

        # Embed and store in ChromaDB
        embedder.store_chunks(chunks_data)

        # Set ready
        async with db_session_factory() as session:
            doc = await session.get(Document, document_id)
            if doc:
                doc.status = "ready"
                await session.commit()

        # Generate roadmap in background
        from app.services.pedagogy.roadmap import generate_roadmap
        try:
            await generate_roadmap(document_id, db_session_factory)
        except Exception:
            pass  # Roadmap failure is non-fatal; can be regenerated on demand

    except Exception as e:
        async with db_session_factory() as session:
            doc = await session.get(Document, document_id)
            if doc:
                doc.status = "failed"
                if hasattr(e, "code"):
                    doc.error_code = e.code
                else:
                    doc.error_code = "INGESTION_FAILED"
                await session.commit()
