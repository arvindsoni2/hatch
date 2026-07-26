"""Deterministic planning and fenced persistence for conversational Coach sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import unicodedata
import uuid
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.async_job import AsyncJob
from ..models.application import Application
from ..models.coach_session import (
    CompanyResearch,
    CoachSessionEvidenceRecord,
    InterviewSession,
    InterviewSessionEvent,
    SessionRecording,
    SessionQuestion,
)
from ..models.document import GeneratedDocument
from ..models.job import JobPosting
from ..models.question_bank import QuestionBankItem
from ..schemas.coach import CreateSessionRequest
from ..schemas.coach_conversation import ConversationalSessionPlan
from .async_job_service import AsyncJobService
from .master_cv_store import resolve_master_cv_path
from .writing_contracts import build_evidence_ledger
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
_PEM_PATTERN = re.compile(
    r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----"
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)([\"']?(?:aws_access_key_id|aws_secret_access_key|client_secret|"
    r"api[_-]?key|authorization|password|secret|access[_-]?token|token)[\"']?"
    r"\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{6,}\d)(?!\w)")
_YEAR_RANGE_PATTERN = re.compile(r"^\d{4}\s*[-–—]\s*\d{4}$")
_SENSITIVE_JSON_KEYS = frozenset(
    {
        "aws_access_key_id",
        "aws_secret_access_key",
        "client_secret",
        "password",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "authorization",
        "secret",
        "email",
        "email_address",
        "phone",
        "phone_number",
        "mobile",
        "telephone",
        "address",
        "postcode",
        "postal_code",
        "dob",
        "date_of_birth",
    }
)
_SENSITIVE_JSON_CONTAINERS = frozenset(
    {"personal", "personal_details", "contact", "contact_details"}
)
_MAX_SOURCE_FILE_BYTES = 10 * 1024 * 1024
_MAX_EVIDENCE_SNAPSHOT_CODEPOINTS = 2000
_MAX_DOCX_ENTRIES = 512
_MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
_SUPPORTED_CV_EXTENSIONS = frozenset({".docx", ".txt", ".md", ".json"})


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


async def load_claim_planning_request(
    db: AsyncSession,
    *,
    request: CreateSessionRequest | None = None,
    claim: SetupClaim | None = None,
    current_retention: dict[str, str] | None = None,
    now: datetime | None = None,
) -> CreateSessionRequest:
    """Resolve initial JD fallback or reload a claim's authoritative stored request."""
    if (request is None) == (claim is None):
        raise ValueError("provide exactly one of request or claim")
    if claim is not None:
        checked_at = now or datetime.utcnow()
        row = (
            await db.execute(
                select(
                    InterviewSession.planning_request_json,
                    InterviewSession.retention_policy_json,
                ).where(
                    InterviewSession.id == claim.session_id,
                    InterviewSession.setup_job_id == claim.job_id,
                    InterviewSession.setup_claim_token == claim.claim_token,
                    InterviewSession.setup_generation == claim.setup_generation,
                    InterviewSession.status == "setup",
                    InterviewSession.conversation_state == "planning",
                    InterviewSession.setup_claim_expires_at >= checked_at,
                    InterviewSession.deletion_state == "not_requested",
                )
            )
        ).one_or_none()
        if row is None or row.planning_request_json is None:
            raise SessionPlanError("coach_conversation_invalid_state")
        return _effective_planning_request(
            row.planning_request_json,
            retention_policy=row.retention_policy_json,
            rebuild=claim.rebuild,
        )

    assert request is not None
    payload = request.model_dump(mode="json")
    if request.jd_text is None and request.application_id is not None:
        linked_jd = await db.scalar(
            select(JobPosting.description)
            .join(Application, Application.job_id == JobPosting.id)
            .where(Application.id == request.application_id)
        )
        if linked_jd:
            payload["jd_text"] = linked_jd
    if payload.get("jd_text"):
        payload["jd_text"] = _redact_evidence_text(payload["jd_text"])
    if current_retention is not None:
        payload["conversational_config"]["retention"] = copy_json(current_retention)
    return CreateSessionRequest.model_validate(payload)


