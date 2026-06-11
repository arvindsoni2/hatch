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
    with op.batch_alter_table("interview_sessions") as batch_op:
        batch_op.add_column(sa.Column("coach_mode", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("rubric", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("signals", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("parent_session_id", sa.String(36), nullable=True))
        batch_op.add_column(sa.Column("focus_areas", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("interview_sessions") as batch_op:
        batch_op.drop_column("focus_areas")
        batch_op.drop_column("parent_session_id")
        batch_op.drop_column("signals")
        batch_op.drop_column("rubric")
        batch_op.drop_column("coach_mode")
