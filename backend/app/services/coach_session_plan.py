"""Deterministic planning and fenced persistence for conversational Coach sessions."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.async_job import AsyncJob
from ..models.coach_session import (
    CoachSessionEvidenceRecord,
    InterviewSession,
    InterviewSessionEvent,
    SessionRecording,
    SessionQuestion,
)
from ..schemas.coach import CreateSessionRequest
from ..schemas.coach_conversation import ConversationalSessionPlan
from .async_job_service import AsyncJobService
from .coach_conversational_contracts import (
    DELIVERY_POLICY,
    EVIDENCE_GROUNDING_CONTRACT,
    ERROR_REGISTRY,
    FOLLOW_UP_CONTRACT,
    REPORT_CONTRACT,
    RUBRIC_CONTRACT,
    SESSION_PLAN_CONTRACT,
)

EVIDENCE_SNAPSHOT_CONTRACT = "coach_session_evidence_snapshot_v1"
QUESTION_GENERATION_CONTRACT = "coach_question_generation_v2"
QUESTION_CATEGORY_CONTRACT = "coach_question_category_v1"
PROGRESS_COMPATIBILITY_CONTRACT = "coach_progress_compatibility_v1"
DEFAULT_SETUP_MAX_ATTEMPTS = 3
DEFAULT_SETUP_LEASE_SECONDS = 2400

_APPROVAL_STATES = frozenset(
    {
        "approved",
        "confirmed",
        "reviewed_final",
        "reviewed",
        "candidate_selected_unapproved",
        "draft",
        "context_only",
    }
)
_CATEGORIES = frozenset(
    {"behavioural", "situational", "culture", "technical", "domain", "commercial"}
)
_BEHAVIOURAL = ("behavioural", "situational", "culture")
_ROLE_SPECIFIC = ("technical", "domain", "commercial")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_snapshot(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")


def _rfc3339_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class EvidenceSource:
    evidence_id: str
    source_type: str
    source_record_id: str
    source_record_version: str
    source_path: str
    snapshot_text: str
    approval_state: str


@dataclass(frozen=True)
class EvidenceRecordBuild:
    evidence_id: str
    source_type: str
    source_record_id: str
    source_record_version: str
    source_path: str
    snapshot_text: str
    approval_state: str
    content_hash: str
    snapshot_hash: str

    def canonical_package_record(self) -> dict[str, str]:
        return {
            "approval_state": self.approval_state,
            "content_hash": self.content_hash,
            "evidence_id": self.evidence_id,
            "snapshot_hash": self.snapshot_hash,
            "snapshot_text": self.snapshot_text,
            "source_path": self.source_path,
            "source_record_id": self.source_record_id,
            "source_record_version": self.source_record_version,
            "source_type": self.source_type,
        }


@dataclass(frozen=True)
class PlannedQuestion:
    text: str
    category: str


@dataclass(frozen=True)
class SessionPlanBuild:
    plan: ConversationalSessionPlan
    questions: tuple[PlannedQuestion, ...]
    evidence_records: tuple[EvidenceRecordBuild, ...]
    compatibility_key: str
    role_family_component: str


@dataclass(frozen=True)
class SetupClaim:
    session_id: str
    job_id: str
    claim_token: str
    setup_generation: int
    claim_expires_at: datetime
    rebuild: bool = False


class SessionPlanError(ValueError):
    """Stable setup error with a frontend-safe registry code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class SessionPlanBuilder:
    """Build the V6 immutable plan from validated request and source snapshots."""

    @staticmethod
    def build(
        request: CreateSessionRequest,
        sources: Sequence[EvidenceSource],
        *,
        questions: Sequence[PlannedQuestion] | None = None,
        plan_id: str | None = None,
        created_at: str | None = None,
    ) -> SessionPlanBuild:
        config = request.conversational_config
        if request.experience_version != "conversational_v1" or config is None:
            raise ValueError("conversational_v1 planning request required")

        count = config.planned_question_count or _default_question_count(
            config.duration_minutes
        )
        normalized_questions = _normalise_questions(
            questions or _default_questions(config.interview_type, count),
            expected_count=count,
            interview_type=config.interview_type,
        )
        evidence_records = _build_evidence_records(
            sources,
            allow_drafts=(
                config.evidence_selection.question_bank == "include_drafts"
                and config.evidence_selection.draft_evidence_consent
            ),
        )
        package_hash = "sha256:" + _sha256(
            _canonical_json(
                [record.canonical_package_record() for record in evidence_records]
            )
        )
        role_family_component = _role_family_component(
            config.role_family, config.role_family_label
        )
        compatibility_components = {
            "role_family_component": role_family_component,
            "role_level": config.role_level,
            "interview_type": config.interview_type,
            "difficulty": config.difficulty,
            "evaluation_contract_version": RUBRIC_CONTRACT,
            "locale": config.locale,
        }
        compatibility_key = _sha256(_canonical_json(compatibility_components))

        plan = ConversationalSessionPlan.model_validate(
            {
                "plan_id": plan_id or uuid.uuid4().hex,
                "role": {
                    "title": request.role_title,
                    "role_family": config.role_family,
                    "role_family_label": config.role_family_label,
                    "role_level": config.role_level,
                    "industry": config.industry,
                },
                "interview": {
                    "type": config.interview_type,
                    "difficulty": config.difficulty,
                    "duration_minutes": config.duration_minutes,
                    "planned_question_count": count,
                    "focus_areas": config.focus_areas,
                    "locale": config.locale,
                    "allowed_answer_modes": config.allowed_answer_modes,
                },
                "evidence_selection": config.evidence_selection.model_dump(mode="json"),
                "evidence_snapshot": {
                    "package_hash": package_hash,
                    "record_count": len(evidence_records),
                    "contract_version": EVIDENCE_SNAPSHOT_CONTRACT,
                },
                "contracts": {
                    "question_generation": QUESTION_GENERATION_CONTRACT,
                    "evaluation": RUBRIC_CONTRACT,
                    "delivery": DELIVERY_POLICY,
                    "evidence_grounding": EVIDENCE_GROUNDING_CONTRACT,
                    "follow_up": FOLLOW_UP_CONTRACT,
                    "report": REPORT_CONTRACT,
                },
                "retention": config.retention.model_dump(mode="json"),
                "compatibility": {
                    "key": compatibility_key,
                    "version": PROGRESS_COMPATIBILITY_CONTRACT,
                },
                "created_at": created_at or _rfc3339_now(),
            }
        )
        return SessionPlanBuild(
            plan=plan,
            questions=normalized_questions,
            evidence_records=evidence_records,
            compatibility_key=compatibility_key,
            role_family_component=role_family_component,
        )


