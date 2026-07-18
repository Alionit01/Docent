"""Standalone endpoint test script for Docent backend.

Usage:
    python test_endpoints.py

Requires the server running at http://127.0.0.1:8000 (python run.py).
Creates its own test PDF, runs the full flow, and prints a summary.
"""
import asyncio
import io
import sys
import fitz  # PyMuPDF
import httpx

BASE = "http://127.0.0.1:8000"


def make_pdf(path: str, pages: int = 4) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Chapter {i+1}: Operating System Concepts")
        page.insert_text((72, 100), f"This is page {i+1} of the test document about operating systems, processes, and memory management.")
        page.insert_text((72, 120), f"A process is a program in execution. The OS manages process scheduling and context switching.")
    doc.save(path)
    doc.close()


async def main() -> None:
    results = []
    doc_id = None
    chapter_id = None
    lesson_id = None
    quiz_q_ids = []

    async with httpx.AsyncClient(base_url=BASE, timeout=120) as client:
        # 1. Health
        try:
            r = await client.get("/health")
            results.append(("GET /health", r.status_code == 200, r.status_code))
        except Exception as e:
            results.append(("GET /health", False, str(e)))

        # 2. Upload (create a temp PDF)
        pdf_path = "test_upload_tmp.pdf"
        make_pdf(pdf_path)
        try:
            with open(pdf_path, "rb") as f:
                r = await client.post(
                    "/api/documents/upload",
                    files={"file": ("test.pdf", f, "application/pdf")},
                )
            ok = r.status_code == 201
            results.append(("POST /api/documents/upload", ok, r.status_code))
            if ok:
                doc_id = r.json().get("id")
        except Exception as e:
            results.append(("POST /api/documents/upload", False, str(e)))

        # Wait for ready
        if doc_id:
            for _ in range(30):
                r = await client.get(f"/api/documents/{doc_id}")
                if r.json().get("status") == "ready":
                    break
                await asyncio.sleep(3)

            # 3. Get document
            try:
                r = await client.get(f"/api/documents/{doc_id}")
                results.append(("GET /api/documents/{id}", r.status_code == 200, r.status_code))
            except Exception as e:
                results.append(("GET /api/documents/{id}", False, str(e)))

            # 4. Roadmap
            try:
                r = await client.get(f"/api/documents/{doc_id}/roadmap")
                ok = r.status_code == 200 and "chapters" in r.json()
                results.append(("GET /api/documents/{id}/roadmap", ok, r.status_code))
                if ok:
                    chapter_id = r.json()["chapters"][0]["id"]
            except Exception as e:
                results.append(("GET /api/documents/{id}/roadmap", False, str(e)))

            # 5. Lesson
            if chapter_id:
                try:
                    r = await client.get(
                        f"/api/documents/{doc_id}/lessons/{chapter_id}?goal=understand"
                    )
                    ok = r.status_code == 200 and "lesson" in r.json()
                    results.append(("GET /api/documents/{id}/lessons/{chapterId}", ok, r.status_code))
                    if ok:
                        lesson_id = r.json()["lesson"]["id"]
                        quiz_q_ids = [q["id"] for q in r.json().get("quiz", [])]
                except Exception as e:
                    results.append(("GET /api/documents/{id}/lessons/{chapterId}", False, str(e)))

            # 6. Ask
            try:
                r = await client.post(
                    f"/api/documents/{doc_id}/ask",
                    json={"question": "what is a process?"},
                )
                ok = r.status_code == 200 and "answer" in r.json()
                results.append(("POST /api/documents/{id}/ask", ok, r.status_code))
            except Exception as e:
                results.append(("POST /api/documents/{id}/ask", False, str(e)))

        # 7. Quiz submit (if we have a lesson + quiz questions)
        if lesson_id and quiz_q_ids:
            try:
                answers = [{"question_id": qid, "selected_index": 0} for qid in quiz_q_ids]
                r = await client.post(
                    f"/api/documents/{doc_id}/lessons/{lesson_id}/quiz/submit",
                    json={"answers": answers},
                )
                ok = r.status_code == 200 and "score" in r.json()
                results.append(("POST .../quiz/submit", ok, r.status_code))
            except Exception as e:
                results.append(("POST .../quiz/submit", False, str(e)))
        else:
            results.append(("POST .../quiz/submit", False, "skipped: no lesson/quiz"))

        # 8. Progress
        if doc_id:
            try:
                r = await client.get(f"/api/documents/{doc_id}/progress")
                ok = r.status_code == 200 and "overall_progress" in r.json()
                results.append(("GET /api/documents/{id}/progress", ok, r.status_code))
            except Exception as e:
                results.append(("GET /api/documents/{id}/progress", False, str(e)))

            # 9. Final quiz
            try:
                r = await client.post(f"/api/documents/{doc_id}/quiz/final")
                ok = r.status_code == 200 and "questions" in r.json()
                results.append(("POST /api/documents/{id}/quiz/final", ok, r.status_code))
            except Exception as e:
                results.append(("POST /api/documents/{id}/quiz/final", False, str(e)))

        # Edge: missing document
        try:
            r = await client.get("/api/documents/doc_doesnotexist")
            ok = r.status_code == 404
            results.append(("GET missing doc -> 404", ok, r.status_code))
        except Exception as e:
            results.append(("GET missing doc -> 404", False, str(e)))

        # Edge: invalid MIME
        try:
            r = await client.post(
                "/api/documents/upload",
                files={"file": ("bad.txt", io.BytesIO(b"x"), "text/plain")},
            )
            ok = r.status_code == 400
            results.append(("POST upload non-PDF -> 400", ok, r.status_code))
        except Exception as e:
            results.append(("POST upload non-PDF -> 400", False, str(e)))

    # Summary
    print("\n" + "=" * 60)
    print("DOCENT ENDPOINT TEST SUMMARY")
    print("=" * 60)
    passed = 0
    for name, ok, status in results:
        mark = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"[{mark}] {name:<45} ({status})")
    print("-" * 60)
    print(f"{passed}/{len(results)} checks passed")
    print("=" * 60)

    # Cleanup
    try:
        import os
        os.remove(pdf_path)
    except Exception:
        pass

    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
