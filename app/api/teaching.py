from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db, async_session
from app.core.errors import AppError
from app.schemas.schemas import GoalType, Chapter as ChapterSchema, Lesson as LessonSchema, QuizSubmitRequest
from app.models.models import Document, Chapter, Lesson, QuizQuestion, LessonProgress
from app.services.pedagogy.roadmap import generate_roadmap
from app.services.pedagogy.lessons import generate_lesson
from app.services.pedagogy.quiz import generate_quiz, generate_final_quiz
from app.services.progress import compute_progress, get_next_lesson_id

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


@router.post("/{document_id}/lessons/{lesson_id}/quiz/submit")
async def submit_quiz(
    document_id: str,
    lesson_id: str,
    body: QuizSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise AppError(detail="Document not found.", code="DOCUMENT_NOT_FOUND", status=404)

    lesson = await db.get(Lesson, lesson_id)
    if not lesson:
        raise AppError(detail="Lesson not found.", code="LESSON_NOT_FOUND", status=404)

    # Fetch quiz questions for this lesson
    result = await db.execute(
        select(QuizQuestion).where(QuizQuestion.lesson_id == lesson_id)
    )
    quiz_questions = {q.id: q for q in result.scalars().all()}

    if not quiz_questions:
        raise AppError(detail="No quiz found for this lesson.", code="NO_QUIZ", status=404)

    results = []
    correct_count = 0
    total = 0

    for answer in body.answers:
        q_id = answer.get("question_id")
        selected = answer.get("selected_index")

        q = quiz_questions.get(q_id)
        if not q:
            continue

        total += 1
        is_correct = selected == q.correct_index
        if is_correct:
            correct_count += 1

        results.append({
            "question_id": q_id,
            "correct": is_correct,
            "explanation": q.explanation,
        })

    score = int((correct_count / total) * 100) if total > 0 else 0

    # Upsert lesson_progress
    result = await db.execute(
        select(LessonProgress).where(
            LessonProgress.document_id == document_id,
            LessonProgress.lesson_id == lesson_id,
        )
    )
    existing = result.scalars().first()

    if existing:
        existing.score = score
    else:
        progress = LessonProgress(
            document_id=document_id,
            lesson_id=lesson_id,
            score=score,
        )
        db.add(progress)

    await db.commit()

    # Compute weak areas and next lesson
    progress_data = await compute_progress(document_id, async_session)
    next_lesson_id = await get_next_lesson_id(document_id, async_session)

    return {
        "score": score,
        "total": total,
        "results": results,
        "weak_areas": progress_data["weak_areas"],
        "next_lesson_id": next_lesson_id,
    }


@router.get("/{document_id}/progress")
async def get_progress(document_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise AppError(detail="Document not found.", code="DOCUMENT_NOT_FOUND", status=404)

    progress_data = await compute_progress(document_id, async_session)

    return {
        "document_id": document_id,
        "completed_lessons": progress_data["completed_lessons"],
        "score_by_lesson": progress_data["score_by_lesson"],
        "weak_areas": progress_data["weak_areas"],
        "overall_progress": progress_data["overall_progress"],
    }


@router.post("/{document_id}/quiz/final")
async def final_quiz(document_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, document_id)
    if not doc:
        raise AppError(detail="Document not found.", code="DOCUMENT_NOT_FOUND", status=404)
    if doc.status != "ready":
        raise AppError(detail="Document is not ready yet.", code="DOCUMENT_NOT_READY", status=409)

    questions = await generate_final_quiz(document_id, async_session)

    return {
        "questions": [
            {
                "id": q.id,
                "lesson_id": q.lesson_id,
                "question": q.question,
                "options": q.options,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
            }
            for q in questions
        ]
    }
