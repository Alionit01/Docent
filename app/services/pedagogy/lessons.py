import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Document, Chapter, Lesson, Chunk
from app.schemas.schemas import GoalType, Lesson as LessonSchema, SourceRef
from app.services.ingestion.embedder import Embedder
from app.services.llm.client import llm_complete
from app.services.llm.prompts import LESSON_PROMPT, GOAL_PROMPTS
from app.services.pedagogy.goal_router import get_goal_instruction
from app.core.ids import generate_id
from app.config import settings


def _verify_snippet(snippet: str, chunk_text: str) -> bool:
    return snippet.strip() in chunk_text


async def generate_lesson(
    chapter_id: str,
    goal_type: GoalType,
    db_session_factory,
) -> Lesson | None:
    async with db_session_factory() as session:
        chapter = await session.get(Chapter, chapter_id)
        if not chapter:
            return None

        doc = await session.get(Document, chapter.document_id)
        if not doc or doc.status != "ready":
            return None

        # Check cache
        result = await session.execute(
            select(Lesson).where(
                Lesson.chapter_id == chapter_id,
                Lesson.goal_type == goal_type,
            )
        )
        existing = result.scalars().first()
        if existing:
            return existing

        # Get chunks for this chapter
        embedder = Embedder(model_name=settings.embedding_model, persist_dir=settings.chroma_persist_dir)
        chroma_results = embedder.query(
            query_text=chapter.summary,
            top_k=6,
            document_id=chapter.document_id,
        )

        chunks_data = []
        if chroma_results:
            for r in chroma_results:
                chunks_data.append({
                    "id": r["id"],
                    "page": r["metadata"].get("page_number", 0),
                    "content": r["content"],
                })

        if not chunks_data:
            return None

        chunks_formatted = "\n".join(
            f"[Page {c['page']}] {c['content']}" for c in chunks_data
        )

        goal_instruction = get_goal_instruction(goal_type)
        prompt = LESSON_PROMPT.format(
            goal_instruction=goal_instruction,
            prev_lessons="None (first lesson for this chapter)",
            chunks_formatted=chunks_formatted,
            chapter_title=chapter.title,
            chapter_summary=chapter.summary,
            goal_type=goal_type,
        )

        messages = [
            {"role": "system", "content": "You are an expert tutor. Respond only in JSON."},
            {"role": "user", "content": prompt},
        ]

        result_data = await llm_complete(messages, temperature=0.3, json_mode=True)

        if not result_data:
            return None

        # Build source refs with verbatim check
        source_refs = []
        for ref in result_data.get("source_refs", []):
            snippet = ref.get("snippet", "")
            chunk_id = ref.get("chunk_id", "")
            page = ref.get("page", 0)

            # Find the chunk text to verify snippet
            matching_chunk = next((c for c in chunks_data if c["id"] == chunk_id), None)
            if matching_chunk and _verify_snippet(snippet, matching_chunk["content"]):
                source_refs.append({"page": page, "chunk_id": chunk_id, "snippet": snippet})

        if len(source_refs) < 1:
            source_refs = [{"page": chunks_data[0]["page"], "chunk_id": chunks_data[0]["id"], "snippet": chunks_data[0]["content"][:150]}]

        lesson_id = generate_id("les")
        lesson = Lesson(
            id=lesson_id,
            chapter_id=chapter_id,
            goal_type=goal_type,
            title=result_data.get("title", chapter.title),
            explanation=result_data.get("explanation", ""),
            analogy=result_data.get("analogy", ""),
            key_points=result_data.get("key_points", []),
            source_refs=source_refs[:4],
        )

        session.add(lesson)
        await session.commit()
        await session.refresh(lesson)
        return lesson
