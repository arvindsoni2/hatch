"""Strict public schemas for the Phase 1 conversational Coach experience."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    StringConstraints,
    TypeAdapter,
    create_model,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from typing_extensions import Self

from ..services.coach_conversational_contracts import (
    CONVERSATION_COMMAND_CONTRACT,
    CONVERSATION_COMMAND_RESULT_CONTRACT,
    DELIVERY_POLICY,
    EVIDENCE_GROUNDING_CONTRACT,
    ERROR_REGISTRY,
    FOLLOW_UP_CONTRACT,
    LIVE_VIEW_CONTRACT,
    REPORT_CONTRACT,
    RUBRIC_CONTRACT,
)
from ..services.coach_conversation_state import TRANSITIONS


SAFE_TOKEN_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$"
SAFE_TOKEN_RE = re.compile(SAFE_TOKEN_PATTERN)
LOCALE_RE = re.compile(
    r"^[A-Za-z]{2,3}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?$"
)
INDUSTRY_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
RFC3339_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)

SafeToken: TypeAlias = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=SAFE_TOKEN_PATTERN),
]
NonNegativeInt: TypeAlias = Annotated[int, Field(ge=0)]

ConversationalLevel = Literal[
    "needs_work", "developing", "interview_ready", "strong", "not_assessed"
]
DeliverySeverity = Literal["none", "moderate", "material", "severe"]
DeliveryMetricFamily = Literal[
    "pace", "fillers_per_minute", "long_pauses", "hedging", "restarts"
]

ExperienceVersion = Literal["legacy_v1", "conversational_v1"]
InterviewType = Literal["behavioural", "role_specific_verbal", "mixed"]
ConversationalDifficulty = Literal["supportive", "realistic", "challenging"]
RoleLevel = Literal[
    "entry",
    "mid",
    "senior",
    "lead",
    "principal",
    "manager",
    "director",
    "executive",
    "unspecified",
]
RoleFamily = Literal[
    "software_engineering",
    "solution_architecture",
    "enterprise_architecture",
    "data_ai",
    "cloud_devops_platform",
    "cybersecurity",
    "product_management",
    "project_program_management",
    "agile_delivery",
    "business_analysis",
    "consulting",
    "operations",
    "commercial",
    "general",
    "other",
]
FocusArea = Literal[
    "leadership",
    "stakeholder_management",
    "delivery_execution",
    "problem_solving",
    "technical_depth",
    "architecture",
    "communication",
    "commercial_awareness",
    "culture_values",
    "role_motivation",
]
AnswerMode = Literal["audio", "text"]
AudioRetentionPolicy = Literal["delete_after_processing", "retain_until_deleted"]
TranscriptRetentionPolicy = Literal["retain"]
AudioUploadResult = Literal["pending", "completed", "failed", "deleted"]
AudioRetentionState = Literal[
    "not_applicable",
    "temporary",
    "retained",
    "delete_pending",
    "deleted",
    "delete_failed",
]
AttemptStageName = Literal[
    "audio_persist",
    "transcription",
    "speech_analysis",
    "content_evaluation",
    "evidence_grounding",
    "follow_up_decision",
    "coaching_enrichment",
    "audio_cleanup",
]
AttemptStageState = Literal[
    "not_started",
    "pending",
    "running",
    "completed",
    "reused",
    "not_applicable",
    "unavailable",
    "failed_retryable",
    "failed_terminal",
]
LowercaseSha256: TypeAlias = Annotated[
    str, StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
]
PositiveByteSize: TypeAlias = Annotated[int, Field(gt=0)]
BoundedMimeType: TypeAlias = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class StrictContractModel(BaseModel):
    """Base for new contracts: reject unknown fields and non-JSON numbers."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class TranscriptEvidenceSpan(StrictContractModel):
    transcript_start: NonNegativeInt
    transcript_end: Annotated[int, Field(gt=0)]
    excerpt: Annotated[str, Field(min_length=1, max_length=2_000)]

    @model_validator(mode="after")
    def require_half_open_span(self) -> Self:
        if self.transcript_start >= self.transcript_end:
            raise ValueError("transcript evidence span must be non-empty")
        return self


