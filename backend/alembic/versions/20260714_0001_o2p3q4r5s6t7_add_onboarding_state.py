"""add authoritative onboarding state

Revision ID: o2p3q4r5s6t7
Revises: n1o2p3q4r5s6
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
import yaml
from alembic import op

revision = "o2p3q4r5s6t7"
down_revision = "n1o2p3q4r5s6"
branch_labels = None
depends_on = None


def _profile_path() -> Path:
    if configured := os.getenv("PROFILE_PATH"):
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "data" / "profile.yaml"


def _non_empty_strings(value: Any) -> bool:
    return isinstance(value, list) and any(
        isinstance(item, str) and bool(item.strip()) for item in value
    )


def _backfill_state() -> tuple[str, str | None]:
    path = _profile_path()
    if not path.is_file():
        return "not_started", None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return "not_started", None
    if not isinstance(raw, dict):
        return "not_started", None

    candidate = raw.get("candidate")
    search = raw.get("search")
    name = candidate.get("name") if isinstance(candidate, dict) else None
    roles = search.get("target_roles") if isinstance(search, dict) else None
    locations = search.get("locations") if isinstance(search, dict) else None
    complete = (
        isinstance(name, str)
        and bool(name.strip())
        and _non_empty_strings(roles)
        and isinstance(locations, list)
        and bool(locations)
    )
    if complete:
        return "complete", "protect-workspace"
    if raw:
        return "in_progress", None
    return "not_started", None


def upgrade() -> None:
    op.create_table(
        "onboarding_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_completed_step", sa.String(64), nullable=True),
        sa.Column("finalization_id", sa.String(36), nullable=True),
        sa.Column("finalization_payload_hash", sa.String(64), nullable=True),
        sa.Column("finalized_profile_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_onboarding_state_singleton"),
        sa.CheckConstraint(
            "status IN ('not_started', 'in_progress', 'finalization_pending', 'complete')",
            name="ck_onboarding_state_status",
        ),
    )
    status, last_step = _backfill_state()
    now = datetime.utcnow()
    op.bulk_insert(
        sa.table(
            "onboarding_state",
            sa.column("id", sa.Integer()),
            sa.column("status", sa.String()),
            sa.column("last_completed_step", sa.String()),
            sa.column("created_at", sa.DateTime()),
            sa.column("updated_at", sa.DateTime()),
        ),
        [{
            "id": 1,
            "status": status,
            "last_completed_step": last_step,
            "created_at": now,
            "updated_at": now,
        }],
    )


def downgrade() -> None:
    op.drop_table("onboarding_state")

