"""Pydantic schemas for the Coach module — sessions, questions, evaluations, feedback."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self

from ..services.coach_contracts import CoachDiagnostic


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


class VoiceToneResult(BaseModel):
    """Dimensional speech-emotion output from audeering (or compatible) analyser.

    arousal   — energy / activation (0=calm, 1=excited)
    valence   — positive vs negative affect (0=negative, 1=positive)
    dominance — assertiveness / confidence (0=submissive, 1=dominant)
    """
    arousal: float = Field(default=0.0, ge=0.0, le=1.0)
    valence: float = Field(default=0.0, ge=0.0, le=1.0)
    dominance: float = Field(default=0.0, ge=0.0, le=1.0)
    sample_count: int = 0  # number of audio samples analysed


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
    interview_date: str | None = None  # ISO date string, stored in config JSON
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
    requirement_id: str | None = None
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


ScoreBand = Literal["strong", "good", "needs_work", "weak"]


class RubricDimension(BaseModel):
    """One dimension in the session rubric — score + band + evidence + drill."""
    score: int = Field(default=0, ge=0, le=10)
    score_band: ScoreBand = "needs_work"
    evidence: list[str] = Field(default_factory=list, description="1-2 concrete examples from the answer")
    drill: str = ""  # recommended practice drill for improvement


class SessionRubric(BaseModel):
    """Full per-dimension rubric for a session answer.

    Dimensions appear only when the underlying signal exists:
    - content dims (relevance, star_structure, …): always present after LLM eval
    - delivery: only when SpeechMetrics / word timestamps are available
    - vocal_confidence: only when VoiceToneResult is available
    - presence: only when face data is available (Phase D opt-in)
    """
    dimensions: dict[str, RubricDimension] = Field(default_factory=dict)
    focus_for_next_session: str = ""
    diagnostic: CoachDiagnostic | None = None


class ModelAnswerResult(BaseModel):
    """Internal model-answer result; the public question keeps text only."""

    model_answer: str = ""
    star_breakdown: dict[str, str] = Field(default_factory=dict)
    evidence_references: list[str] = Field(default_factory=list)
    diagnostic: CoachDiagnostic


class AnswerEvaluation(BaseModel):
    evaluation_state: Literal["completed", "unavailable", "invalid"] = "completed"
    diagnostic: CoachDiagnostic | None = None
    scores: dict[str, int] = Field(
        default_factory=dict,
        description="6 dimensions: relevance, star_structure, technical_depth, conciseness, communication, impact_metrics (0-10)",
    )
    overall: float | None = 0.0
    feedback: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    follow_up_question: str | None = None
    speech_coaching: list[str] = Field(default_factory=list)
    rubric: SessionRubric | None = None

    @model_validator(mode="after")
    def validate_score_state(self) -> Self:
        if self.evaluation_state == "completed":
            if self.overall is None:
                raise ValueError("completed evaluations require an overall score")
        elif self.scores or self.overall is not None or self.rubric is not None:
            raise ValueError(
                "unavailable or invalid evaluations cannot contain scores or a rubric"
            )
        return self


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
    requirement_id: str | None = None
    model_answer_diagnostics: CoachDiagnostic | None = None
    order_in_session: int


class TechnicalDrill(BaseModel):
    """A worked-example drill for a technical question."""
    question_id: str
    question_text: str
    walkthrough: str       # worked example
    drill_prompt: str      # "explain your approach out loud" prompt
    category: str


class ProgressTrendItem(BaseModel):
    """Per-session progress data for a session chain."""
    session_id: str
    created_at: datetime
    overall_score: float | None
    rubric_scores: dict[str, int]   # dim_name → score
    focus_areas: list[str]


class PlanFollowUpResponse(BaseModel):
    """Response after planning a follow-up session."""
    followup_session_id: str
    focus_areas: list[str]
    message: str


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
    interview_date: str | None = None  # set for manual sessions without an application_id
    # Phase C fields
    coach_mode: str | None = None
    rubric: SessionRubric | None = None
    signals: dict | None = None
    parent_session_id: str | None = None
    focus_areas: list[str] | None = None
    technical_drills: list[TechnicalDrill] = Field(default_factory=list)


class SessionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_name: str
    role_title: str
    status: str
    overall_score: float | None = None
    created_at: datetime
    started_at: datetime | None = None


# ---------------------------------------------------------------------------
# Company research
# ---------------------------------------------------------------------------


class ResearchSource(BaseModel):
    """A retrieved public source used to support company research facts."""

    source_id: str
    title: str
    url: str
    retrieved_at: datetime


class CompanyResearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_name: str
    sector: str | None = None
    website: str | None = None
    description: str | None = None
    recent_news: list[str] = Field(default_factory=list)
    key_products: list[str] = Field(default_factory=list)
    tech_stack_signals: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    retrieved_at: datetime | None = None
    verification_state: Literal[
        "verified",
        "partially_verified",
        "not_verified",
    ] = "not_verified"


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
    report_state: Literal["completed", "fallback"] = "completed"
    diagnostic: CoachDiagnostic | None = None
    overall_score: float | None
    question_count_total: int = 0
    question_count_evaluated: int = 0
    question_count_skipped: int = 0
    question_count_unavailable: int = 0
    question_count_unanswered: int = 0
    category_scores: dict[str, float] = Field(default_factory=dict)
    executive_summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)
    coaching_points: list[str] = Field(default_factory=list)
    practice_plan: list[PracticePlanDay] = Field(default_factory=list)
    question_evaluations: list[QuestionEvaluationSummary] = Field(default_factory=list)