class DeliveryObservation(StrictContractModel):
    measured_value: int | float
    threshold_bucket: str
    severity: DeliverySeverity


class ConversationalRubricDimension(StrictContractModel):
    level: ConversationalLevel
    evidence: Annotated[list[TranscriptEvidenceSpan], Field(max_length=2)] = Field(
        default_factory=list
    )
    rationale: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None
    improvement: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None
    observations: dict[DeliveryMetricFamily, DeliveryObservation] = Field(
        default_factory=dict
    )


def _normalized_bounded_text(
    value: str, *, field_name: str, minimum: int, maximum: int
) -> str:
    normalized = (
        unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    )
    normalized = normalized.strip()
    if not minimum <= len(normalized) <= maximum:
        raise ValueError(
            f"{field_name} must contain between {minimum} and {maximum} Unicode code points"
        )
    return normalized


def normalize_locale(value: str) -> str:
    """Validate and canonicalize the intentionally constrained BCP-47 subset."""

    value = value.strip()
    if not LOCALE_RE.fullmatch(value):
        raise ValueError("locale is outside the supported BCP-47 subset")
    parts = value.split("-")
    normalized = [parts[0].lower()]
    cursor = 1
    if cursor < len(parts) and len(parts[cursor]) == 4:
        normalized.append(parts[cursor].title())
        cursor += 1
    if cursor < len(parts):
        region = parts[cursor]
        normalized.append(region if region.isdigit() else region.upper())
    return "-".join(normalized)


class EvidenceSelection(StrictContractModel):
    application_cv: Literal["approved_only", "current_if_no_approved", "none"]
    master_cv: Literal["include", "exclude"]
    question_bank: Literal["reviewed_final_only", "include_drafts", "exclude"]
    selected_question_bank_record_ids: Annotated[
        list[SafeToken], Field(max_length=50)
    ] = Field(default_factory=list)
    company_research: Literal["include_if_fresh", "exclude"]
    draft_evidence_consent: bool = False

    @field_validator("selected_question_bank_record_ids")
    @classmethod
    def require_unique_record_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("selected question bank record identifiers must be unique")
        return value

    @model_validator(mode="after")
    def require_draft_consent(self) -> Self:
        if self.question_bank == "include_drafts" and not self.draft_evidence_consent:
            raise ValueError("coach_draft_evidence_consent_required")
        return self


class RetentionPolicy(StrictContractModel):
    audio: AudioRetentionPolicy = "delete_after_processing"
    transcript: TranscriptRetentionPolicy = "retain"


def project_retention_summary(value: object) -> dict[str, str] | None:
    """Return only a complete, contract-valid persisted retention summary."""
    if not isinstance(value, Mapping):
        return None
    try:
        return RetentionPolicy.model_validate(
            {field: value[field] for field in ("audio", "transcript") if field in value}
        ).model_dump(mode="json")
    except ValueError:
        return None


