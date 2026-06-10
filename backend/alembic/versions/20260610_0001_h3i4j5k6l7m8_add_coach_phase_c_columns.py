"""Add Phase C columns to interview_sessions: coach_mode, rubric, signals, parent_session_id, focus_areas.

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-06-10 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "h3i4j5k6l7m8"
down_revision = "g2h3i4j5k6l7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column("coach_mode", sa.String(16), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("rubric", sa.JSON(), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("signals", sa.JSON(), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column(
            "parent_session_id",
            sa.String(36),
            sa.ForeignKey("interview_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("focus_areas", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_sessions", "focus_areas")
    op.drop_column("interview_sessions", "parent_session_id")
    op.drop_column("interview_sessions", "signals")
    op.drop_column("interview_sessions", "rubric")
    op.drop_column("interview_sessions", "coach_mode")
