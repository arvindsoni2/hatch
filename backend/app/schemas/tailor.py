"""Pydantic schemas for the Tailor module — JD analysis, CV tailoring, cover letter, ATS scoring."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# JD Analysis sub-schemas
# ---------------------------------------------------------------------------


class ContractDetails(BaseModel):
    contract_type: str | None = None
    rate_range: str | None = None
    ir35_status: str | None = None
    duration: str | None = None
    location: str | None = None
    remote_policy: str | None = None
    start_date: str | None = None


class CompanyContext(BaseModel):
    company_name: str | None = None
    sector: str | None = None
    size: str | None = None
    culture_indicators: list[str] = Field(default_factory=list)


class Requirements(BaseModel):
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    years_experience: int | str | None = None


class ATSKeywords(BaseModel):
    technical: list[str] = Field(default_factory=list)
    methodologies: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    domain: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class ToneAnalysis(BaseModel):
    formality: str = "professional"
    emphasis: str = "technical"
    red_flags: list[str] = Field(default_factory=list)


class JDAnalysisResult(BaseModel):
    role_title: str
    seniority_level: str | None = None
    contract_details: ContractDetails = Field(default_factory=ContractDetails)
    company_context: CompanyContext = Field(default_factory=CompanyContext)
    requirements: Requirements = Field(default_factory=Requirements)
    responsibilities: list[str] = Field(default_factory=list)
    ats_keywords: ATSKeywords = Field(default_factory=ATSKeywords)
    tone_analysis: ToneAnalysis = Field(default_factory=ToneAnalysis)
    raw_text_length: int | None = None


# ---------------------------------------------------------------------------
# Skill match
# ---------------------------------------------------------------------------


class SkillMatchResult(BaseModel):
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    match_pct: float = 0.0
    domain_match: bool = False
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CV tailoring
# ---------------------------------------------------------------------------


class TailoredExperience(BaseModel):
    role: str
    company: str
    period: str
    achievements: list[str] = Field(default_factory=list)


class TailoredEducation(BaseModel):
    qualification: str = ""
    institution: str = ""
    year: str = ""
    field: str = ""
    location: str = ""
    details: list[str] = Field(default_factory=list)


class TailoredCVResult(BaseModel):
    summary: str
    skills: list[dict[str, Any]] = Field(default_factory=list)
    experience: list[TailoredExperience] = Field(default_factory=list)
    education: list[TailoredEducation] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    ats_keywords_embedded: list[str] = Field(default_factory=list)
    tailoring_notes: str = ""
    structural_warnings: list[str] = Field(default_factory=list)
    validation_status: Literal["passed", "repaired", "failed"] = "passed"
    blocking_issues: list[str] = Field(default_factory=list)
    fabrication_warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Cover letter
# ---------------------------------------------------------------------------


class CoverLetterResult(BaseModel):
    subject_line: str
    greeting: str
    body_paragraphs: list[str] = Field(default_factory=list)
    sign_off: str
    word_count: int
    key_keywords_used: list[str] = Field(default_factory=list)
    grounding_issues: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ATS scoring
# ---------------------------------------------------------------------------


class KeywordMatch(BaseModel):
    keyword: str
    found: bool
    context: str | None = None


class ATSScoreResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    target_score: int = 80
    passed_target: bool = False
    attempts: int = 1
    algorithmic_score: float | None = None
    semantic_score: float | None = None
    keyword_matches: list[KeywordMatch] = Field(default_factory=list)
    format_warnings: list[str] = Field(default_factory=list)
    missing_critical: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    grounded_improvements: list[str] = Field(default_factory=list)
    unsupported_gaps: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Request / response wrappers
# ---------------------------------------------------------------------------


class TailorRequest(BaseModel):
    application_id: str | None = None   # None = auto-create from job metadata
    variant: str = "A"
    generate_cv: bool = True
    generate_cover_letter: bool = True
    custom_instructions: str | None = None
    template_id: str | None = None
    regeneration_instruction: str | None = None
    jd_text: str | None = None
    # Used when application_id is None to create a pipeline entry automatically
    job_title: str | None = None
    company_name: str | None = None
    job_url: str | None = None


class JDAnalysisResponse(BaseModel):
    job_id: str
    analysis: JDAnalysisResult
    skill_match: SkillMatchResult | None = None


class TailorResultBundle(BaseModel):
    application_id: str
    cv_document_id: str | None = None
    cl_document_id: str | None = None
    ats_score: ATSScoreResult | None = None
    analysis: JDAnalysisResult | None = None
    skill_match: SkillMatchResult | None = None
    review: dict[str, Any] | None = None


class RegenerateSectionRequest(BaseModel):
    document_id: str
    section: str  # "summary" | "paragraph_0" .. "paragraph_3" | "skills"
    instruction: str