class ConversationalConfig(StrictContractModel):
    interview_type: InterviewType
    difficulty: ConversationalDifficulty
    duration_minutes: Annotated[int, Field(ge=10, le=90)] = 30
    planned_question_count: Annotated[int, Field(ge=3, le=12)] | None = None
    role_family: RoleFamily
    role_family_label: str | None = None
    role_level: RoleLevel
    industry: str | None = None
    locale: str = "en-GB"
    focus_areas: Annotated[list[FocusArea], Field(max_length=6)] = Field(
        default_factory=list
    )
    allowed_answer_modes: Annotated[list[AnswerMode], Field(min_length=1, max_length=2)]
    evidence_selection: EvidenceSelection
    retention: RetentionPolicy = Field(default_factory=RetentionPolicy)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str) -> str:
        return normalize_locale(value)

    @field_validator("role_family_label")
    @classmethod
    def normalize_role_family_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalized_bounded_text(
            value, field_name="role_family_label", minimum=1, maximum=80
        )

    @field_validator("industry")
    @classmethod
    def validate_industry(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not 1 <= len(value) <= 64 or not INDUSTRY_RE.fullmatch(value):
            raise ValueError("industry must be a normalized slug of 1 to 64 characters")
        return value

    @field_validator("focus_areas", "allowed_answer_modes")
    @classmethod
    def require_unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("values must be unique")
        return value

    @model_validator(mode="after")
    def validate_role_family_label(self) -> Self:
        if self.role_family == "other" and self.role_family_label is None:
            raise ValueError("role_family_label is required for role_family other")
        if self.role_family != "other" and self.role_family_label is not None:
            raise ValueError("role_family_label is valid only for role_family other")
        return self


class EmptyCommandPayload(StrictContractModel):
    pass


class StartPayload(EmptyCommandPayload):
    pass


class BeginAnswerPayload(StrictContractModel):
    recording_type: AnswerMode
    client_attempt_id: SafeToken


class FinishAnswerPayload(StrictContractModel):
    attempt_id: SafeToken
    transcript: str | None = None
    upload_id: SafeToken | None = None

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalized_bounded_text(
            value, field_name="transcript", minimum=1, maximum=30_000
        )

    @model_validator(mode="after")
    def require_one_answer_source(self) -> Self:
        if (self.transcript is None) == (self.upload_id is None):
            raise ValueError("exactly one of transcript or upload_id is required")
        return self


class KeepSpeakingPayload(StrictContractModel):
    attempt_id: SafeToken


class PausePayload(EmptyCommandPayload):
    pass


class ResumePayload(EmptyCommandPayload):
    pass


class CancelAttemptPayload(StrictContractModel):
    attempt_id: SafeToken


class RecordCaptureHardStopPayload(StrictContractModel):
    attempt_id: SafeToken


class RetryAnswerPayload(StrictContractModel):
    question_id: SafeToken | None = None


class RetrySetupPayload(EmptyCommandPayload):
    pass


class RebuildPlanPayload(StrictContractModel):
    refresh_sources: Literal[True]


class RetryProcessingPayload(EmptyCommandPayload):
    pass


class RetryReportPayload(EmptyCommandPayload):
    pass


class RequestHintPayload(StrictContractModel):
    hint_type: Literal[
        "star_structure",
        "competency_reminder",
        "experience_category",
        "clarify_question",
    ]


class RequestCoachingPayload(StrictContractModel):
    attempt_id: SafeToken


class ReturnToReviewPayload(EmptyCommandPayload):
    pass


class EditTranscriptPayload(StrictContractModel):
    attempt_id: SafeToken
    transcript: str
    edit_reason: Literal["transcription_error"]

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, value: str) -> str:
        return _normalized_bounded_text(
            value, field_name="transcript", minimum=1, maximum=30_000
        )


class AcceptAttemptPayload(StrictContractModel):
    attempt_id: SafeToken


class RecordSelfAssessmentPayload(StrictContractModel):
    attempt_id: SafeToken
    comfort_level: Literal["low", "medium", "high"]
    felt_complete: bool
    note: str | None = None

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalized_bounded_text(
            value, field_name="note", minimum=1, maximum=1_000
        )


class UpdateRetentionPayload(StrictContractModel):
    audio: AudioRetentionPolicy


class SkipQuestionPayload(EmptyCommandPayload):
    pass


class EndSessionPayload(StrictContractModel):
    unaccepted_attempt_action: Literal[
        "accept_attempt", "exclude_attempt", "not_applicable"
    ]
    attempt_id: SafeToken | None = None
    paused_draft_action: Literal["discard_draft"] | None = None

    @model_validator(mode="after")
    def validate_attempt_selection(self) -> Self:
        if (
            self.unaccepted_attempt_action == "accept_attempt"
            and self.attempt_id is None
        ):
            raise ValueError("accept_attempt requires attempt_id")
        if (
            self.unaccepted_attempt_action != "accept_attempt"
            and self.attempt_id is not None
        ):
            raise ValueError("attempt_id is valid only when accepting an attempt")
        return self


class DeleteAudioPayload(StrictContractModel):
    attempt_id: SafeToken


class DeleteTranscriptPayload(StrictContractModel):
    attempt_id: SafeToken


