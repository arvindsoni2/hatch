"""Pydantic schemas for the Coach module — sessions, questions, evaluations, feedback."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class SpeechMetrics(BaseModel):
    filler_count: int = 0
    filler_rate: float = 0.0  # fillers per minute (from word timestamps)
    wpm: float = 0.0
    hedging_count: int = 0
    duration_ms: int = 0
    pause_count: int = 0
    star_coverage: float = 0.0  # 0.0–1.0 fraction of STAR sections detected


class VideoMetrics(BaseModel):
    eye_contact_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    head_stability: float = Field(default=0.0, ge=0.0, le=1.0)
    expression: str = "neutral"
    gesture_freq: float = 0.0


# ---------------------------------------------------------------------------
# Session configuration
# ---------------------------------------------------------------------------


class SessionConfig(BaseModel):
    question_count: int = Field(default=10, ge=1, le=20)
    categories: list[str] = Field(default_factory=list)
    recording_mode: str = "text"  # audio | video | text
    difficulty: str = "medium"  # easy | medium | hard
    interviewer_persona: str | None = None


class CreateSessionRequest(BaseModel):
    application_id: str | None = None
    company_name: str
    role_title: str
    jd_text: str | None = None
    config: SessionConfig = Field(default_factory=SessionConfig)


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


class QuestionPresentation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    text: str
    category: str
    difficulty: str
    context: str | None = None
    num: int
    total: int


# ---------------------------------------------------------------------------
# Answer submission
# ---------------------------------------------------------------------------


class SubmitAnswerRequest(BaseModel):
    transcript: str
    speech_metrics: SpeechMetrics | None = None
    video_metrics: VideoMetrics | None = None
    duration_ms: int = 0
    audio_uri: str | None = None  # server-populated for audio submissions; not user-provided


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class AnswerEvaluation(BaseModel):
    scores: dict[str, int] = Field(
        default_factory=dict,
        description="6 dimensions: relevance, star_structure, technical_depth, conciseness, communication, impact_metrics (0-10)",
    )
    overall: float = 0.0
    feedback: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    follow_up_question: str | None = None
    speech_coaching: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Session responses
# ---------------------------------------------------------------------------


class SessionQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_num: int
    text: str
    category: str
    difficulty: str
    context: str | None = None
    model_answer: str | None = None
    order_in_session: int


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    application_id: str | None = None
    company_name: str
    role_title: str
    status: str
    overall_score: float | None = None
    questions: list[SessionQuestionRead] = Field(default_factory=list)
    created_at: datetime


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_name: str
    role_title: str
    status: str
    overall_score: float | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Company research
# ---------------------------------------------------------------------------


class CompanyResearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str
    sector: str | None = None
    website: str | None = None
    description: str | None = None
    recent_news: list[str] = Field(default_factory=list)
    key_products: list[str] = Field(default_factory=list)
    tech_stack_signals: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Feedback report
# ---------------------------------------------------------------------------


class PracticePlanDay(BaseModel):
    day: int
    focus: str
    activity: str
    resource: str | None = None


class QuestionEvaluationSummary(BaseModel):
    question_id: str
    question_text: str
    category: str
    overall_score: float
    scores: dict[str, int]
    strengths: list[str]
    improvements: list[str]


class SessionFeedbackReport(BaseModel):
    session_id: str
    overall_score: float
    category_scores: dict[str, float] = Field(default_factory=dict)
    executive_summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)
    coaching_points: list[str] = Field(default_factory=list)
    practice_plan: list[PracticePlanDay] = Field(default_factory=list)
    question_evaluations: list[QuestionEvaluationSummary] = Field(default_factory=list)
