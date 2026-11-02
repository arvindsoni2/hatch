"""Case and output contracts for the Coach Phase 2 benchmark suite.

Grounding is a stub until ``services/coach_readiness/grounding.py`` lands in P6;
the bench then swaps this local check for the production implementation.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from benchmarks.contracts import StrictModel

Phase2Stage = Literal[
    "explain",
    "brief_enhance",
    "debrief_extract",
    "competency_extract",
]
Dimension = Literal[
    "relevance",
    "structure",
    "specificity",
    "impact",
    "role_depth",
    "clarity",
    "conciseness",
]
Difficulty = Literal["supportive", "realistic", "challenging"]

PHASE2_STAGES: tuple[Phase2Stage, ...] = (
    "explain",
    "brief_enhance",
    "debrief_extract",
    "competency_extract",
)
TASK_TIERS: dict[Phase2Stage, Literal["T", "S"]] = {
    "explain": "S",
    "brief_enhance": "S",
    "debrief_extract": "T",
    "competency_extract": "T",
}
TIER_MAX_DEADLINE_SECONDS = {"T": 60, "S": 180, "L": 300}

_FINGERPRINT = r"^sha256:[0-9a-f]{64}$"


def _word_count(text: str) -> int:
    return len(text.split())


class ExplainExcerpt(StrictModel):
    excerpt_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    session_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    difficulty: Difficulty


class ExplainInput(StrictModel):
    dimension: Dimension
    rubric_description: str = Field(min_length=1)
    excerpts: list[ExplainExcerpt] = Field(min_length=1, max_length=3)


class BriefHeader(StrictModel):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    round_type: Literal["behavioural", "role_specific_verbal", "mixed"]


class BriefStory(StrictModel):
    story_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    competencies: list[str] = Field(min_length=1)
    score: float = Field(ge=0, le=1)


class BriefWatchOut(StrictModel):
    fingerprint: str = Field(min_length=1)
    dimension: Dimension
    evidence: str = Field(min_length=1)


class BriefEnhanceInput(StrictModel):
    brief_id: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=_FINGERPRINT)
    header: BriefHeader
    stories: list[BriefStory] = Field(min_length=1, max_length=3)
    watch_outs: list[BriefWatchOut] = Field(max_length=2)


class DebriefExtractInput(StrictModel):
    debrief_id: str = Field(min_length=1)
    notes: str = Field(min_length=1, max_length=4000)


class CompetencyExtractInput(StrictModel):
    job_id: str = Field(min_length=1)
    job_description: str = Field(min_length=50, max_length=12000)


class ExplainOutput(StrictModel):
    tips: list[str] = Field(min_length=1, max_length=3)

    @field_validator("tips")
    @classmethod
    def tips_are_short(cls, value: list[str]) -> list[str]:
        for tip in value:
            if not tip.strip() or _word_count(tip) > 60:
                raise ValueError("each tip must be 1-60 words")
        return value


class TalkingPoint(StrictModel):
    story_id: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def text_is_short(cls, value: str) -> str:
        if _word_count(value) > 30:
            raise ValueError("talking point must be at most 30 words")
        return value


class WatchOutTip(StrictModel):
    fingerprint: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def text_is_short(cls, value: str) -> str:
        if _word_count(value) > 30:
            raise ValueError("watch-out must be at most 30 words")
        return value


class BriefEnhanceOutput(StrictModel):
    talking_points: list[TalkingPoint] = Field(max_length=3)
    watch_outs: list[WatchOutTip] = Field(max_length=2)


class DebriefExtractOutput(StrictModel):
    questions: list[str] = Field(max_length=20)

    @field_validator("questions")
    @classmethod
    def questions_are_short(cls, value: list[str]) -> list[str]:
        for question in value:
            if not question.strip() or len(question) > 200:
                raise ValueError("each question must be 1-200 characters")
        return value


class CompetencyExtractOutput(StrictModel):
    competencies: list[str] = Field(max_length=4)

    @field_validator("competencies")
    @classmethod
    def competencies_are_short(cls, value: list[str]) -> list[str]:
        for competency in value:
            if not competency.strip() or len(competency) > 40:
                raise ValueError("each competency must be 1-40 characters")
        return value


_INPUT_MODELS = {
    "explain": ExplainInput,
    "brief_enhance": BriefEnhanceInput,
    "debrief_extract": DebriefExtractInput,
    "competency_extract": CompetencyExtractInput,
}
_OUTPUT_MODELS = {
    "explain": ExplainOutput,
    "brief_enhance": BriefEnhanceOutput,
    "debrief_extract": DebriefExtractOutput,
    "competency_extract": CompetencyExtractOutput,
}


def validate_case_input(stage: str, payload: dict[str, Any]) -> Any:
    """Validate one bench case input against its task contract."""
    try:
        model = _INPUT_MODELS[stage]
    except KeyError as exc:
        raise ValueError(f"unknown Phase 2 bench stage: {stage}") from exc
    return model.model_validate(payload)


def validate_output(stage: str, payload: dict[str, Any]) -> Any:
    """Validate one model output against its task contract."""
    try:
        model = _OUTPUT_MODELS[stage]
    except KeyError as exc:
        raise ValueError(f"unknown Phase 2 bench stage: {stage}") from exc
    return model.model_validate(payload)


def grounding_violations(
    stage: str, output: dict[str, Any], case: dict[str, Any]
) -> tuple[str, ...]:
    """Return grounding violations; P6 replaces this with grounding.py."""
    del stage, output, case
    return ()