def _effective_planning_request(
    planning_request: dict[str, Any],
    *,
    retention_policy: dict[str, str] | None,
    rebuild: bool,
) -> CreateSessionRequest:
    payload = copy_json(planning_request)
    if rebuild and retention_policy is not None:
        payload["conversational_config"]["retention"] = copy_json(retention_policy)
    return CreateSessionRequest.model_validate(payload)


def copy_json(value: Any) -> Any:
    """Round-trip JSON-compatible state without retaining mutable ORM containers."""
    return json.loads(_canonical_json(value))


async def load_session_plan_sources(
    db: AsyncSession,
    request: CreateSessionRequest,
    *,
    now: datetime | None = None,
    managed_cv_roots: Sequence[Path] | None = None,
    claim: SetupClaim | None = None,
) -> tuple[EvidenceSource, ...]:
    """Select the latest V6-eligible immutable source snapshots."""
    if claim is not None:
        effective_request = await load_claim_planning_request(db, claim=claim)
        if effective_request.model_dump(mode="json") != request.model_dump(mode="json"):
            raise SessionPlanError("coach_conversation_invalid_state")
    config = request.conversational_config
    if config is None:
        raise SessionPlanError("coach_conversation_invalid_state")
    if not request.jd_text:
        raise SessionPlanError("coach_contract_unsupported")
    selected: list[EvidenceSource] = []
    application: Application | None = None
    if request.application_id is not None:
        application = await db.get(Application, request.application_id)

    if config.evidence_selection.application_cv != "none" and application is not None:
        approved = (
            await db.execute(
                select(GeneratedDocument)
                .where(
                    GeneratedDocument.application_id == application.id,
                    GeneratedDocument.document_type == "cv",
                    GeneratedDocument.status == "approved",
                )
                .order_by(GeneratedDocument.version.desc(), GeneratedDocument.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if approved is not None:
            selected.append(
                _document_evidence_source(
                    locator=approved.file_path,
                    evidence_id=f"application_cv:{approved.id}",
                    source_record_id=approved.id,
                    source_record_version=str(approved.version),
                    approval_state="approved",
                    managed_cv_roots=managed_cv_roots,
                )
            )
        elif (
            config.evidence_selection.application_cv == "current_if_no_approved"
            and application.cv_version
        ):
            text = _read_supported_cv(
                application.cv_version, managed_cv_roots=managed_cv_roots
            )
            redacted = _redact_evidence_text(text)
            selected.append(
                EvidenceSource(
                    evidence_id=f"application_cv:{application.id}",
                    source_type="application_cv",
                    source_record_id=application.id,
                    source_record_version=_sha256(redacted),
                    source_path="application/current_cv",
                    snapshot_text=redacted,
                    approval_state="candidate_selected_unapproved",
                )
            )

    if config.evidence_selection.master_cv == "include":
        selected.extend(_master_cv_sources())

    selected.extend(await _question_bank_sources(db, request))

    if request.jd_text:
        redacted_jd = _redact_evidence_text(request.jd_text)
        selected.append(
            EvidenceSource(
                evidence_id="job_description",
                source_type="job_posting",
                source_record_id=request.application_id or "planning_request",
                source_record_version=_sha256(redacted_jd),
                source_path="planning_request/jd_text",
                snapshot_text=redacted_jd,
                approval_state="context_only",
            )
        )

    if config.evidence_selection.company_research == "include_if_fresh":
        timestamp = now or datetime.utcnow()
        normalized_company = _normalized_name(request.company_name)
        research = (
            await db.execute(
                select(CompanyResearch)
                .where(
                    CompanyResearch.expires_at >= timestamp,
                    _sql_normalized_name(CompanyResearch.company_name)
                    == normalized_company,
                )
                .order_by(CompanyResearch.cached_at.desc(), CompanyResearch.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if research is not None and (
            _normalized_name(research.company_name) != normalized_company
        ):
            raise SessionPlanError("coach_grounding_source_unavailable")
        if research is not None:
            research_text = _structured_research_text(research)
            if not research_text:
                raise SessionPlanError("coach_grounding_source_unavailable")
            selected.append(
                EvidenceSource(
                    evidence_id=f"company_research:{research.id}",
                    source_type="company_research",
                    source_record_id=research.id,
                    source_record_version=research.cached_at.isoformat(),
                    source_path="company_research/structured",
                    snapshot_text=research_text,
                    approval_state="context_only",
                )
            )

    if any(not item.snapshot_text for item in selected):
        raise SessionPlanError("coach_grounding_source_unavailable")
    if (
        len(selected) > 30
        or any(len(item.snapshot_text) > 2000 for item in selected)
        or sum(len(item.snapshot_text) for item in selected) > 40000
    ):
        raise SessionPlanError("coach_contract_unsupported")
    if claim is not None:
        await db.flush()
        await load_claim_planning_request(db, claim=claim)
    return tuple(selected)


def _document_evidence_source(
    *,
    locator: str | None,
    evidence_id: str,
    source_record_id: str,
    source_record_version: str,
    approval_state: str,
    managed_cv_roots: Sequence[Path] | None,
) -> EvidenceSource:
    if not locator:
        raise SessionPlanError("coach_grounding_source_unavailable")
    redacted = _redact_evidence_text(
        _read_supported_cv(locator, managed_cv_roots=managed_cv_roots)
    )
    return EvidenceSource(
        evidence_id=evidence_id,
        source_type="application_cv",
        source_record_id=source_record_id,
        source_record_version=source_record_version,
        source_path="application/generated_cv",
        snapshot_text=redacted,
        approval_state=approval_state,
    )


def _read_supported_cv(
    locator: str, *, managed_cv_roots: Sequence[Path] | None = None
) -> str:
    try:
        path = _resolve_managed_cv_path(locator, managed_cv_roots)
        suffix = path.suffix.casefold()
        if suffix == ".docx":
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if (
                    len(entries) > _MAX_DOCX_ENTRIES
                    or sum(entry.file_size for entry in entries)
                    > _MAX_DOCX_UNCOMPRESSED_BYTES
                    or any(entry.flag_bits & 0x1 for entry in entries)
                ):
                    raise SessionPlanError("coach_grounding_source_unavailable")
            from docx import Document  # type: ignore  # noqa: PLC0415

            document = Document(str(path))
            value = _bounded_text_join(
                paragraph.text for paragraph in document.paragraphs if paragraph.text
            )
        elif suffix in {".txt", ".md", ".json"}:
            value = _read_bounded_text(path)
        else:
            raise SessionPlanError("coach_grounding_source_unavailable")
    except SessionPlanError:
        raise
    except Exception as exc:
        raise SessionPlanError("coach_grounding_source_unavailable") from exc
    if not value.strip():
        raise SessionPlanError("coach_grounding_source_unavailable")
    return value


def _default_managed_cv_roots() -> tuple[Path, ...]:
    roots = [(Path.cwd() / "data" / "generated").resolve()]
    data_dir = os.environ.get("DATA_DIR")
    if data_dir:
        roots.append((Path(data_dir) / "generated").resolve())
    return tuple(dict.fromkeys(roots))


def _resolve_managed_cv_path(
    locator: str, managed_cv_roots: Sequence[Path] | None
) -> Path:
    candidate = Path(locator)
    if candidate.suffix.casefold() not in _SUPPORTED_CV_EXTENSIONS:
        raise SessionPlanError("coach_grounding_source_unavailable")
    lexical_candidate = Path(os.path.abspath(candidate))
    roots = managed_cv_roots or _default_managed_cv_roots()
    for configured_root in roots:
        lexical_root = Path(os.path.abspath(configured_root))
        try:
            relative = lexical_candidate.relative_to(lexical_root)
        except ValueError:
            continue
        current = lexical_root
        if current.is_symlink():
            continue
        unsafe = False
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                unsafe = True
                break
        if unsafe:
            continue
        try:
            resolved_root = lexical_root.resolve(strict=True)
            resolved = lexical_candidate.resolve(strict=True)
            resolved.relative_to(resolved_root)
        except (OSError, ValueError):
            continue
        if resolved.is_file() and resolved.stat().st_size <= _MAX_SOURCE_FILE_BYTES:
            return resolved
    raise SessionPlanError("coach_grounding_source_unavailable")


def _read_bounded_text(path: Path) -> str:
    parts: list[str] = []
    remaining = _MAX_EVIDENCE_SNAPSHOT_CODEPOINTS + 1
    with path.open(encoding="utf-8", newline=None) as source:
        while remaining > 0:
            chunk = source.read(min(4096, remaining))
            if not chunk:
                break
            parts.append(chunk)
            remaining -= len(chunk)
    return "".join(parts)


def _bounded_text_join(values: Iterable[str]) -> str:
    parts: list[str] = []
    size = 0
    for value in values:
        if not value:
            continue
        prefix = "\n" if parts else ""
        remaining = _MAX_EVIDENCE_SNAPSHOT_CODEPOINTS + 1 - size
        if remaining <= 0:
            break
        fragment = (prefix + value)[:remaining]
        parts.append(fragment)
        size += len(fragment)
    return "".join(parts)


def _master_cv_sources() -> list[EvidenceSource]:
    try:
        configured_path = resolve_master_cv_path()
        if not configured_path.exists():
            return []
        if configured_path.stat().st_size > _MAX_SOURCE_FILE_BYTES:
            raise SessionPlanError("coach_grounding_source_unavailable")
        with configured_path.open("rb") as source:
            raw = source.read(_MAX_SOURCE_FILE_BYTES + 1)
        if len(raw) > _MAX_SOURCE_FILE_BYTES:
            raise SessionPlanError("coach_grounding_source_unavailable")
        master = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        if isinstance(exc, SessionPlanError):
            raise
        raise SessionPlanError("coach_grounding_source_unavailable") from exc
    if not isinstance(master, dict):
        raise SessionPlanError("coach_grounding_source_unavailable")
    professional = {
        key: master[key]
        for key in (
            "summary",
            "summary_variants",
            "skills",
            "experience",
            "education",
            "certifications",
            "projects",
        )
        if key in master
    }
    redacted_professional = _redact_json_value(professional)
    canonical_professional = _canonical_json(redacted_professional)
    if (
        len(canonical_professional) > 40_000
        or len(canonical_professional.encode("utf-8")) > 40_000
    ):
        raise SessionPlanError("coach_contract_unsupported")
    source_version = _sha256(canonical_professional)
    rows: list[EvidenceSource] = []
    for item in build_evidence_ledger(redacted_professional):
        text = _redact_evidence_text(item.text)
        if text:
            rows.append(
                EvidenceSource(
                    evidence_id=f"master_cv:{_sha256(item.source_path)[:24]}",
                    source_type="master_cv",
                    source_record_id="master_cv",
                    source_record_version=source_version,
                    source_path=f"master_cv/{item.source_path}",
                    snapshot_text=text,
                    approval_state="confirmed",
                )
            )
    return rows


async def _question_bank_sources(
    db: AsyncSession, request: CreateSessionRequest
) -> list[EvidenceSource]:
    config = request.conversational_config
    assert config is not None
    policy = config.evidence_selection.question_bank
    if policy == "exclude":
        return []
    confidences = ("reviewed", "final")
    if policy == "include_drafts":
        confidences = ("draft", "reviewed", "final")
    text_columns = (
        QuestionBankItem.title,
        QuestionBankItem.question,
        QuestionBankItem.situation,
        QuestionBankItem.task,
        QuestionBankItem.action,
        QuestionBankItem.result,
        QuestionBankItem.answer_draft,
    )
    stmt = select(
        QuestionBankItem.id,
        QuestionBankItem.type,
        QuestionBankItem.confidence,
        QuestionBankItem.updated_at,
        *(func.length(column) for column in text_columns),
    ).where(
        QuestionBankItem.archived_at.is_(None),
        or_(
            QuestionBankItem.type == "company_research_note",
            QuestionBankItem.confidence.in_(confidences),
        ),
    )
    explicit_ids = config.evidence_selection.selected_question_bank_record_ids
    if explicit_ids:
        stmt = stmt.where(QuestionBankItem.id.in_(explicit_ids))
    stmt = stmt.order_by(
        QuestionBankItem.updated_at.desc(), QuestionBankItem.id.asc()
    ).limit(50 if explicit_ids else 31)
    metadata_rows = list((await db.execute(stmt)).all())
    if explicit_ids and {row.id for row in metadata_rows} != set(explicit_ids):
        raise SessionPlanError("coach_grounding_source_unavailable")
    if not explicit_ids and len(metadata_rows) > 30:
        raise SessionPlanError("coach_contract_unsupported")
    for row in metadata_rows:
        lengths = [length for length in row[4:] if length]
        if sum(lengths) + max(0, len(lengths) - 1) > 2000:
            raise SessionPlanError("coach_contract_unsupported")
    selected_ids = [row.id for row in metadata_rows]
    if not selected_ids:
        return []
    rows = list(
        (
            await db.execute(
                select(QuestionBankItem)
                .where(QuestionBankItem.id.in_(selected_ids))
                .order_by(QuestionBankItem.updated_at.desc(), QuestionBankItem.id.asc())
                .limit(len(selected_ids))
            )
        )
        .scalars()
        .all()
    )
    if [row.id for row in rows] != selected_ids:
        raise SessionPlanError("coach_grounding_source_unavailable")
    approval = {"draft": "draft", "reviewed": "reviewed", "final": "reviewed_final"}
    return [
        EvidenceSource(
            evidence_id=f"question_bank:{row.id}",
            source_type="question_bank",
            source_record_id=row.id,
            source_record_version=row.updated_at.isoformat(),
            source_path=(
                "question_bank/company_research_note"
                if row.type == "company_research_note"
                else "question_bank/answer"
            ),
            snapshot_text=_redact_evidence_text(
                "\n".join(
                    value
                    for value in (
                        row.title,
                        row.question,
                        row.situation,
                        row.task,
                        row.action,
                        row.result,
                        row.answer_draft,
                    )
                    if value
                )
            ),
            approval_state=(
                "context_only"
                if row.type == "company_research_note"
                else approval[row.confidence]
            ),
        )
        for row in rows
    ]


def _structured_research_text(research: CompanyResearch) -> str:
    payload = {
        "sector": research.sector,
        "description": research.description,
        "recent_news": research.recent_news,
        "key_products": research.key_products,
        "tech_stack_signals": research.tech_stack_signals,
    }
    return _redact_evidence_text(_canonical_json(payload)).strip()


def _normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _sql_normalized_name(column: Any) -> Any:
    expression = func.lower(func.trim(column))
    for whitespace in ("\t", "\n", "\r"):
        expression = func.replace(expression, whitespace, " ")
    for _ in range(8):
        expression = func.replace(expression, "  ", " ")
    return expression


def _redact_evidence_text(value: str) -> str:
    return _canonical_redacted_text(value)


def _canonical_redacted_text(value: str) -> str:
    normalized = _normalize_snapshot(value).strip()
    try:
        parsed = json.loads(normalized)
    except (json.JSONDecodeError, TypeError):
        return _redact_plain_text(normalized).strip()
    return _canonical_json(_redact_json_value(parsed))


def _redact_plain_text(value: str) -> str:
    redacted = _PEM_PATTERN.sub("[REDACTED]", value)
    redacted = _SECRET_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _BEARER_PATTERN.sub("[REDACTED]", redacted)
    redacted = _EMAIL_PATTERN.sub("[REDACTED EMAIL]", redacted)
    return _PHONE_PATTERN.sub(_redact_phone_candidate, redacted)


def _redact_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = re.sub(
                r"[^a-z0-9]+",
                "_",
                unicodedata.normalize("NFKC", str(key)).casefold(),
            ).strip("_")
            if normalized_key in _SENSITIVE_JSON_KEYS | _SENSITIVE_JSON_CONTAINERS:
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = _redact_json_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    if isinstance(value, str):
        return _redact_plain_text(value)
    return value


def _redact_phone_candidate(match: re.Match[str]) -> str:
    candidate = match.group(0)
    if _YEAR_RANGE_PATTERN.fullmatch(candidate.strip()):
        return candidate
    digit_count = sum(character.isdigit() for character in candidate)
    return "[REDACTED PHONE]" if 8 <= digit_count <= 15 else candidate


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
        canonical_sources = tuple(
            replace(
                source,
                snapshot_text=_canonical_redacted_text(source.snapshot_text),
            )
            for source in sources
        )
        _validate_source_selection(request, canonical_sources)
        normalized_questions = _normalise_questions(
            _default_questions(request, canonical_sources, count)
            if questions is None
            else questions,
            expected_count=count,
            interview_type=config.interview_type,
        )
        evidence_records = _build_evidence_records(
            canonical_sources,
            allow_drafts=(
                config.evidence_selection.question_bank == "include_drafts"
                and config.evidence_selection.draft_evidence_consent
            ),
            canonicalize_snapshots=False,
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


def _default_questions(
    request: CreateSessionRequest,
    sources: Sequence[EvidenceSource],
    count: int,
) -> tuple[PlannedQuestion, ...]:
    config = request.conversational_config
    assert config is not None
    interview_type = config.interview_type
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
    focus = ", ".join(area.replace("_", " ") for area in config.focus_areas)
    grounding = next(
        (
            source.snapshot_text[:160].strip()
            for source in sources
            if source.source_type == "job_posting" and source.snapshot_text.strip()
        ),
        "the supplied role context",
    )
    role_context = f"the {request.role_title} role"
    focus_context = f", focusing on {focus}" if focus else ""
    return tuple(
        PlannedQuestion(
            text=(
                f"For {role_context}{focus_context}, discuss a {category} example "
                f"relevant to: {grounding}"
            )[:10_000],
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
        if not text or len(text) > 10_000 or category not in _CATEGORIES:
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


def _validate_source_selection(
    request: CreateSessionRequest,
    sources: Sequence[EvidenceSource],
    *,
    require_exact_selected_ids: bool = False,
) -> None:
    config = request.conversational_config
    assert config is not None
    selection = config.evidence_selection
    application_sources = [
        source for source in sources if source.source_type == "application_cv"
    ]
    if len(application_sources) > 1:
        raise ValueError("application CV source selection is inconsistent")
    if selection.application_cv == "none" and application_sources:
        raise ValueError("application CV evidence is excluded by the request")
    if selection.application_cv == "approved_only" and any(
        source.approval_state != "approved" for source in application_sources
    ):
        raise ValueError("application CV approval does not match the request")
    if any(
        source.approval_state not in {"approved", "candidate_selected_unapproved"}
        for source in application_sources
    ) or (
        any(source.approval_state == "approved" for source in application_sources)
        and any(
            source.approval_state == "candidate_selected_unapproved"
            for source in application_sources
        )
    ):
        raise ValueError("application CV source selection is inconsistent")

    master_sources = [source for source in sources if source.source_type == "master_cv"]
    if selection.master_cv == "exclude" and master_sources:
        raise ValueError("master CV evidence is excluded by the request")
    if any(source.approval_state != "confirmed" for source in master_sources):
        raise ValueError("master CV evidence must be confirmed")

    question_sources = [
        source for source in sources if source.source_type == "question_bank"
    ]
    if any(source.approval_state == "draft" for source in question_sources) and not (
        selection.question_bank == "include_drafts" and selection.draft_evidence_consent
    ):
        raise ValueError("draft evidence requires selected explicit consent")
    allowed_question_approvals = (
        {"reviewed", "reviewed_final", "draft", "context_only"}
        if selection.question_bank == "include_drafts"
        else {"reviewed", "reviewed_final", "context_only"}
        if selection.question_bank == "reviewed_final_only"
        else set()
    )
    if any(
        source.approval_state not in allowed_question_approvals
        for source in question_sources
    ):
        raise ValueError("question bank evidence does not match the request")
    if any(
        source.approval_state == "context_only"
        and source.source_path != "question_bank/company_research_note"
        for source in question_sources
    ):
        raise ValueError("question bank context evidence type is invalid")
    if require_exact_selected_ids and any(
        source.approval_state != "context_only"
        and source.source_path != "question_bank/answer"
        for source in question_sources
    ):
        raise ValueError("question bank evidence type is invalid")
    selected_ids = set(selection.selected_question_bank_record_ids)
    if require_exact_selected_ids and selected_ids:
        built_ids = [source.source_record_id for source in question_sources]
        if set(built_ids) != selected_ids or len(built_ids) != len(selected_ids):
            raise ValueError(
                "question bank evidence does not match selected identifiers"
            )
    company_sources = [
        source for source in sources if source.source_type == "company_research"
    ]
    if len(company_sources) > 1:
        raise ValueError("company research source selection is inconsistent")
    if selection.company_research == "exclude" and company_sources:
        raise ValueError("company research is excluded by the request")
    if any(source.approval_state != "context_only" for source in company_sources):
        raise ValueError("company research must remain context only")

    job_sources = [source for source in sources if source.source_type == "job_posting"]
    if (require_exact_selected_ids and len(job_sources) != 1) or any(
        source.approval_state != "context_only" for source in job_sources
    ):
        raise ValueError("job posting evidence must remain context only")

    known_types = {
        "application_cv",
        "master_cv",
        "question_bank",
        "job_posting",
        "company_research",
    }
    if any(source.source_type not in known_types for source in sources):
        raise ValueError("evidence source type is not selected by the request")


def _build_evidence_records(
    sources: Sequence[EvidenceSource],
    *,
    allow_drafts: bool,
    canonicalize_snapshots: bool = True,
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
        snapshot = (
            _canonical_redacted_text(source.snapshot_text)
            if canonicalize_snapshots
            else source.snapshot_text
        )
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
    request: CreateSessionRequest | None = None,
    rebuild: bool = False,
    supported_locales: Sequence[str] = ("en-GB",),
    now: datetime | None = None,
    lease_seconds: int = DEFAULT_SETUP_LEASE_SECONDS,
    expected_state_version: int | None = None,
    candidate_command_id: str | None = None,
) -> SetupClaim:
    """Claim one initial, retry, or candidate-requested rebuild generation."""
    current = await db.get(InterviewSession, session_id)
    if current is None or current.experience_version != "conversational_v1":
        raise SessionPlanError("coach_conversation_invalid_state")
    await db.flush()
    await db.refresh(current)
    if (
        expected_state_version is not None
        and current.state_version != expected_state_version
    ):
        raise SessionPlanError("coach_conversation_version_conflict")
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

    if initial:
        if request is None:
            raise SessionPlanError("coach_conversation_invalid_state")
        authoritative_request = request
    else:
        if current.planning_request_json is None:
            raise SessionPlanError("coach_conversation_invalid_state")
        authoritative_request = CreateSessionRequest.model_validate(
            current.planning_request_json
        )
        if request is not None and request.model_dump(
            mode="json"
        ) != authoritative_request.model_dump(mode="json"):
            raise SessionPlanError("coach_conversation_invalid_state")
    config = authoritative_request.conversational_config
    if (
        authoritative_request.experience_version != "conversational_v1"
        or config is None
    ):
        raise SessionPlanError("coach_conversation_invalid_state")
    if config.locale not in frozenset(supported_locales):
        raise SessionPlanError("coach_locale_unsupported")

    claimed_at = now or datetime.utcnow()
    claim_expires_at = claimed_at + timedelta(seconds=lease_seconds)
    claim_token = secrets.token_hex(32)
    job = await AsyncJobService.create(db, "coach_session")
    prior_state = current.conversation_state
    increment_state = 0 if initial else 1
    values: dict[str, object] = {
        "setup_generation": InterviewSession.setup_generation + 1,
        "setup_attempt_count": InterviewSession.setup_attempt_count + 1,
        "setup_job_id": job.id,
        "setup_claim_token": claim_token,
        "setup_claimed_at": claimed_at,
        "setup_claim_expires_at": claim_expires_at,
        "setup_started_at": claimed_at,
        "setup_completed_at": None,
        "recoverable_error_code": None,
        "recoverable_error_scope": None,
        "recoverable_error_context_json": None,
        "conversation_state": "planning",
        "state_version": InterviewSession.state_version + increment_state,
    }
    if initial:
        values["planning_request_json"] = authoritative_request.model_dump(mode="json")
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
            *(
                (InterviewSession.state_version == expected_state_version,)
                if expected_state_version is not None
                else ()
            ),
        )
        .values(**values)
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
        candidate_command_id=candidate_command_id,
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
    _validate_canonical_evidence_build(build)
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
    try:
        effective_request = await load_claim_planning_request(
            db, claim=claim, now=completed_at
        )
    except SessionPlanError:
        return False
    _validate_build_for_request(
        build,
        request=effective_request,
    )
    nested = await db.begin_nested()
    try:
        job_transitioned = await db.execute(
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
            .returning(AsyncJob.id)
        )
        if job_transitioned.scalar_one_or_none() is None:
            await nested.rollback()
            return False

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
            await nested.rollback()
            return False

        await persist_session_plan(db, session_id=claim.session_id, build=build)
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
        await nested.commit()
        return True
    except BaseException:
        if nested.is_active:
            await nested.rollback()
        raise


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
    canonical_questions = _normalise_questions(
        build.questions,
        expected_count=expected_question_count,
        interview_type=config.interview_type,
    )
    if canonical_questions != build.questions:
        raise ValueError("plan questions are not canonical")
    build_sources = [
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
    ]
    _validate_source_selection(
        request,
        build_sources,
        require_exact_selected_ids=True,
    )
    _validate_canonical_evidence_build(build)
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


def _validate_canonical_evidence_build(build: SessionPlanBuild) -> None:
    selection = build.plan.evidence_selection
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
            selection.question_bank == "include_drafts"
            and selection.draft_evidence_consent
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
        build.plan.evidence_snapshot.record_count != len(build.evidence_records)
        or build.plan.evidence_snapshot.package_hash != expected_package_hash
    ):
        raise ValueError("plan evidence snapshot does not match the build")


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
    nested = await db.begin_nested()
    try:
        job_transitioned = await db.execute(
            update(AsyncJob)
            .where(
                AsyncJob.id == claim.job_id,
                AsyncJob.status.in_(("pending", "running")),
            )
            .values(
                status="failed",
                result_json=None,
                error=error_code,
                updated_at=failed_at,
            )
            .returning(AsyncJob.id)
        )
        if job_transitioned.scalar_one_or_none() is None:
            await nested.rollback()
            return False

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
            await nested.rollback()
            return False
        await _append_setup_events(
            db,
            session_id=claim.session_id,
            event_types=("session_plan_failed",),
            state_before="planning",
            state_after=state_after,
            state_version=state_version,
        )
        await db.flush()
        await nested.commit()
        return True
    except BaseException:
        if nested.is_active:
            await nested.rollback()
        raise


async def _append_setup_events(
    db: AsyncSession,
    *,
    session_id: str,
    event_types: Sequence[str],
    state_before: str | None,
    state_after: str,
    state_version: int,
    candidate_command_id: str | None = None,
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
                else (
                    "candidate"
                    if event_type
                    in {
                        "session_plan_retry_requested",
                        "session_plan_rebuild_requested",
                    }
                    and candidate_command_id is not None
                    else "system"
                ),
                command_id=(
                    candidate_command_id
                    if event_type
                    in {
                        "session_plan_retry_requested",
                        "session_plan_rebuild_requested",
                    }
                    else None
                ),
                payload_json=None,
            )
            for offset, event_type in enumerate(event_types)
        ]
    )
    await db.flush()