def _default_question_count(duration_minutes: int) -> int:
    if duration_minutes <= 15:
        return 3
    if duration_minutes <= 25:
        return 4
    if duration_minutes <= 35:
        return 6
    if duration_minutes <= 50:
        return 8
    if duration_minutes <= 70:
        return 10
    return 12


def _default_questions(interview_type: str, count: int) -> tuple[PlannedQuestion, ...]:
    if interview_type == "behavioural":
        categories = _BEHAVIOURAL
    elif interview_type == "role_specific_verbal":
        categories = _ROLE_SPECIFIC
    else:
        categories = tuple(
            category
            for pair in zip(_BEHAVIOURAL, _ROLE_SPECIFIC, strict=True)
            for category in pair
        )
    return tuple(
        PlannedQuestion(
            text=f"Discuss a relevant example for this {category} interview question.",
            category=category,
        )
        for index in range(count)
        for category in (categories[index % len(categories)],)
    )


def _normalise_questions(
    questions: Sequence[PlannedQuestion], *, expected_count: int, interview_type: str
) -> tuple[PlannedQuestion, ...]:
    if len(questions) != expected_count:
        raise ValueError("planned question count does not match the plan")
    normalized: list[PlannedQuestion] = []
    for question in questions:
        text = _normalize_snapshot(question.text).strip()
        category = question.category.strip().lower()
        if not text or category not in _CATEGORIES:
            raise ValueError("planned question is invalid")
        normalized.append(PlannedQuestion(text=text, category=category))
    categories = {question.category for question in normalized}
    if interview_type == "behavioural" and not categories <= set(_BEHAVIOURAL):
        raise ValueError("behavioural plan contains a role-specific category")
    if interview_type == "role_specific_verbal" and not categories <= set(
        _ROLE_SPECIFIC
    ):
        raise ValueError("role-specific plan contains a behavioural category")
    if interview_type == "mixed" and not (
        categories & set(_BEHAVIOURAL) and categories & set(_ROLE_SPECIFIC)
    ):
        raise ValueError("mixed plan must contain both category groups")
    return tuple(normalized)


