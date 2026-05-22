"""add_agentic_tables

Revision ID: a1b2c3d4e5f6
Revises: 2d22dcc71570
Create Date: 2026-04-09 00:01:00.000000+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "2d22dcc71570"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── agent_events ──────────────────────────────────────────
    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("source_agent", sa.String(32), nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.Column("processed_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index("idx_events_status", "agent_events", ["status", "event_type"])
    op.create_index("idx_events_created", "agent_events", ["created_at"])

    # ── agent_state ───────────────────────────────────────────
    op.create_table(
        "agent_state",
        sa.Column("agent_name", sa.String(32), primary_key=True),
        sa.Column("last_run_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(32), server_default="idle"),
        sa.Column("current_task", sa.Text, nullable=True),
        sa.Column("config", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.current_timestamp()),
    )

    # ── job_scores ────────────────────────────────────────────
    op.create_table(
        "job_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_postings.id"), nullable=False),
        sa.Column("overall_score", sa.Float, nullable=False),
        sa.Column("skill_match", sa.Float, nullable=True),
        sa.Column("experience_match", sa.Float, nullable=True),
        sa.Column("rate_match", sa.Float, nullable=True),
        sa.Column("location_match", sa.Float, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("scored_at", sa.DateTime, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("job_id", name="uq_job_scores_job_id"),
    )
    op.create_index("idx_scores_overall", "job_scores", ["overall_score"])

    # ── job_postings additions ────────────────────────────────
    with op.batch_alter_table("job_postings") as batch_op:
        batch_op.add_column(sa.Column("auto_scored", sa.Boolean, server_default="0"))
        batch_op.add_column(sa.Column("auto_tailored", sa.Boolean, server_default="0"))

    # ── applications additions ────────────────────────────────
    with op.batch_alter_table("applications") as batch_op:
        batch_op.add_column(sa.Column("agent_created", sa.Boolean, server_default="0"))
        batch_op.add_column(sa.Column("approval_status", sa.String(16), server_default="pending"))


def downgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_column("approval_status")
        batch_op.drop_column("agent_created")

    with op.batch_alter_table("job_postings") as batch_op:
        batch_op.drop_column("auto_tailored")
        batch_op.drop_column("auto_scored")

    op.drop_index("idx_scores_overall", table_name="job_scores")
    op.drop_table("job_scores")
    op.drop_table("agent_state")
    op.drop_index("idx_events_created", table_name="agent_events")
    op.drop_index("idx_events_status", table_name="agent_events")
    op.drop_table("agent_events")
