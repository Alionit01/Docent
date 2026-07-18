from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Dict
from datetime import datetime

GoalType = Literal["exam", "understand", "implement", "research"]


class Document(BaseModel):
    id: str
    filename: str
    status: Literal["processing", "ready", "failed"]
    page_count: int = Field(ge=1)
    created_at: datetime


class Chunk(BaseModel):
    id: str
    document_id: str
    content: str = Field(min_length=20)
    embedding: Optional[List[float]] = None
    page_number: int
    chapter_hint: Optional[str] = None
    token_count: int


class Chapter(BaseModel):
    id: str
    document_id: str
    title: str
    order: int
    summary: str
    lesson_count: int = 1


class SourceRef(BaseModel):
    page: int
    chunk_id: str
    snippet: str = Field(max_length=300)


class Lesson(BaseModel):
    id: str
    chapter_id: str
    goal_type: GoalType
    title: str
    explanation: str
    analogy: str
    key_points: List[str] = Field(min_length=2, max_length=5)
    source_refs: List[SourceRef] = Field(min_length=1, max_length=4)


class QuizQuestion(BaseModel):
    id: str
    lesson_id: str
    question: str
    options: List[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str


class UserProgress(BaseModel):
    document_id: str
    completed_lessons: List[str] = []
    scores: Dict[str, int] = {}
    weak_areas: List[str] = []
    overall_progress: int = Field(ge=0, le=100)


class UploadResponse(BaseModel):
    id: str
    filename: str
    status: Literal["processing"] = "processing"
    page_count: int


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    lesson_context_id: Optional[str] = None


class Citation(BaseModel):
    page: int
    chunk_id: str
    snippet: str


class AskResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(min_length=1)
    follow_up_questions: List[str] = Field(max_length=3)


class QuizSubmitRequest(BaseModel):
    answers: List[Dict]


class QuizSubmitResponse(BaseModel):
    score: int
    total: int
    results: List[Dict]
    weak_areas: List[str]
    next_lesson_id: Optional[str]


class ErrorResponse(BaseModel):
    detail: str
    code: str
    meta: Optional[Dict] = None
