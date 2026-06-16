"""API schemas for deterministic outcome learning."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

Confidence = Literal["insufficient", "low", "medium", "high"]


class OutcomeReason(BaseModel):
    signal: str
    value: str
    direction: Literal["positive", "negative"]
    contribution: float
    segment_rate: float
    baseline_rate: float
    sample_size: int
    message: str


class OpportunityScoreRead(BaseModel):
    state: Literal["computed", "not_computed", "disabled"] = "computed"
    job_id: str
    base_fit_score: float
    outcome_adjustment: float = 0.0
    opportunity_score: float
    confidence: Confidence = "insufficient"
    raw_sample_size: int = 0
    effective_sample_size: float = 0.0
    reasons: list[OutcomeReason] = Field(default_factory=list)
    model_version: str = "outcome-v1"
    calculated_at: datetime | None = None


class OutcomeLearningSummary(BaseModel):
    enabled: bool
    model_version: str = "outcome-v1"
    confidence: Confidence
    resolved_applications: int
    effective_sample_size: float
    positive_responses: int
    global_response_rate: float
    minimum_required: int
    additional_required: int
    learning_since: datetime | None
    top_positive_signals: list[OutcomeReason] = Field(default_factory=list)
    top_negative_signals: list[OutcomeReason] = Field(default_factory=list)
    variant_recommendations: list[dict] = Field(default_factory=list)
    variant_performance: dict[str, list[dict]] = Field(default_factory=dict)
    last_recomputed_at: datetime | None = None


class ResetRequest(BaseModel):
    confirmation: str