CommandType = Literal[
    "start",
    "begin_answer",
    "finish_answer",
    "keep_speaking",
    "pause",
    "resume",
    "cancel_attempt",
    "record_capture_hard_stop",
    "retry_answer",
    "retry_setup",
    "rebuild_plan",
    "retry_processing",
    "retry_report",
    "request_hint",
    "request_coaching",
    "return_to_review",
    "edit_transcript",
    "accept_attempt",
    "record_self_assessment",
    "update_retention",
    "skip_question",
    "end_session",
    "delete_audio",
    "delete_transcript",
]

CommandPayload = (
    StartPayload
    | BeginAnswerPayload
    | FinishAnswerPayload
    | KeepSpeakingPayload
    | PausePayload
    | ResumePayload
    | CancelAttemptPayload
    | RecordCaptureHardStopPayload
    | RetryAnswerPayload
    | RetrySetupPayload
    | RebuildPlanPayload
    | RetryProcessingPayload
    | RetryReportPayload
    | RequestHintPayload
    | RequestCoachingPayload
    | ReturnToReviewPayload
    | EditTranscriptPayload
    | AcceptAttemptPayload
    | RecordSelfAssessmentPayload
    | UpdateRetentionPayload
    | SkipQuestionPayload
    | EndSessionPayload
    | DeleteAudioPayload
    | DeleteTranscriptPayload
)

COMMAND_PAYLOAD_TYPES: dict[str, type[StrictContractModel]] = {
    "start": StartPayload,
    "begin_answer": BeginAnswerPayload,
    "finish_answer": FinishAnswerPayload,
    "keep_speaking": KeepSpeakingPayload,
    "pause": PausePayload,
    "resume": ResumePayload,
    "cancel_attempt": CancelAttemptPayload,
    "record_capture_hard_stop": RecordCaptureHardStopPayload,
    "retry_answer": RetryAnswerPayload,
    "retry_setup": RetrySetupPayload,
    "rebuild_plan": RebuildPlanPayload,
    "retry_processing": RetryProcessingPayload,
    "retry_report": RetryReportPayload,
    "request_hint": RequestHintPayload,
    "request_coaching": RequestCoachingPayload,
    "return_to_review": ReturnToReviewPayload,
    "edit_transcript": EditTranscriptPayload,
    "accept_attempt": AcceptAttemptPayload,
    "record_self_assessment": RecordSelfAssessmentPayload,
    "update_retention": UpdateRetentionPayload,
    "skip_question": SkipQuestionPayload,
    "end_session": EndSessionPayload,
    "delete_audio": DeleteAudioPayload,
    "delete_transcript": DeleteTranscriptPayload,
}

COMMAND_ENVELOPE_TYPES: dict[str, type[StrictContractModel]] = {}
for _command_type, _payload_type in COMMAND_PAYLOAD_TYPES.items():
    _envelope_name = f"{_payload_type.__name__.removesuffix('Payload')}CommandEnvelope"
    _envelope_type = create_model(
        _envelope_name,
        __base__=StrictContractModel,
        __module__=__name__,
        command_id=(SafeToken, ...),
        command_type=(Literal[_command_type], ...),
        expected_state_version=(NonNegativeInt, ...),
        payload=(_payload_type, ...),
        contract_version=(Literal[CONVERSATION_COMMAND_CONTRACT], ...),
    )
    COMMAND_ENVELOPE_TYPES[_command_type] = _envelope_type
    globals()[_envelope_name] = _envelope_type

_COMMAND_ENVELOPE_SCHEMA = TypeAdapter(
    Annotated[
        Union[tuple(COMMAND_ENVELOPE_TYPES.values())],  # type: ignore[valid-type]
        Field(discriminator="command_type"),
    ]
)


class ConversationCommandRequest(StrictContractModel):
    command_id: SafeToken
    command_type: CommandType
    expected_state_version: NonNegativeInt
    payload: CommandPayload
    contract_version: Literal[CONVERSATION_COMMAND_CONTRACT]

    @model_validator(mode="before")
    @classmethod
    def dispatch_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        command_type = value.get("command_type")
        if not isinstance(command_type, str):
            return value
        payload_type = COMMAND_PAYLOAD_TYPES.get(command_type)
        if payload_type is None:
            return value
        dispatched = dict(value)
        dispatched["payload"] = payload_type.model_validate(value.get("payload"))
        return dispatched

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(_COMMAND_ENVELOPE_SCHEMA.core_schema)


