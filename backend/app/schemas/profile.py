"""Pydantic schema for profile.yaml validation.

All user-specific configuration lives in profile.yaml. This schema validates
the structure on load so agents fail fast with clear errors rather than KeyErrors.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CandidateConfig(BaseModel):
    name: str = ""
    title: str = ""
    years_experience: int = 0
    summary: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    current_employer: str = ""


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


class TailoringConfig(BaseModel):
    ats_target_score: int = Field(default=80, ge=60, le=100)
    ats_retry_limit: int = Field(default=1, ge=0, le=3)
    default_template_id: Literal[
        "ats_classic", "professional_2_page", "compact_one_page", "career_switcher"
    ] = "ats_classic"
    resume_design_defaults: dict = Field(default_factory=dict)


class ASRConfig(BaseModel):
    provider: Literal["faster_whisper", "qwen3_asr", "web_speech", "deepgram"] = "faster_whisper"
    model: str = "small"
    compute_type: str = "int8"
    language: str = "auto"


class VoiceEmotionConfig(BaseModel):
    provider: Literal["audeering", "emotion2vec", "hume", "none"] = "none"
    model: str = "wav2vec2-large-robust-12-ft-emotion-msp-dim"


class FaceConfig(BaseModel):
    provider: Literal["mediapipe_browser", "emotiefflib", "hume", "none"] = "mediapipe_browser"
    enabled: bool = False


class TTSConfig(BaseModel):
    provider: Literal["none", "piper", "kokoro", "qwen3_tts", "elevenlabs"] = "none"
    voice: str = "en_GB-default"


class PerceptionConfig(BaseModel):
    asr: ASRConfig = Field(default_factory=ASRConfig)
    voice_emotion: VoiceEmotionConfig = Field(default_factory=VoiceEmotionConfig)
    face: FaceConfig = Field(default_factory=FaceConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)


OutcomeSignal = Literal["source", "role_family", "seniority", "working_pattern", "employment_type", "freshness"]


class OutcomeLearningConfig(BaseModel):
    enabled: bool = True
    minimum_total_applications: int = Field(default=15, ge=5)
    minimum_segment_size: int = Field(default=5, ge=3)
    maximum_score_adjustment: float = Field(default=0.10, ge=0.0, le=0.20)
    maximum_signal_adjustment: float = Field(default=0.04, ge=0.0)
    no_response_after_days: int = Field(default=35, ge=14, le=120)
    recency_half_life_days: int = Field(default=120, ge=30, le=730)
    enabled_signals: list[OutcomeSignal] = Field(default_factory=lambda: [
        "source", "role_family", "seniority", "working_pattern", "employment_type", "freshness",
    ])
    learning_since: datetime | None = None

    @field_validator("enabled_signals")
    @classmethod
    def deduplicate_signals(cls, values: list[OutcomeSignal]) -> list[OutcomeSignal]:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def validate_thresholds(self) -> "OutcomeLearningConfig":
        if self.minimum_segment_size > self.minimum_total_applications:
            raise ValueError("minimum_segment_size cannot exceed minimum_total_applications")
        if self.maximum_signal_adjustment > self.maximum_score_adjustment:
            raise ValueError("maximum_signal_adjustment cannot exceed maximum_score_adjustment")
        return self


class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "google_genai", "google_vertexai", "ollama", "azure_openai", "aws_bedrock", "llamacpp"] = "llamacpp"
    triage_model: str = "qwen3.5-0.8b-q8_0"
    primary_model: str = "qwen3.5-4b-instruct-q4_k_m"
    api_key_env: str = ""
    base_url: str | None = "http://llm-primary:8080/v1"
    triage_base_url: str = "http://llm-triage:8081/v1"  # separate endpoint for the triage model; falls back to base_url if empty
    temperature: float = 0.3
    max_retries: int = 3
    track_costs: bool = False
    monthly_budget: float = 0.0
    currency: str = "USD"  # currency for budget display; override per locale
    reasoning: bool = False  # enable thinking tokens for Ollama reasoners (e.g. gemma4)
    top_p: float | None = None  # nucleus sampling; None = use model default
    top_k: int | None = None  # top-k sampling; None = use model default


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
    tailoring: TailoringConfig = Field(default_factory=TailoringConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    preferences: PreferencesConfig = Field(default_factory=PreferencesConfig)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    outcome_learning: OutcomeLearningConfig = Field(default_factory=OutcomeLearningConfig)

    def is_complete(self) -> bool:
        """Return True if the profile has enough data for agents to run."""
        return bool(
            self.candidate.name
            and self.search.target_roles
            and self.search.locations
        )