def _build_evidence_records(
    sources: Sequence[EvidenceSource],
    *,
    allow_drafts: bool,
) -> tuple[EvidenceRecordBuild, ...]:
    if len(sources) > 30:
        raise ValueError("evidence package exceeds 30 records")
    records: list[EvidenceRecordBuild] = []
    seen: set[str] = set()
    total_codepoints = 0
    for source in sources:
        if source.evidence_id in seen:
            raise ValueError("evidence identifiers must be unique")
        seen.add(source.evidence_id)
        if (
            not _SAFE_ID.fullmatch(source.evidence_id)
            or not 1 <= len(source.source_type) <= 64
            or not 1 <= len(source.source_record_id) <= 128
            or not 1 <= len(source.source_record_version) <= 128
            or not 1 <= len(source.source_path) <= 512
            or source.approval_state not in _APPROVAL_STATES
        ):
            raise ValueError("evidence record metadata is invalid")
        if source.approval_state == "draft" and not allow_drafts:
            raise ValueError("draft evidence requires selected explicit consent")
        snapshot = _normalize_snapshot(source.snapshot_text)
        if not snapshot or len(snapshot) > 2000:
            raise ValueError("evidence snapshot exceeds its code-point bound")
        total_codepoints += len(snapshot)
        if total_codepoints > 40000:
            raise ValueError("evidence package exceeds its code-point bound")
        content_hash = "sha256:" + _sha256(snapshot)
        snapshot_identity = {
            "approval_state": source.approval_state,
            "evidence_id": source.evidence_id,
            "snapshot_text": snapshot,
            "source_path": source.source_path,
            "source_record_id": source.source_record_id,
            "source_record_version": source.source_record_version,
            "source_type": source.source_type,
        }
        records.append(
            EvidenceRecordBuild(
                evidence_id=source.evidence_id,
                source_type=source.source_type,
                source_record_id=source.source_record_id,
                source_record_version=source.source_record_version,
                source_path=source.source_path,
                snapshot_text=snapshot,
                approval_state=source.approval_state,
                content_hash=content_hash,
                snapshot_hash="sha256:" + _sha256(_canonical_json(snapshot_identity)),
            )
        )
    return tuple(sorted(records, key=lambda record: record.evidence_id))


def _role_family_component(role_family: str, role_family_label: str | None) -> str:
    if role_family != "other":
        return role_family
    if role_family_label is None:
        raise ValueError("other role family requires a label")
    normalized = " ".join(
        unicodedata.normalize("NFKC", role_family_label).casefold().strip().split()
    )
    return "other:" + _sha256(normalized)[:16]


