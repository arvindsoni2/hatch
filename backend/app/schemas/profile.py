"""Pydantic schema for profile.yaml validation.

All user-specific configuration lives in profile.yaml. This schema validates
the structure on load so agents fail fast with clear errors rather than KeyErrors.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CandidateConfig(BaseModel):
    name: str = ""
    title: str = ""
    years_experience: int = 0
    summary: str = ""


class LocationConfig(BaseModel):
    city: str = ""
    country: str = ""
    radius_miles: int = 30
    remote_preference: Literal["onsite", "hybrid", "remote", "any"] = "any"


class SearchConfig(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    locations: list[LocationConfig] = Field(default_factory=list)
    contract_type: Literal["contract", "permanent", "freelance", "any"] = "any"


class CompensationConfig(BaseModel):
    min_rate: float = 0
    max_rate: float = 0
    rate_type: Literal["daily", "hourly", "annual", "monthly"] = "daily"
    currency: str = ""  # set by locale pack (GBP, INR, EUR, AED, …)
    # Locale-specific legal/compliance preferences (e.g. contract_status, work_auth, notice_period)
    legal_preferences: dict[str, str] = Field(default_factory=dict)


class SkillsConfig(BaseModel):
    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class DomainsConfig(BaseModel):
    preferred: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)


class ProofPoint(BaseModel):
    id: str
    summary: str
    context: str = ""
    metrics: str = ""
    tags: list[str] = Field(default_factory=list)


class JobBoardConfig(BaseModel):
    name: str
    enabled: bool = True
    scraper: str = ""
    search_params: dict[str, Any] = Field(default_factory=dict)


class ScoringWeights(BaseModel):
    skill_match: float = 0.35
    experience_match: float = 0.30
    rate_match: float = 0.20
    location_match: float = 0.15

    @field_validator("skill_match", "experience_match", "rate_match", "location_match")
    @classmethod
    def must_be_fraction(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("weight must be between 0.0 and 1.0")
        return v


class ScoringConfig(BaseModel):
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    shortlist_threshold: float = 0.75
    method: Literal["auto", "llm", "local", "hybrid"] = "auto"
    hybrid_llm_top_pct: float = 0.20  # fraction of top-scoring local jobs to send to LLM

    @field_validator("shortlist_threshold")
    @classmethod
    def must_be_fraction(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("shortlist_threshold must be between 0.0 and 1.0")
        return v


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "google_genai", "google_vertexai", "ollama", "azure_openai", "aws_bedrock", "llamacpp"] = "ollama"
    triage_model: str = ""
    primary_model: str = ""
    api_key_env: str = ""
    base_url: str | None = None
    temperature: float = 0.3
    max_retries: int = 3
    track_costs: bool = False
    monthly_budget: float = 0.0
    currency: str = "USD"  # currency for budget display; override per locale


class PreferencesConfig(BaseModel):
    scrape_interval_hours: int = 4
    max_tailor_batch: int = 5
    follow_up_days: list[int] = Field(default_factory=lambda: [5, 10, 15])
    locale: str = "en-GB"  # display/date locale (BCP-47)
    archive_after_days: int = 30  # auto-archive jobs older than this
    max_job_age_days: int = 60  # hide jobs older than this from the approval queue


class Profile(BaseModel):
    """Root schema for profile.yaml. Validates the full user configuration."""

    locale: str = "uk"  # geographic locale ID (matches locales/*.yaml id field)
    candidate: CandidateConfig = Field(default_factory=CandidateConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    compensation: CompensationConfig = Field(default_factory=CompensationConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    domains: DomainsConfig = Field(default_factory=DomainsConfig)
    proof_points: list[ProofPoint] = Field(default_factory=list)
    master_cv_path: str = "./data/master_cv.json"
    job_boards: list[JobBoardConfig] = Field(default_factory=list)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    preferences: PreferencesConfig = Field(default_factory=PreferencesConfig)

    def is_complete(self) -> bool:
        """Return True if the profile has enough data for agents to run."""
        return bool(
            self.candidate.name
            and self.search.target_roles
            and self.search.locations
        )
