"""Question Bank API schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

QuestionBankItemType = Literal[
    "interview_question",
    "star_story",
    "proof_point",
    "company_research_note",
    "role_specific_answer",
]
QuestionBankSource = Literal["manual", "interview_prep", "cv_import", "ai_suggested"]
QuestionBankConfidence = Literal["draft", "reviewed", "final"]


class QuestionBankCreate(BaseModel):
    type: QuestionBankItemType = "interview_question"
    question: str | None = None
    title: str = Field(min_length=1, max_length=256)
    answer_draft: str = Field(min_length=1)
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    skills: list[str] | None = None
    tags: list[str] | None = None
    seniority: str | None = None
    role_family: str | None = None
    linked_applications: list[str] | None = None
    source: QuestionBankSource = "manual"
    confidence: QuestionBankConfidence = "draft"

    @field_validator(
        "question",
        "title",
        "answer_draft",
        "situation",
        "task",
        "action",
        "result",
        "seniority",
        "role_family",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        return trimmed or None


class QuestionBankUpdate(BaseModel):
    type: QuestionBankItemType | None = None
    question: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=256)
    answer_draft: str | None = Field(default=None, min_length=1)
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    skills: list[str] | None = None
    tags: list[str] | None = None
    seniority: str | None = None
    role_family: str | None = None
    linked_applications: list[str] | None = None
    confidence: QuestionBankConfidence | None = None


class QuestionBankFromInterviewAnswer(BaseModel):
    session_id: str
    question_id: str
    answer_draft: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=256)
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    skills: list[str] | None = None
    tags: list[str] | None = None
    confidence: QuestionBankConfidence = "draft"


class QuestionBankRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    question: str | None = None
    title: str
    answer_draft: str
    situation: str | None = None
    task: str | None = None
    action: str | None = None
    result: str | None = None
    skills: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    seniority: str | None = None
    role_family: str | None = None
    linked_applications: list[str] = Field(default_factory=list)
    source: str
    confidence: str
    source_session_id: str | None = None
    source_question_id: str | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class QuestionBankList(BaseModel):
    items: list[QuestionBankRead]
    total: int
    skip: int
    limit: int