async def claim_session_setup(
    db: AsyncSession,
    *,
    session_id: str,
    request: CreateSessionRequest,
    rebuild: bool = False,
    supported_locales: Sequence[str] = ("en-GB",),
    now: datetime | None = None,
    lease_seconds: int = DEFAULT_SETUP_LEASE_SECONDS,
) -> SetupClaim:
    """Claim one initial, retry, or candidate-requested rebuild generation."""
    config = request.conversational_config
    if request.experience_version != "conversational_v1" or config is None:
        raise SessionPlanError("coach_conversation_invalid_state")
    if config.locale not in frozenset(supported_locales):
        raise SessionPlanError("coach_locale_unsupported")
    current = await db.get(InterviewSession, session_id)
    if current is None or current.experience_version != "conversational_v1":
        raise SessionPlanError("coach_conversation_invalid_state")
    if current.deletion_state != "not_requested":
        raise SessionPlanError("coach_session_deletion_in_progress")
    if current.setup_job_id is not None or current.setup_claim_token is not None:
        raise SessionPlanError("coach_conversation_invalid_state")
    if current.setup_attempt_count >= current.setup_max_attempts:
        raise SessionPlanError("coach_setup_retry_budget_exhausted")

    initial = current.setup_attempt_count == 0 and current.conversation_state is None
    retry = (
        current.conversation_state == "recoverable_error"
        and current.recoverable_error_scope == "setup"
    )
    valid_rebuild = (
        rebuild
        and current.status == "setup"
        and current.conversation_state == "ready"
        and current.started_at is None
        and not await db.scalar(
            select(SessionRecording.id)
            .where(SessionRecording.session_id == session_id)
            .limit(1)
        )
    )
    if rebuild != valid_rebuild or not (initial or retry or valid_rebuild):
        raise SessionPlanError(
            "coach_plan_rebuild_not_allowed"
            if rebuild
            else "coach_conversation_invalid_state"
        )

    claimed_at = now or datetime.utcnow()
    claim_expires_at = claimed_at + timedelta(seconds=lease_seconds)
    claim_token = secrets.token_hex(32)
    job = await AsyncJobService.create(db, "coach_session")
    prior_state = current.conversation_state
    increment_state = 0 if initial else 1
    claimed = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == session_id,
            InterviewSession.experience_version == "conversational_v1",
            InterviewSession.status == "setup",
            InterviewSession.conversation_state.is_(prior_state)
            if prior_state is None
            else InterviewSession.conversation_state == prior_state,
            InterviewSession.setup_generation == current.setup_generation,
            InterviewSession.setup_attempt_count == current.setup_attempt_count,
            InterviewSession.setup_attempt_count < InterviewSession.setup_max_attempts,
            InterviewSession.setup_job_id.is_(None),
            InterviewSession.setup_claim_token.is_(None),
            InterviewSession.deletion_state == "not_requested",
        )
        .values(
            planning_request_json=request.model_dump(mode="json"),
            setup_generation=InterviewSession.setup_generation + 1,
            setup_attempt_count=InterviewSession.setup_attempt_count + 1,
            setup_job_id=job.id,
            setup_claim_token=claim_token,
            setup_claimed_at=claimed_at,
            setup_claim_expires_at=claim_expires_at,
            setup_started_at=claimed_at,
            setup_completed_at=None,
            recoverable_error_code=None,
            recoverable_error_scope=None,
            recoverable_error_context_json=None,
            conversation_state="planning",
            state_version=InterviewSession.state_version + increment_state,
        )
        .returning(InterviewSession.setup_generation, InterviewSession.state_version)
    )
    row = claimed.one_or_none()
    if row is None:
        await db.delete(job)
        await db.flush()
        raise SessionPlanError("coach_conversation_invalid_state")

    generation, state_version = row
    if valid_rebuild:
        event_types = ("session_plan_rebuild_requested", "session_plan_started")
    elif retry:
        event_types = ("session_plan_retry_requested", "session_plan_started")
    else:
        event_types = ("session_plan_started",)
    await _append_setup_events(
        db,
        session_id=session_id,
        event_types=event_types,
        state_before=prior_state,
        state_after="planning",
        state_version=state_version,
    )
    await db.flush()
    return SetupClaim(
        session_id=session_id,
        job_id=job.id,
        claim_token=claim_token,
        setup_generation=generation,
        claim_expires_at=claim_expires_at,
        rebuild=valid_rebuild,
    )


async def persist_session_plan(
    db: AsyncSession,
    *,
    session_id: str,
    build: SessionPlanBuild,
) -> None:
    """Replace all staged plan children inside the caller-owned transaction."""
    await db.execute(
        delete(CoachSessionEvidenceRecord).where(
            CoachSessionEvidenceRecord.session_id == session_id
        )
    )
    await db.execute(
        delete(SessionQuestion).where(SessionQuestion.session_id == session_id)
    )
    db.add_all(
        [
            CoachSessionEvidenceRecord(
                id=str(uuid.uuid4()),
                session_id=session_id,
                evidence_id=record.evidence_id,
                source_type=record.source_type,
                source_record_id=record.source_record_id,
                source_record_version=record.source_record_version,
                source_path=record.source_path,
                snapshot_text=record.snapshot_text,
                approval_state=record.approval_state,
                content_hash=record.content_hash,
                snapshot_hash=record.snapshot_hash,
            )
            for record in build.evidence_records
        ]
    )
    db.add_all(
        [
            SessionQuestion(
                id=str(uuid.uuid4()),
                session_id=session_id,
                question_num=index,
                text=question.text,
                category=question.category,
                difficulty=build.plan.interview.difficulty,
                order_in_session=index,
                question_kind="planned",
                follow_up_depth=0,
                question_state="pending",
                question_category_contract_version=QUESTION_CATEGORY_CONTRACT,
                question_contract_version=QUESTION_GENERATION_CONTRACT,
            )
            for index, question in enumerate(build.questions, start=1)
        ]
    )
    await db.flush()


