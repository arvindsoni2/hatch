"""add coach focus areas and practice plans

Revision ID: f4f4b2b410de
Revises: ebfc0afaf8c9
Create Date: 2026-11-11 11:39:45.286953+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4f4b2b410de'
down_revision: Union[str, None] = 'ebfc0afaf8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coach_focus_areas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(80), nullable=False),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("group_json", sa.JSON(), nullable=True),
        sa.Column(
            "application_id",
            sa.String(36),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("criteria_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','paused','achieved','archived')",
            name="ck_coach_focus_areas_status",
        ),
        sa.CheckConstraint(
            "active_slot IS NULL OR active_slot IN (1,2,3)",
            name="ck_coach_focus_areas_slot",
        ),
        sa.CheckConstraint(
            "(status = 'active') = (active_slot IS NOT NULL)",
            name="ck_coach_focus_areas_active_slot",
        ),
    )
    op.create_index(
        "uq_coach_focus_areas_active_slot",
        "coach_focus_areas",
        ["active_slot"],
        unique=True,
    )
    op.create_table(
        "coach_practice_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column(
            "target_round_id",
            sa.String(36),
            sa.ForeignKey("interview_rounds.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft','active','completed','superseded','expired','discarded')",
            name="ck_coach_practice_plans_status",
        ),
        sa.CheckConstraint(
            "minutes BETWEEN 10 AND 120",
            name="ck_coach_practice_plans_minutes",
        ),
    )
    op.create_index(
        "uq_coach_practice_plans_one_active",
        "coach_practice_plans",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_coach_practice_plans_one_active", table_name="coach_practice_plans"
    )
    op.drop_table("coach_practice_plans")
    op.drop_index(
        "uq_coach_focus_areas_active_slot", table_name="coach_focus_areas"
    )
    op.drop_table("coach_focus_areas")
