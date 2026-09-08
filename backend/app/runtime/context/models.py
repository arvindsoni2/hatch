"""Immutable, metadata-only contracts for declared runtime context."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Any, Literal, Protocol

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


INITIAL_CONTEXT_CAPABILITIES = frozenset(
    {
        "candidate.profile_summary",
        "candidate.verified_experience",
        "candidate.achievements",
        "candidate.skills",
        "candidate.resume_text",
        "job.summary",
        "job.requirements",
        "job.description",
        "application.current_cv",
        "application.current_cover_letter",
        "coach.session_context",
        "coach.question_context",
        "coach.transcript",
    }
)

_STABLE_CODE = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
_OPAQUE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_HASH = re.compile(r"^[a-f0-9]{64}$")
_MAX_METADATA_LENGTH = 256


class FrozenDict(dict[str, str]):
    """A JSON-serializable mapping that cannot be changed after validation."""

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("context metadata is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable


def _stable_code(value: str, field_name: str) -> str:
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > _MAX_METADATA_LENGTH
        or _STABLE_CODE.fullmatch(normalized) is None
    ):
        raise ValueError(f"{field_name} must be a bounded stable code")
    return normalized


def _opaque_ref(value: str, field_name: str) -> str:
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > _MAX_METADATA_LENGTH
        or _OPAQUE_REF.fullmatch(normalized) is None
        or "/" in normalized
        or "\\" in normalized
    ):
        raise ValueError(f"{field_name} must be an opaque bounded reference")
    return normalized


class ContextRequirement(BaseModel):
    """One explicitly requested context capability."""

    model_config = ConfigDict(frozen=True, strict=True)

    capability: str
    required: bool = True
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
    freshness_policy: str | None = None

    @field_validator("capability")
    @classmethod
    def _validate_capability(cls, value: str) -> str:
        return _stable_code(value, "capability")

    @field_validator("freshness_policy")
    @classmethod
    def _validate_freshness_policy(cls, value: str | None) -> str | None:
        return None if value is None else _stable_code(value, "freshness_policy")


class ContextItem(BaseModel):
    """An immutable, non-content-bearing reference to one source capability."""

    model_config = ConfigDict(frozen=True, strict=True)

    capability: str
    provider_id: str
    source_ref: str
    descriptor: str
    summary: str | None = Field(default=None, max_length=_MAX_METADATA_LENGTH)
    provenance: Mapping[str, str]
    freshness: AwareDatetime | None
    sensitivity: Literal["public", "internal", "confidential", "restricted"]
    token_estimate: int = Field(ge=0, le=32768)
    confidence: float | None = Field(default=None, ge=0, le=1)
    content_hash: str

    @field_validator("capability", "provider_id", "descriptor")
    @classmethod
    def _validate_stable_metadata(cls, value: str, info: Any) -> str:
        return _stable_code(value, info.field_name)

    @field_validator("source_ref")
    @classmethod
    def _validate_source_ref(cls, value: str) -> str:
        return _opaque_ref(value, "source_ref")

    @field_validator("content_hash")
    @classmethod
    def _validate_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _HASH.fullmatch(normalized) is None:
            raise ValueError("content_hash must be a sha256 hex digest")
        return normalized

    @model_validator(mode="after")
    def _freeze_provenance(self) -> ContextItem:
        object.__setattr__(self, "provenance", FrozenDict(self.provenance))
        return self


class ContextOmission(BaseModel):
    """A stable explanation for intentionally omitted optional context."""

    model_config = ConfigDict(frozen=True, strict=True)

    capability: str
    reason: str

    @field_validator("capability", "reason")
    @classmethod
    def _validate_codes(cls, value: str, info: Any) -> str:
        return _stable_code(value, info.field_name)


class ContextPackage(BaseModel):
    """An immutable package bound to exactly one task attempt."""

    model_config = ConfigDict(frozen=True, strict=True)

    id: str
    task_attempt_id: str
    items: tuple[ContextItem, ...]
    omissions: tuple[ContextOmission, ...] = ()
    total_token_estimate: int = Field(ge=0, le=32768)
    content_hash: str

    @field_validator("id", "task_attempt_id")
    @classmethod
    def _validate_identifiers(cls, value: str, info: Any) -> str:
        return _opaque_ref(value, info.field_name)

    @field_validator("content_hash")
    @classmethod
    def _validate_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _HASH.fullmatch(normalized) is None:
            raise ValueError("content_hash must be a sha256 hex digest")
        return normalized

    @model_validator(mode="after")
    def _validate_total(self) -> ContextPackage:
        if sum(item.token_estimate for item in self.items) != self.total_token_estimate:
            raise ValueError("total_token_estimate must match context items")
        return self


def validate_context_item_metadata(item: ContextItem) -> None:
    """Reject content-bearing or non-opaque item metadata at every write boundary."""
    if item.summary is not None:
        raise ValueError("context_package_metadata_unsafe")
    for key, value in item.provenance.items():
        _stable_code(key, "provenance_key")
        _opaque_ref(value, "provenance_value")


def context_package_hash(
    task_attempt_id: str,
    items: tuple[ContextItem, ...],
    omissions: tuple[ContextOmission, ...],
) -> str:
    """Derive the immutable package hash from JSON-mode durable metadata."""
    canonical = {
        "task_attempt_id": task_attempt_id,
        "items": [item.model_dump(mode="json") for item in items],
        "omissions": [omission.model_dump(mode="json") for omission in omissions],
    }
    return sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class ContextProvider(Protocol):
    """Read-only source wrapper registered by a product binding."""

    provider_id: str
    capabilities: tuple[str, ...]

    async def resolve(
        self, task_attempt_id: str, requirement: ContextRequirement
    ) -> ContextItem | None: ...