async def finalise_session_setup(
    db: AsyncSession,
    *,
    claim: SetupClaim,
    build: SessionPlanBuild,
    now: datetime | None = None,
) -> bool:
    """Atomically publish a complete plan only for the live unexpired claim."""
    completed_at = now or datetime.utcnow()
    live_request_json = await db.scalar(
        select(InterviewSession.planning_request_json).where(
            InterviewSession.id == claim.session_id,
            InterviewSession.status == "setup",
            InterviewSession.conversation_state == "planning",
            InterviewSession.setup_job_id == claim.job_id,
            InterviewSession.setup_claim_token == claim.claim_token,
            InterviewSession.setup_generation == claim.setup_generation,
            InterviewSession.setup_claim_expires_at >= completed_at,
            InterviewSession.deletion_state == "not_requested",
        )
    )
    if live_request_json is None:
        return False
    _validate_build_for_request(
        build,
        request=CreateSessionRequest.model_validate(live_request_json),
    )
    transitioned = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == claim.session_id,
            InterviewSession.status == "setup",
            InterviewSession.conversation_state == "planning",
            InterviewSession.setup_job_id == claim.job_id,
            InterviewSession.setup_claim_token == claim.claim_token,
            InterviewSession.setup_generation == claim.setup_generation,
            InterviewSession.setup_claim_expires_at >= completed_at,
            InterviewSession.deletion_state == "not_requested",
        )
        .values(
            session_plan_json=build.plan.model_dump(mode="json"),
            session_plan_contract_version=SESSION_PLAN_CONTRACT,
            evaluation_contract_version=RUBRIC_CONTRACT,
            report_contract_version=REPORT_CONTRACT,
            compatibility_key=build.compatibility_key,
            retention_policy_json=build.plan.retention.model_dump(mode="json"),
            session_plan_amendment_version=(
                InterviewSession.session_plan_amendment_version + 1
                if claim.rebuild
                else InterviewSession.session_plan_amendment_version
            ),
            setup_job_id=None,
            setup_claim_token=None,
            setup_claimed_at=None,
            setup_claim_expires_at=None,
            setup_completed_at=completed_at,
            recoverable_error_code=None,
            recoverable_error_scope=None,
            recoverable_error_context_json=None,
            conversation_state="ready",
            state_version=InterviewSession.state_version + 1,
        )
        .returning(InterviewSession.state_version)
    )
    state_version = transitioned.scalar_one_or_none()
    if state_version is None:
        return False

    await persist_session_plan(db, session_id=claim.session_id, build=build)
    await db.execute(
        update(AsyncJob)
        .where(
            AsyncJob.id == claim.job_id,
            AsyncJob.status.in_(("pending", "running")),
        )
        .values(
            status="done",
            result_json=_canonical_json(
                {"session_id": claim.session_id, "status": "ready"}
            ),
            error=None,
            updated_at=completed_at,
        )
    )
    await _append_setup_events(
        db,
        session_id=claim.session_id,
        event_types=(
            "session_plan_rebuilt" if claim.rebuild else "session_plan_completed",
        ),
        state_before="planning",
        state_after="ready",
        state_version=state_version,
    )
    await db.flush()
    return True


def _validate_build_for_request(
    build: SessionPlanBuild, *, request: CreateSessionRequest
) -> None:
    config = request.conversational_config
    if config is None:
        raise ValueError("plan requires a conversational planning request")
    plan = build.plan
    if plan.compatibility.key != build.compatibility_key:
        raise ValueError("plan compatibility key does not match the build")
    expected_role_component = _role_family_component(
        config.role_family, config.role_family_label
    )
    expected_compatibility_key = _sha256(
        _canonical_json(
            {
                "role_family_component": expected_role_component,
                "role_level": config.role_level,
                "interview_type": config.interview_type,
                "difficulty": config.difficulty,
                "evaluation_contract_version": RUBRIC_CONTRACT,
                "locale": config.locale,
            }
        )
    )
    if (
        build.role_family_component != expected_role_component
        or build.compatibility_key != expected_compatibility_key
    ):
        raise ValueError("plan compatibility components do not match the request")

    expected_question_count = config.planned_question_count or _default_question_count(
        config.duration_minutes
    )
    _normalise_questions(
        build.questions,
        expected_count=expected_question_count,
        interview_type=config.interview_type,
    )
    rebuilt_evidence = _build_evidence_records(
        [
            EvidenceSource(
                evidence_id=record.evidence_id,
                source_type=record.source_type,
                source_record_id=record.source_record_id,
                source_record_version=record.source_record_version,
                source_path=record.source_path,
                snapshot_text=record.snapshot_text,
                approval_state=record.approval_state,
            )
            for record in build.evidence_records
        ],
        allow_drafts=(
            config.evidence_selection.question_bank == "include_drafts"
            and config.evidence_selection.draft_evidence_consent
        ),
    )
    if rebuilt_evidence != build.evidence_records:
        raise ValueError("plan evidence records are not canonical")
    expected_package_hash = "sha256:" + _sha256(
        _canonical_json(
            [
                record.canonical_package_record()
                for record in sorted(
                    build.evidence_records, key=lambda candidate: candidate.evidence_id
                )
            ]
        )
    )
    if (
        plan.evidence_snapshot.record_count != len(build.evidence_records)
        or plan.evidence_snapshot.package_hash != expected_package_hash
    ):
        raise ValueError("plan evidence snapshot does not match the build")
    if (
        plan.role.title != request.role_title
        or plan.role.role_family != config.role_family
        or plan.role.role_family_label != config.role_family_label
        or plan.role.role_level != config.role_level
        or plan.role.industry != config.industry
        or plan.interview.type != config.interview_type
        or plan.interview.difficulty != config.difficulty
        or plan.interview.duration_minutes != config.duration_minutes
        or plan.interview.planned_question_count != expected_question_count
        or plan.interview.focus_areas != config.focus_areas
        or plan.interview.locale != config.locale
        or plan.interview.allowed_answer_modes != config.allowed_answer_modes
        or plan.evidence_selection != config.evidence_selection
        or plan.retention != config.retention
    ):
        raise ValueError("plan snapshot does not match the normalized request")