ConversationCommandResultState = Literal[
    "completed",
    "accepted_processing",
    "duplicate",
    "invalid_state",
    "version_conflict",
    "idempotency_conflict",
    "invalid_payload",
    "resource_blocked",
    "not_found",
    "permission_denied",
    "stale_claim",
]

ConversationState = Literal[
    "planning",
    "ready",
    "asking",
    "listening",
    "processing_answer",
    "awaiting_next_action",
    "coaching",
    "asking_follow_up",
    "advancing",
    "paused",
    "reporting",
    "completed",
    "recoverable_error",
    "abandoned",
    "failed",
]
ConversationStatus = Literal["setup", "active", "completed", "abandoned", "failed"]

# Candidate-command pairs come from Task 1's authoritative transition registry.
# These are the additional worker/transient/terminal pairs which never expose a
# candidate command while persisted.
_INTERNAL_STATUS_STATE_PAIRS = frozenset(
    {
        ("planning", "setup"),
        ("processing_answer", "active"),
        ("asking_follow_up", "active"),
        ("advancing", "active"),
        ("reporting", "active"),
        ("abandoned", "abandoned"),
        ("failed", "failed"),
    }
)
VALID_STATUS_STATE_PAIRS = (
    frozenset(pair for rule in TRANSITIONS.values() for pair in rule.allowed_pairs)
    | _INTERNAL_STATUS_STATE_PAIRS
)


