import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_upload_invalid_mime(client: AsyncClient):
    # Send a non-PDF file
    files = {"file": ("test.txt", b"not a pdf", "text/plain")}
    resp = await client.post("/api/documents/upload", files=files)
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_PDF"


@pytest.mark.asyncio
async def test_get_missing_document(client: AsyncClient):
    resp = await client.get("/api/documents/doc_nonexistent")
    assert resp.status_code == 404
    assert resp.json()["code"] == "DOCUMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_ask_missing_document(client: AsyncClient):
    resp = await client.post(
        "/api/documents/doc_nonexistent/ask",
        json={"question": "what is this?"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_roadmap_not_ready(client: AsyncClient, session_factory):
    from app.models.models import Document
    import uuid

    doc_id = f"doc_test_{uuid.uuid4().hex[:8]}"
    async with session_factory() as session:
        doc = Document(id=doc_id, filename="t.pdf", status="processing", page_count=5)
        session.add(doc)
        await session.commit()

    resp = await client.get(f"/api/documents/{doc_id}/roadmap")
    assert resp.status_code == 409
    assert resp.json()["code"] == "DOCUMENT_NOT_READY"


@pytest.mark.asyncio
async def test_progress_missing_document(client: AsyncClient):
    resp = await client.get("/api/documents/doc_nonexistent/progress")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_final_quiz_missing_document(client: AsyncClient):
    resp = await client.post("/api/documents/doc_nonexistent/quiz/final")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_quiz_submit_missing_lesson(client: AsyncClient):
    resp = await client.post(
        "/api/documents/doc_nonexistent/lessons/les_nonexistent/quiz/submit",
        json={"answers": [{"question_id": "q_123", "selected_index": 0}]},
    )
    assert resp.status_code == 404
