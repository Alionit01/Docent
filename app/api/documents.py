import os
import asyncio
import fitz
from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db, async_session
from app.core.errors import AppError
from app.core.ids import generate_id
from app.schemas.schemas import UploadResponse, Document
from app.models.models import Document as DocumentModel
from app.services.ingestion.pipeline import run_pipeline
from app.config import settings

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _get_page_count(filepath: str) -> int:
    doc = fitz.open(filepath)
    count = doc.page_count
    doc.close()
    return count


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise AppError(detail="File must be a PDF.", code="INVALID_PDF", status=400)

    contents = await file.read()
    file_size_mb = len(contents) / (1024 * 1024)
    if file_size_mb > settings.max_pdf_mb:
        raise AppError(
            detail=f"PDF exceeds {settings.max_pdf_mb}MB limit.",
            code="INVALID_PDF",
            status=400,
        )

    os.makedirs(settings.upload_dir, exist_ok=True)
    doc_id = generate_id("doc")
    safe_filename = f"{doc_id}.pdf"
    filepath = os.path.join(settings.upload_dir, safe_filename)
    with open(filepath, "wb") as f:
        f.write(contents)

    page_count = _get_page_count(filepath)

    doc = DocumentModel(id=doc_id, filename=file.filename, status="processing", page_count=page_count)
    db.add(doc)
    await db.commit()

    asyncio.create_task(run_pipeline(doc_id, filepath, async_session))

    return UploadResponse(id=doc_id, filename=file.filename, status="processing", page_count=page_count)


@router.get("/{document_id}", response_model=Document)
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(DocumentModel, document_id)
    if not doc:
        raise AppError(detail="Document not found.", code="DOCUMENT_NOT_FOUND", status=404)
    return doc
