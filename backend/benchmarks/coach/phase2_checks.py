"""Case, output and grounding contracts for the Coach Phase 2 benchmark suite.

P6 replaces the grounding checks here with a re-export of
``services/coach_readiness/grounding.py``; until then the bench and the tests
share this implementation.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

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
TASK_OUTPUT_CAPS = {"T": 512, "S": 600, "L": 600}
TIER_MAX_DEADLINE_SECONDS = {"T": 60, "S": 180, "L": 300}
INPUT_MAX_CHARS = {
    "explain": 3_000,
    "brief_enhance": 3_600,
    "debrief_extract": 2_500,
    "competency_extract": 4_500,
}

_FINGERPRINT = r"^sha256:[0-9a-f]{64}$"
_NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_NAME = re.compile(r"\b[A-Z][a-zA-Z0-9'-]{1,}\b")


def _word_count(text: str) -> int:
    return len(text.split())


class ExplainExcerpt(StrictModel):
    excerpt_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1_000)
    session_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    difficulty: Difficulty


class ExplainInput(StrictModel):
    dimension: Dimension
    rubric_description: str = Field(min_length=1, max_length=500)
    excerpts: list[ExplainExcerpt] = Field(min_length=1, max_length=3)


class BriefHeader(StrictModel):
    company: str = Field(min_length=1)
    role: str = Field(min_length=1)
    round_type: Literal["behavioural", "role_specific_verbal", "mixed"]


class BriefStory(StrictModel):
    story_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1_200)
    competencies: list[str] = Field(min_length=1)
    score: float = Field(ge=0, le=1)


class BriefWatchOut(StrictModel):
    fingerprint: str = Field(min_length=1)
    dimension: Dimension
    evidence: str = Field(min_length=1, max_length=500)


class BriefEnhanceInput(StrictModel):
    brief_id: str = Field(min_length=1)
    input_fingerprint: str = Field(pattern=_FINGERPRINT)
    header: BriefHeader
    stories: list[BriefStory] = Field(min_length=1, max_length=3)
    watch_outs: list[BriefWatchOut] = Field(max_length=2)


class DebriefExtractInput(StrictModel):
    debrief_id: str = Field(min_length=1)
    notes: str = Field(min_length=1, max_length=2_500)


class CompetencyExtractInput(StrictModel):
    job_id: str = Field(min_length=1)
    job_description: str = Field(min_length=50, max_length=4_500)


class ExplainOutput(StrictModel):
    tips: list[str] = Field(min_length=1, max_length=3)

    @field_validator("tips")
    @classmethod
    def tips_are_short(cls, value: list[str]) -> list[str]:
        for tip in value:
            if not tip.strip() or _word_count(tip) > 40:
                raise ValueError("each tip must be 1-40 words")
        return value

    @model_validator(mode="after")
    def tips_are_within_total(self) -> "ExplainOutput":
        if sum(_word_count(tip) for tip in self.tips) > 120:
            raise ValueError("tips must total at most 120 words")
        return self


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
    questions: list[str] = Field(max_length=12)

    @field_validator("questions")
    @classmethod
    def questions_are_short(cls, value: list[str]) -> list[str]:
        for question in value:
            if not question.strip() or len(question) > 120:
                raise ValueError("each question must be 1-120 characters")
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


def input_size_chars(stage: str, payload: dict[str, Any]) -> int:
    """Return the task's content size, excluding JSON structure."""
    if stage == "explain":
        return sum(len(item["text"]) for item in payload["excerpts"])
    if stage == "brief_enhance":
        return sum(len(item["text"]) for item in payload["stories"])
    if stage == "debrief_extract":
        return len(payload["notes"])
    if stage == "competency_extract":
        return len(payload["job_description"])
    raise ValueError(f"unknown Phase 2 bench stage: {stage}")


def _numbers(text: str) -> set[str]:
    return {match.group().replace(",", "") for match in _NUMBER.finditer(text)}


def _names(text: str) -> set[str]:
    names: set[str] = set()
    for match in _NAME.finditer(text):
        prefix = text[: match.start()].rstrip()
        if not prefix or prefix.endswith((".", "!", "?", "\n")):
            continue
        names.add(match.group())
    return names


def _text_violations(text: str, source: str, label: str) -> list[str]:
    violations: list[str] = []
    source_numbers = _numbers(source)
    for number in sorted(_numbers(text)):
        if number not in source_numbers:
            violations.append(f"number_not_in_source:{label}:{number}")
    source_casefold = source.casefold()
    for name in sorted(_names(text)):
        if name.casefold() not in source_casefold:
            violations.append(f"name_not_in_source:{label}:{name}")
    return violations


def _brief_violations(output: dict[str, Any], case: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    stories = {item["story_id"]: item["text"] for item in case["stories"]}
    watch_outs = {item["fingerprint"]: item["evidence"] for item in case["watch_outs"]}
    for point in output.get("talking_points", []):
        story_id = str(point.get("story_id", ""))
        if story_id not in stories:
            violations.append(f"unknown_story_id:{story_id}")
        else:
            violations.extend(
                _text_violations(
                    str(point.get("text", "")),
                    stories[story_id],
                    f"story:{story_id}",
                )
            )
    for watch_out in output.get("watch_outs", []):
        fingerprint = str(watch_out.get("fingerprint", ""))
        if fingerprint not in watch_outs:
            violations.append(f"unknown_fingerprint:{fingerprint}")
        else:
            violations.extend(
                _text_violations(
                    str(watch_out.get("text", "")),
                    watch_outs[fingerprint],
                    f"watch_out:{fingerprint}",
                )
            )
    return violations


def grounding_violations(
    stage: str, output: dict[str, Any], case: dict[str, Any]
) -> tuple[str, ...]:
    """Return schema, citation, numeric and naming violations for one output."""
    try:
        valid = validate_output(stage, output)
    except ValidationError as exc:
        return tuple(
            f"schema:{'.'.join(str(item) for item in error['loc'])}"
            for error in exc.errors()
        )

    if stage == "brief_enhance":
        return tuple(_brief_violations(valid.model_dump(), case))
    if stage == "explain":
        source = " ".join(
            [case["rubric_description"]]
            + [item["text"] for item in case["excerpts"]]
        )
        texts = valid.tips
    elif stage == "debrief_extract":
        source = case["notes"]
        texts = valid.questions
    else:
        source = case["job_description"]
        texts = valid.competencies

    violations: list[str] = []
    for text in texts:
        violations.extend(_text_violations(text, source, stage))
    return tuple(violations)
