import json
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Document, Chunk, Chapter
from app.services.llm.client import llm_complete
from app.services.llm.prompts import GOAL_PROMPTS
from app.core.ids import generate_id


ROADMAP_PROMPT = """
You are analyzing a document to create a chapter roadmap for teaching.

Document text (first portion):
{document_text}

Task: Identify logical chapters in this document and create a structured roadmap.
Each chapter should cover a distinct topic or section.

Return JSON exactly:
{{
  "chapters": [
    {{
      "title": "Chapter title, <80 chars",
      "order": 1,
      "summary": "2-3 sentence summary of what this chapter covers, <150 chars"
    }}
  ]
}}
"""


async def generate_roadmap(document_id: str, db_session_factory) -> list[dict]:
    async with db_session_factory() as session:
        doc = await session.get(Document, document_id)
        if not doc or doc.status != "ready":
            return []

        result = await session.execute(
            select(Chunk)
            .where(Chunk.document_id == document_id)
            .order_by(Chunk.page_number)
            .limit(20)
        )
        chunks = result.scalars().all()

        if not chunks:
            return []

        document_text = " ".join(c.content for c in chunks)
        if len(document_text) > 5000:
            document_text = document_text[:5000]

        prompt = ROADMAP_PROMPT.format(document_text=document_text)
        messages = [
            {"role": "system", "content": "You are a curriculum designer. Respond only in JSON."},
            {"role": "user", "content": prompt},
        ]

        result_data = await llm_complete(messages, temperature=0.2, json_mode=True)

        if not result_data or "chapters" not in result_data:
            return []

        chapters_data = result_data["chapters"]
        for ch in chapters_data:
            chapter = Chapter(
                id=generate_id("ch"),
                document_id=document_id,
                title=ch.get("title", "Untitled"),
                order=ch.get("order", 0),
                summary=ch.get("summary", ""),
                lesson_count=1,
            )
            session.add(chapter)

        await session.commit()
        return chapters_data
