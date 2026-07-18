# Plan: Docent API Frontend (Visual Testing Tool)

## Goal
A single-page HTML app (no build step) that lets you visually exercise all 8 backend
endpoints against a running `python run.py` server. Focus is exclusively on the API
contract — not a product UI. Shows request/response JSON, status codes, and error codes.

## CORS — do you need to configure it?
**Yes, but only if the HTML file is opened from a different origin than the API.**

Current backend CORS allows `http://localhost:3000` only:
```python
allow_origins=["http://localhost:3000"]
```

Two cases:
1. **Open HTML via `file://` or different port** (e.g. `http://localhost:5500`, Live Server)
   → browser blocks fetch → you MUST add that origin to `allow_origins`.
2. **Serve HTML from same origin as API** (e.g. put `index.html` in a folder the API
   serves, or run a tiny static server on `localhost:3000`) → no CORS issue.

**Recommendation for this tool:** Add `http://localhost:8000` and `http://localhost:5500`
(or `null` for `file://`) to the CORS allow list in `app/main.py` so the HTML works
whether opened directly or via a dev server. Keep credentials handling simple.

## Tech Choice
- **Plain `index.html` + vanilla JS** (no React/Next). Zero build, double-click to open.
- Use `fetch()` + `FormData` for the multipart upload.
- Split into `frontend/index.html` / `frontend/app.js` / `frontend/styles.css`.

## Layout
A left nav listing the 8 endpoints. Clicking one opens a panel with:
- Method + URL (read-only, with `{id}` placeholders as input fields)
- Request body builder (text area for JSON, file picker for upload)
- "Send" button
- Response area: status code, formatted JSON, raw error envelope

## Endpoint Panels (exact contract from AGENTS.md)

### 1. POST /api/documents/upload
- Input: file picker (PDF)
- Sends `multipart/form-data` `file`
- Shows: `201 UploadResponse {id, filename, status, page_count}`
- Edge: non-PDF → 400 INVALID_PDF; >50MB → 400; >2 concurrent → 429 RATE_LIMITED

### 2. GET /api/documents/{id}
- Input: document id
- Shows: `Document` status (poll loop button "Poll until ready")

### 3. GET /api/documents/{id}/roadmap
- Input: document id
- Shows: `{chapters: [{id, title, order, summary, lesson_count}]}`
- 409 DOCUMENT_NOT_READY if processing

### 4. GET /api/documents/{id}/lessons/{lessonId}?goal=
- Inputs: document id, chapter id (from roadmap), goal dropdown (exam/understand/implement/research)
- Shows: `{lesson: Lesson, quiz: [QuizQuestion x2]}`
- Note: pass a chapter `id` — lesson is generated on first hit

### 5. POST /api/documents/{id}/ask
- Inputs: document id, question text, optional lesson_context_id
- Body: `{"question": "...", "lesson_context_id": null}`
- Shows: `AskResponse {answer, citations[], follow_up_questions[]}`

### 6. POST /api/documents/{id}/lessons/{lessonId}/quiz/submit
- Inputs: document id, lesson id, JSON array of answers `[{question_id, selected_index}]`
- Shows: `QuizSubmitResponse {score, total, results[], weak_areas[], next_lesson_id}`

### 7. GET /api/documents/{id}/progress
- Input: document id
- Shows: `{document_id, completed_lessons[], score_by_lesson{}, weak_areas[], overall_progress}`

### 8. POST /api/documents/{id}/quiz/final
- Input: document id
- Shows: `{questions: QuizQuestion[10]}`

## Files to Create
- `frontend/index.html` — markup + nav
- `frontend/app.js` — fetch logic per endpoint, state (last doc id, chapter id, lesson id, quiz q ids) carried across panels
- `frontend/styles.css` — minimal dark UI
- `app/main.py` — extend CORS `allow_origins`

## State Carry-Over (key UX)
After upload → store doc id. After roadmap → store chapter id. After lesson → store
lesson id + quiz question ids. Pre-fill downstream panels so you can click through the
whole flow without copy-paste.

## Verification
1. `python run.py` (server on :8000)
2. Open `frontend/index.html` in browser
3. Upload a PDF → poll → roadmap → lesson → quiz submit → progress → final quiz → ask
4. Confirm each panel shows correct JSON + status codes
5. Test edge cases (non-PDF upload, missing doc id)
