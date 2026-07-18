import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import QuizQuestion, Lesson, Chunk
from app.services.ingestion.embedder import Embedder
from app.services.llm.client import llm_complete
from app.services.llm.prompts import QUIZ_PROMPT
from app.services.pedagogy.goal_router import get_goal_instruction
from app.core.ids import generate_id
from app.config import settings


async def generate_quiz(
    lesson_id: str,
    goal_type: str,
    db_session_factory,
) -> list[QuizQuestion]:
    async with db_session_factory() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            return []

        # Check if quiz already exists
        from sqlalchemy import select
        result = await session.execute(
            select(QuizQuestion).where(QuizQuestion.lesson_id == lesson_id)
        )
        existing = result.scalars().all()
        if existing:
            return list(existing)

        # Get chunks for context
        embedder = Embedder(model_name=settings.embedding_model, persist_dir=settings.chroma_persist_dir)
        chroma_results = embedder.query(
            query_text=lesson.explanation[:200],
            top_k=6,
            document_id=None,
        )

        chunks_formatted = ""
        if chroma_results:
            chunks_formatted = "\n".join(
                f"[Page {r['metadata'].get('page_number', 0)}] {r['content']}"
                for r in chroma_results
            )

        goal_instruction = get_goal_instruction(goal_type)
        prompt = QUIZ_PROMPT.format(
            goal_instruction=goal_instruction,
            chunks_formatted=chunks_formatted,
        )

        messages = [
            {"role": "system", "content": "You are a quiz generator. Respond only in JSON."},
            {"role": "user", "content": prompt},
        ]

        result_data = await llm_complete(messages, temperature=0.4, json_mode=True)

        if not result_data or "questions" not in result_data:
            return []

        questions = []
        for q_data in result_data["questions"][:2]:
            q = QuizQuestion(
                id=generate_id("q"),
                lesson_id=lesson_id,
                question=q_data.get("question", ""),
                options=q_data.get("options", []),
                correct_index=q_data.get("correct_index", 0),
                explanation=q_data.get("explanation", ""),
            )
            session.add(q)
            questions.append(q)

        await session.commit()
        return questions


FINAL_QUIZ_PROMPT = """
{goal_instruction}

Document chunks (from weak areas if available):
{chunks_formatted}
  Each chunk: [Page {{page}}] {{content}}

Generate exactly 10 multiple-choice quiz questions covering the document content.
Three incorrect options MUST be plausible distractors from the document (not generic).
Each correct answer explanation MUST cite a page number.

Return JSON exactly:
{{
  "questions": [
    {{
      "question": "string",
      "options": ["A", "B", "C", "D"],
      "correct_index": 0,
      "explanation": "why correct, citing page X"
    }}
  ]
}}
"""


async def generate_final_quiz(
    document_id: str,
    db_session_factory,
    num_questions: int = 10,
) -> list[QuizQuestion]:
    from sqlalchemy import select, func
    from app.services.progress import compute_progress

    async with db_session_factory() as session:
        # Determine weak areas
        progress_data = await compute_progress(document_id, db_session_factory)
        weak_areas = progress_data["weak_areas"]

        # Get chapters
        result = await session.execute(
            select(Chapter).where(Chapter.document_id == document_id).order_by(Chapter.order)
        )
        chapters = result.scalars().all()

        if not chapters:
            return []

        # If weak areas exist, filter chapters by weak area titles
        target_chapters = chapters
        if weak_areas:
            weak_set = set(weak_areas)
            target_chapters = [c for c in chapters if c.title in weak_set]

        # Gather chunks from target chapters via ChromaDB
        embedder = Embedder(model_name=settings.embedding_model, persist_dir=settings.chroma_persist_dir)

        chunk_texts = []
        for ch in target_chapters[:5]:
            chroma_results = embedder.query(
                query_text=ch.summary,
                top_k=4,
                document_id=document_id,
            )
            for r in chroma_results:
                chunk_texts.append({
                    "page": r["metadata"].get("page_number", 0),
                    "content": r["content"],
                })

        if not chunk_texts:
            # Fallback: get any chunks from the document
            chroma_results = embedder.query(
                query_text="document content",
                top_k=20,
                document_id=document_id,
            )
            chunk_texts = [
                {"page": r["metadata"].get("page_number", 0), "content": r["content"]}
                for r in chroma_results
            ]

        chunks_formatted = "\n".join(
            f"[Page {c['page']}] {c['content']}" for c in chunk_texts[:30]
        )

        goal_instruction = get_goal_instruction("exam")
        prompt = FINAL_QUIZ_PROMPT.format(
            goal_instruction=goal_instruction,
            chunks_formatted=chunks_formatted,
        )

        messages = [
            {"role": "system", "content": "You are a quiz generator. Respond only in JSON."},
            {"role": "user", "content": prompt},
        ]

        result_data = await llm_complete(messages, temperature=0.4, json_mode=True)

        if not result_data or "questions" not in result_data:
            return []

        questions = []
        for q_data in result_data["questions"][:num_questions]:
            q = QuizQuestion(
                id=generate_id("q"),
                lesson_id="",
                question=q_data.get("question", ""),
                options=q_data.get("options", []),
                correct_index=q_data.get("correct_index", 0),
                explanation=q_data.get("explanation", ""),
            )
            session.add(q)
            questions.append(q)

        await session.commit()
        return questions
