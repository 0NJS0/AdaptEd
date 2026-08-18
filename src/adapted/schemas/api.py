from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field

# ---------------------------------------------------------------- auth


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    role: str  # teacher | student
    grade_level: str | None = None
    daily_study_minutes: int | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    grade_level: str | None = None
    daily_study_minutes: int | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- courses


class CourseCreate(BaseModel):
    title: str
    subject: str | None = None
    description: str | None = None
    exam_date: date | None = None


class CourseOut(BaseModel):
    id: str
    teacher_id: str
    title: str
    subject: str | None
    description: str | None
    exam_date: date | None
    status: str
    created_at: datetime
    student_count: int = 0

    model_config = {"from_attributes": True}


class EnrollRequest(BaseModel):
    student_id: str


# ---------------------------------------------------------------- documents


class DocumentOut(BaseModel):
    id: str
    course_id: str
    filename: str
    file_type: str
    size_bytes: int
    page_count: int | None
    status: str
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- curriculum


class TopicOut(BaseModel):
    id: str
    chapter_id: str
    title: str
    order_index: int
    difficulty: float
    description: str | None
    objectives: list[str] = []
    prerequisites: list[str] = []


class ChapterOut(BaseModel):
    id: str
    course_id: str
    title: str
    order_index: int
    source_refs: str | None
    topics: list[TopicOut] = []


class CurriculumOut(BaseModel):
    course_id: str
    chapters: list[ChapterOut] = []


# ---------------------------------------------------------------- study plans


class PlanItemOut(BaseModel):
    id: str | None = None
    topic_id: str
    title: str
    day_index: int
    sequence: int
    estimated_minutes: int
    goal: str
    reason: str
    status: str


class StudyPlanOut(BaseModel):
    id: str
    student_id: str
    course_id: str
    version: int
    exam_date: date | None
    daily_minutes: int
    status: str
    created_at: datetime
    items: list[PlanItemOut] = []


# ---------------------------------------------------------------- lessons


class LessonSection(BaseModel):
    name: str
    content: str


class LessonOut(BaseModel):
    id: str
    course_id: str
    topic_id: str
    student_id: str | None
    level: str
    title: str
    content: dict
    chunks_used: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- quizzes


class QuestionOut(BaseModel):
    id: str
    question_type: str
    prompt: str
    choices: list[str] | None
    difficulty: float
    topic_id: str | None
    explanation: str | None = None


class QuizOut(BaseModel):
    id: str
    course_id: str
    student_id: str | None
    title: str
    quiz_type: str
    status: str
    created_at: datetime
    questions: list[QuestionOut] = []


class QuizGenerateRequest(BaseModel):
    course_id: str
    topic_id: str | None = None
    student_id: str | None = None
    count: int = 10
    difficulty: float = 0.5
    types: list[str] = ["mcq", "true_false", "numerical"]
    quiz_type: str = "assessment"
    title: str | None = None


class QuizSubmitRequest(BaseModel):
    answers: dict[str, Any]  # question_id -> {value: ...}


# ---------------------------------------------------------------- grading


class AnswerGradeOut(BaseModel):
    answer_id: str
    question_id: str
    is_correct: bool
    ai_score: float
    confidence: float
    explanation: str | None
    needs_teacher_review: bool


class GradingResultOut(BaseModel):
    attempt_id: str
    quiz_id: str | None = None
    score: float
    max_score: float
    percentage: float
    answers: list[AnswerGradeOut] = []


# ---------------------------------------------------------------- performance


class MasteryOut(BaseModel):
    topic_id: str
    topic_title: str
    mastery: float
    attempts: int
    status: str


class MisconceptionOut(BaseModel):
    id: str | None = None
    topic_id: str | None
    topic_title: str | None = None
    label: str
    description: str | None
    status: str


class PerformanceOut(BaseModel):
    student_id: str
    course_id: str | None = None
    weak_topics: list[dict] = []
    strong_topics: list[dict] = []
    topic_mastery: list[MasteryOut] = []
    misconceptions: list[MisconceptionOut] = []


# ---------------------------------------------------------------- recommendations


class RecommendationOut(BaseModel):
    id: str
    action: str
    title: str
    reasons: list[str]
    payload: dict
    confidence: float
    needs_teacher_review: bool
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------- agent ops


class AgentMessageOut(BaseModel):
    message_id: str
    task_id: str
    correlation_id: str
    sender: str
    receiver: str
    action: str
    payload: dict
    status: str
    error: str | None
    duration_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentTaskOut(BaseModel):
    id: str
    task_id: str
    correlation_id: str
    workflow: str
    intent: str
    status: str
    error: str | None
    result: dict | None
    retries: int
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int

    model_config = {"from_attributes": True}


class PipelineResult(BaseModel):
    task_id: str
    correlation_id: str
    status: str
    errors: list[str] = []
    context: dict[str, Any] = {}
