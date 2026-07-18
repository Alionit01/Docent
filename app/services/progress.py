from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Document, Chapter, Lesson, LessonProgress, QuizQuestion


async def compute_progress(document_id: str, db_session_factory) -> dict:
    async with db_session_factory() as session:
        # All lessons for this document (via chapters)
        result = await session.execute(
            select(Lesson.id, Lesson.chapter_id)
            .join(Chapter, Chapter.id == Lesson.chapter_id)
            .where(Chapter.document_id == document_id)
        )
        lesson_rows = result.all()
        total_lessons = len(lesson_rows)

        if total_lessons == 0:
            return {
                "completed_lessons": [],
                "score_by_lesson": {},
                "weak_areas": [],
                "overall_progress": 0,
            }

        lesson_ids = [r[0] for r in lesson_rows]
        chapter_ids = set(r[1] for r in lesson_rows)

        # Progress rows
        result = await session.execute(
            select(LessonProgress).where(LessonProgress.document_id == document_id)
        )
        progress_rows = result.scalars().all()

        score_by_lesson = {p.lesson_id: p.score for p in progress_rows}
        completed_lessons = [p.lesson_id for p in progress_rows]

        # Weak areas: chapters with avg score < 60
        # Group lesson scores by chapter
        lesson_to_chapter = {r[0]: r[1] for r in lesson_rows}
        chapter_scores: dict[str, list[int]] = {}
        for p in progress_rows:
            ch = lesson_to_chapter.get(p.lesson_id)
            if ch:
                chapter_scores.setdefault(ch, []).append(p.score)

        weak_areas = []
        for ch_id, scores in chapter_scores.items():
            avg = sum(scores) / len(scores)
            if avg < 60:
                ch_result = await session.execute(select(Chapter.title).where(Chapter.id == ch_id))
                title = ch_result.scalar()
                if title:
                    weak_areas.append(title)

        overall_progress = int((len(progress_rows) / total_lessons) * 100) if total_lessons else 0

        return {
            "completed_lessons": completed_lessons,
            "score_by_lesson": score_by_lesson,
            "weak_areas": weak_areas,
            "overall_progress": overall_progress,
        }


async def get_next_lesson_id(document_id: str, db_session_factory) -> str | None:
    async with db_session_factory() as session:
        # Get all lessons ordered by chapter order, then lesson id
        result = await session.execute(
            select(Lesson.id, Chapter.order)
            .join(Chapter, Chapter.id == Lesson.chapter_id)
            .where(Chapter.document_id == document_id)
            .order_by(Chapter.order, Lesson.id)
        )
        lessons = result.all()

        result = await session.execute(
            select(LessonProgress.lesson_id).where(LessonProgress.document_id == document_id)
        )
        completed = set(r[0] for r in result.all())

        for lesson_id, _ in lessons:
            if lesson_id not in completed:
                return lesson_id

        return None
