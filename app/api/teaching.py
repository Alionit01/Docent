from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db, async_session
from app.core.errors import AppError
from app.schemas.schemas import GoalType, Chapter as ChapterSchema, Lesson as LessonSchema
from app.models.models import Document, Chapter, Lesson
from app.services.pedagogy.roadmap import generate_roadmap
from app.services.pedagogy.lessons import generate_lesson
from app.services.pedagogy.quiz import generate_quiz

router = APIRouter(prefix="/api/documents", tags=["teaching"])


@router.get("/{document_id}/roadmap")
async def get_roadmap(document_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise AppError(detail="Document not found.", code="DOCUMENT_NOT_FOUND", status=404)
    if doc.status != "ready":
        raise AppError(detail="Document is not ready yet.", code="DOCUMENT_NOT_READY", status=409)

    result = await db.execute(
        select(Chapter).where(Chapter.document_id == document_id).order_by(Chapter.order)
    )
    chapters = result.scalars().all()

    if not chapters:
        chapters_data = await generate_roadmap(document_id, async_session)
        if not chapters_data:
            raise AppError(detail="Failed to generate roadmap.", code="ROADMAP_FAILED", status=500)
        result = await db.execute(
            select(Chapter).where(Chapter.document_id == document_id).order_by(Chapter.order)
        )
        chapters = result.scalars().all()

    if not chapters:
        raise AppError(detail="No chapters generated.", code="NO_CHAPTERS", status=500)

    return {
        "chapters": [
            {
                "id": ch.id,
                "document_id": ch.document_id,
                "title": ch.title,
                "order": ch.order,
                "summary": ch.summary,
                "lesson_count": ch.lesson_count,
            }
            for ch in chapters
        ]
    }


@router.get("/{document_id}/lessons/{lesson_id}")
async def get_lesson(
    document_id: str,
    lesson_id: str,
    goal: GoalType = Query("understand"),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise AppError(detail="Document not found.", code="DOCUMENT_NOT_FOUND", status=404)
    if doc.status != "ready":
        raise AppError(detail="Document is not ready yet.", code="DOCUMENT_NOT_READY", status=409)

    # The lesson_id could be a chapter ID if lesson doesn't exist yet
    chapter = await db.get(Chapter, lesson_id)
    if chapter and chapter.document_id != document_id:
        raise AppError(detail="Lesson not found.", code="LESSON_NOT_FOUND", status=404)

    if chapter:
        # Generate lesson for this chapter
        lesson = await generate_lesson(lesson_id, goal, async_session)
        if not lesson:
            raise AppError(detail="Failed to generate lesson.", code="LESSON_FAILED", status=500)
    else:
        lesson = await db.get(Lesson, lesson_id)
        if not lesson:
            raise AppError(detail="Lesson not found.", code="LESSON_NOT_FOUND", status=404)

    # Generate quiz if needed
    from sqlalchemy import select
    from app.models.models import QuizQuestion

    result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.lesson_id == lesson.id)
    )
    quiz_questions = result.scalars().all()

    if not quiz_questions:
        quiz_questions = await generate_quiz(lesson.id, goal, async_session)

    return {
        "lesson": {
            "id": lesson.id,
            "chapter_id": lesson.chapter_id,
            "goal_type": lesson.goal_type,
            "title": lesson.title,
            "explanation": lesson.explanation,
            "analogy": lesson.analogy,
            "key_points": lesson.key_points,
            "source_refs": lesson.source_refs,
        },
        "quiz": [
            {
                "id": q.id,
                "lesson_id": q.lesson_id,
                "question": q.question,
                "options": q.options,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
            }
            for q in quiz_questions[:2]
        ],
    }