async def fail_session_setup(
    db: AsyncSession,
    *,
    claim: SetupClaim,
    error_code: str,
    retryable: bool,
    now: datetime | None = None,
) -> bool:
    """Release a matching failed claim, preserving any prior audit plan."""
    if error_code not in ERROR_REGISTRY:
        raise ValueError("setup failure must use a canonical error code")
    failed_at = now or datetime.utcnow()
    session = await db.get(InterviewSession, claim.session_id)
    if session is None:
        return False
    recoverable = retryable and session.setup_attempt_count < session.setup_max_attempts
    state_after = "recoverable_error" if recoverable else "failed"
    status_after = "setup" if recoverable else "failed"
    transitioned = await db.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == claim.session_id,
            InterviewSession.status == "setup",
            InterviewSession.conversation_state == "planning",
            InterviewSession.setup_job_id == claim.job_id,
            InterviewSession.setup_claim_token == claim.claim_token,
            InterviewSession.setup_generation == claim.setup_generation,
            InterviewSession.setup_claim_expires_at >= failed_at,
            InterviewSession.deletion_state == "not_requested",
        )
        .values(
            status=status_after,
            conversation_state=state_after,
            setup_job_id=None,
            setup_claim_token=None,
            setup_claimed_at=None,
            setup_claim_expires_at=None,
            recoverable_error_code=error_code if recoverable else None,
            recoverable_error_scope="setup" if recoverable else None,
            recoverable_error_context_json={} if recoverable else None,
            state_version=InterviewSession.state_version + 1,
        )
        .returning(InterviewSession.state_version)
    )
    state_version = transitioned.scalar_one_or_none()
    if state_version is None:
        return False
    await db.execute(
        update(AsyncJob)
        .where(
            AsyncJob.id == claim.job_id,
            AsyncJob.status.in_(("pending", "running")),
        )
        .values(
            status="failed", result_json=None, error=error_code, updated_at=failed_at
        )
    )
    await _append_setup_events(
        db,
        session_id=claim.session_id,
        event_types=("session_plan_failed",),
        state_before="planning",
        state_after=state_after,
        state_version=state_version,
    )
    await db.flush()
    return True


async def _append_setup_events(
    db: AsyncSession,
    *,
    session_id: str,
    event_types: Sequence[str],
    state_before: str | None,
    state_after: str,
    state_version: int,
) -> None:
    if not event_types:
        return
    allocation = await db.execute(
        update(InterviewSession)
        .where(InterviewSession.id == session_id)
        .values(event_version=InterviewSession.event_version + len(event_types))
        .returning(InterviewSession.event_version)
    )
    final_sequence = allocation.scalar_one()
    first_sequence = final_sequence - len(event_types) + 1
    db.add_all(
        [
            InterviewSessionEvent(
                id=str(uuid.uuid4()),
                session_id=session_id,
                sequence_number=first_sequence + offset,
                event_type=event_type,
                state_before=state_before,
                state_after=state_after,
                state_version=state_version,
                actor_type="worker"
                if event_type.endswith(("completed", "rebuilt", "failed"))
                else "system",
                payload_json=None,
            )
            for offset, event_type in enumerate(event_types)
        ]
    )
    await db.flush()