class ConversationCommandResult(StrictContractModel):
    command_id: SafeToken
    result: ConversationCommandResultState
    session_id: SafeToken
    state: ConversationState
    state_version: NonNegativeInt
    active_question_id: SafeToken | None
    active_attempt_id: SafeToken | None
    async_job_id: SafeToken | None
    allowed_commands: list[CommandType]
    contract_version: Literal[CONVERSATION_COMMAND_RESULT_CONTRACT]

    @field_validator("allowed_commands")
    @classmethod
    def require_unique_allowed_commands(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_commands must be unique")
        return value


QuestionCategory = Literal[
    "behavioural", "situational", "culture", "technical", "domain", "commercial"
]
QuestionKind = Literal["planned", "adaptive_follow_up"]
QuestionState = Literal["pending", "asked", "answered", "skipped"]


class ConversationalQuestionRead(StrictContractModel):
    id: SafeToken
    text: Annotated[str, Field(min_length=1, max_length=10_000)]
    category: QuestionCategory
    difficulty: ConversationalDifficulty
    question_kind: QuestionKind
    question_state: QuestionState
    root_question_id: SafeToken | None
    parent_question_id: SafeToken | None
    follow_up_depth: Annotated[int, Field(ge=0, le=2)]
    follow_up_reason: (
        Literal[
            "clarify_example",
            "measurable_result",
            "personal_action",
            "reasoning",
            "role_depth",
            "resolve_ambiguity",
            "evidence_consistency",
        ]
        | None
    ) = None
    attempts_created_count: Annotated[int, Field(ge=0, le=20)]
    attempt_limit: Annotated[int, Field(ge=1, le=20)]
    attempts_remaining: NonNegativeInt

    @model_validator(mode="after")
    def validate_read_invariants(self) -> Self:
        if self.attempts_created_count > self.attempt_limit:
            raise ValueError("attempts_created_count exceeds the attempt limit")
        expected = self.attempt_limit - self.attempts_created_count
        if self.attempts_remaining != expected:
            raise ValueError("attempts_remaining does not match the attempt budget")
        if self.question_kind == "planned":
            if (
                self.root_question_id is not None
                or self.parent_question_id is not None
                or self.follow_up_reason is not None
                or self.follow_up_depth != 0
            ):
                raise ValueError("planned questions cannot contain follow-up metadata")
        elif (
            self.root_question_id is None
            or self.parent_question_id is None
            or self.follow_up_reason is None
            or self.follow_up_depth not in (1, 2)
        ):
            raise ValueError(
                "adaptive follow-ups require root, parent, reason, and depth"
            )
        return self


class TranscriptVersionRead(StrictContractModel):
    id: SafeToken
    version_number: Annotated[int, Field(ge=1)]
    transcript: Annotated[str, Field(min_length=1, max_length=30_000)]
    source: Literal[
        "transcription", "candidate_text", "candidate_edit", "recovered_transcription"
    ]
    edit_reason: Literal["transcription_error"] | None = None
    created_by: Literal["system", "candidate"]
    processing_generation: NonNegativeInt | None
    created_at: datetime

    @field_validator("transcript")
    @classmethod
    def require_canonical_transcript(cls, value: str) -> str:
        normalized = (
            unicodedata.normalize("NFC", value)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        if value != normalized or not value.strip():
            raise ValueError("transcript must be non-empty canonical NFC/LF text")
        return value

    @model_validator(mode="after")
    def validate_source_actor(self) -> Self:
        if self.source in ("transcription", "recovered_transcription"):
            valid = self.created_by == "system" and self.edit_reason is None
        elif self.source == "candidate_text":
            valid = self.created_by == "candidate" and self.edit_reason is None
        else:
            valid = (
                self.created_by == "candidate"
                and self.edit_reason == "transcription_error"
            )
        if not valid:
            raise ValueError(
                "transcript source, actor, and edit reason are inconsistent"
            )
        return self


class InterviewAttemptRead(StrictContractModel):
    id: SafeToken
    question_id: SafeToken
    recording_type: AnswerMode
    attempt_number: Annotated[int, Field(ge=1)]
    attempt_state: Literal[
        "draft",
        "uploaded",
        "pending_processing",
        "completed",
        "recoverable_error",
        "unavailable",
        "invalid",
        "cancelled",
        "deleted",
        "skipped",
    ]
    attempt_version: NonNegativeInt
    processing_generation: NonNegativeInt
    processing_retry_count: NonNegativeInt
    processing_retry_limit: Annotated[int, Field(ge=0, le=5)]
    processing_retries_remaining: NonNegativeInt
    audio_retention_policy: AudioRetentionPolicy | None
    audio_retention_state: AudioRetentionState | None
    transcript_version: TranscriptVersionRead | None

    @model_validator(mode="after")
    def validate_processing_retry_budget(self) -> Self:
        if self.processing_retry_count > self.processing_retry_limit:
            raise ValueError("processing retry count exceeds its snapshotted limit")
        expected = self.processing_retry_limit - self.processing_retry_count
        if self.processing_retries_remaining != expected:
            raise ValueError(
                "processing_retries_remaining does not match the retry budget"
            )
        return self


class ProcessingProjection(StrictContractModel):
    job_id: SafeToken | None
    stage: AttemptStageName | None
    state: AttemptStageState
    retryable: bool
    retry_count: NonNegativeInt
    retry_limit: Annotated[int, Field(ge=0, le=5)]
    retries_remaining: NonNegativeInt

    @model_validator(mode="after")
    def validate_retry_budget(self) -> Self:
        if self.retry_count > self.retry_limit:
            raise ValueError("processing retry count exceeds its snapshotted limit")
        expected = self.retry_limit - self.retry_count
        if self.retries_remaining != expected:
            raise ValueError("retries_remaining does not match the retry budget")
        return self


class ProgressProjection(StrictContractModel):
    planned_questions_total: Annotated[int, Field(ge=0, le=12)]
    planned_questions_completed: Annotated[int, Field(ge=0, le=12)]
    follow_ups_completed: Annotated[int, Field(ge=0, le=24)]
    current_planned_position: Annotated[int, Field(ge=1, le=12)] | None

    @model_validator(mode="after")
    def validate_progress_counts(self) -> Self:
        if self.planned_questions_completed > self.planned_questions_total:
            raise ValueError("completed planned questions exceed the plan total")
        if self.follow_ups_completed > self.planned_questions_total * 2:
            raise ValueError("completed follow-ups exceed the per-root budget")
        if (
            self.current_planned_position is not None
            and self.current_planned_position > self.planned_questions_total
        ):
            raise ValueError("current planned position exceeds the plan total")
        return self


class RetentionStatus(StrictContractModel):
    audio_policy: AudioRetentionPolicy
    current_audio_state: AudioRetentionState | None
    retryable_audio_cleanup_attempt_id: SafeToken | None


class AttemptAudioUploadRead(StrictContractModel):
    """Public result for one hash-verified conversational audio upload."""

    attempt_id: SafeToken
    upload_id: SafeToken
    result: AudioUploadResult
    content_sha256: LowercaseSha256
    byte_size: PositiveByteSize
    mime_type: BoundedMimeType
    audio_retention_state: AudioRetentionState
    contract_version: Literal["coach_attempt_audio_upload_v1"]


class SilencePolicy(StrictContractModel):
    warning_ms: Annotated[int, Field(ge=0, le=600_000)]
    finish_prompt_ms: Annotated[int, Field(ge=0, le=600_000)]

    @model_validator(mode="after")
    def validate_threshold_order(self) -> Self:
        if self.finish_prompt_ms < self.warning_ms:
            raise ValueError("finish prompt cannot precede the silence warning")
        return self


class RegisteredErrorMetadata(StrictContractModel):
    code: Annotated[str, Field(min_length=1, max_length=128)]
    message: Annotated[str, Field(min_length=1, max_length=500)]
    retryable: bool

    @model_validator(mode="before")
    @classmethod
    def derive_registry_metadata(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        code = value.get("code")
        if not isinstance(code, str) or code not in ERROR_REGISTRY:
            return value
        definition = ERROR_REGISTRY[code]
        derived = dict(value)
        for field_name, expected in (
            ("message", definition.message),
            ("retryable", definition.retryable),
        ):
            supplied = derived.get(field_name, expected)
            if supplied != expected:
                raise ValueError(
                    f"{field_name} does not match the canonical error registry"
                )
            derived[field_name] = expected
        return derived

    @field_validator("code")
    @classmethod
    def require_registered_error_code(cls, value: str) -> str:
        if value not in ERROR_REGISTRY:
            raise ValueError("unregistered conversational error code")
        return value


class EmptyErrorDetails(StrictContractModel):
    """Public PR1 errors intentionally expose no free-form diagnostic content."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        json_schema_extra={"maxProperties": 0},
    )


class RecoverableErrorProjection(RegisteredErrorMetadata):
    scope: Literal[
        "setup", "attempt_processing", "initial_report", "completed_report_rebuild"
    ]
    details: EmptyErrorDetails = Field(default_factory=EmptyErrorDetails)


class ConversationLiveView(StrictContractModel):
    session_id: SafeToken
    experience_version: Literal["conversational_v1"]
    status: ConversationStatus
    conversation_state: ConversationState
    state_version: NonNegativeInt
    activity_version: NonNegativeInt
    retention_version: NonNegativeInt
    active_question: ConversationalQuestionRead | None
    root_question: ConversationalQuestionRead | None
    active_attempt: InterviewAttemptRead | None
    processing: ProcessingProjection
    progress: ProgressProjection
    retention: RetentionStatus
    allowed_commands: list[CommandType]
    silence_policy: SilencePolicy
    recoverable_error: RecoverableErrorProjection | None
    report_state: Literal[
        "not_started", "building", "completed", "fallback", "failed", "invalidated"
    ]
    contract_version: Literal[LIVE_VIEW_CONTRACT]

    @field_validator("allowed_commands")
    @classmethod
    def require_unique_allowed_commands(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("allowed_commands must be unique")
        return value

    @model_validator(mode="after")
    def validate_status_state_pair(self) -> Self:
        if (self.conversation_state, self.status) not in VALID_STATUS_STATE_PAIRS:
            raise ValueError("conversation state contradicts the coarse session status")
        return self


class ConversationError(RegisteredErrorMetadata):
    current_state: ConversationState | None = None
    current_state_version: NonNegativeInt | None = None
    correlation_id: SafeToken
    details: EmptyErrorDetails = Field(default_factory=EmptyErrorDetails)


class ConversationErrorResponse(StrictContractModel):
    error: ConversationError


class PlanRole(StrictContractModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    role_family: RoleFamily
    role_family_label: Annotated[str, Field(min_length=1, max_length=80)] | None
    role_level: RoleLevel
    industry: Annotated[str, Field(min_length=1, max_length=64)] | None

    @field_validator("title")
    @classmethod
    def require_canonical_title(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFC", value).strip()
        if value != normalized:
            raise ValueError(
                "stored plan role title must be canonical trimmed NFC text"
            )
        return value

    @field_validator("role_family_label")
    @classmethod
    def require_canonical_role_label(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = unicodedata.normalize("NFC", value).strip()
        if value != normalized:
            raise ValueError(
                "stored role family label must be canonical trimmed NFC text"
            )
        return value

    @field_validator("industry")
    @classmethod
    def require_canonical_industry(cls, value: str | None) -> str | None:
        if value is not None and not INDUSTRY_RE.fullmatch(value):
            raise ValueError("stored industry must be a canonical normalized slug")
        return value

    @model_validator(mode="after")
    def validate_role_label(self) -> Self:
        if self.role_family == "other" and self.role_family_label is None:
            raise ValueError("other role families require a label")
        if self.role_family != "other" and self.role_family_label is not None:
            raise ValueError("registered role families cannot contain a custom label")
        return self


class PlanInterview(StrictContractModel):
    type: InterviewType
    difficulty: ConversationalDifficulty
    duration_minutes: Annotated[int, Field(ge=10, le=90)]
    planned_question_count: Annotated[int, Field(ge=3, le=12)]
    focus_areas: Annotated[list[FocusArea], Field(max_length=6)]
    locale: str
    allowed_answer_modes: Annotated[list[AnswerMode], Field(min_length=1, max_length=2)]

    @field_validator("locale")
    @classmethod
    def require_canonical_locale(cls, value: str) -> str:
        if value != normalize_locale(value):
            raise ValueError("stored plan locale must already be canonical")
        return value

    @field_validator("focus_areas", "allowed_answer_modes")
    @classmethod
    def require_unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("persisted plan lists must be unique")
        return value


class EvidenceSnapshot(StrictContractModel):
    package_hash: Annotated[str, StringConstraints(pattern=r"^sha256:[a-f0-9]{64}$")]
    record_count: Annotated[int, Field(ge=0, le=30)]
    contract_version: Literal["coach_session_evidence_snapshot_v1"]


class PlanContracts(StrictContractModel):
    question_generation: Literal["coach_question_generation_v2"]
    evaluation: Literal[RUBRIC_CONTRACT]
    delivery: Literal[DELIVERY_POLICY]
    evidence_grounding: Literal[EVIDENCE_GROUNDING_CONTRACT]
    follow_up: Literal[FOLLOW_UP_CONTRACT]
    report: Literal[REPORT_CONTRACT]


class PlanCompatibility(StrictContractModel):
    key: SafeToken
    version: Literal["coach_progress_compatibility_v1"]


class ConversationalSessionPlan(StrictContractModel):
    plan_id: SafeToken
    role: PlanRole
    interview: PlanInterview
    evidence_selection: EvidenceSelection
    evidence_snapshot: EvidenceSnapshot
    contracts: PlanContracts
    retention: RetentionPolicy
    compatibility: PlanCompatibility
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def parse_canonical_created_at(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if not RFC3339_DATETIME_RE.fullmatch(value) or value.endswith("-00:00"):
            raise ValueError("created_at must be a canonical RFC3339 datetime")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("created_at must be a valid RFC3339 datetime") from exc

    @field_validator("created_at")
    @classmethod
    def require_timezone_aware_created_at(cls, value: datetime) -> datetime:
        offset = value.utcoffset() if value.tzinfo is not None else None
        if offset is None:
            raise ValueError("created_at must include a timezone offset")
        if offset.total_seconds() % 60:
            raise ValueError("created_at timezone offset must use whole minutes")
        return value
