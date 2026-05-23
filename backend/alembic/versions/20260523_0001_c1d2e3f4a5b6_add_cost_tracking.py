"""Add cost_tracking table for LLM API usage observability.

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-05-23 00:01:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_tracking",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("agent_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_postings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_estimate", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(8), server_default="USD"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_cost_agent_date", "cost_tracking", ["agent_name", "created_at"])
    op.create_index("idx_cost_job_id", "cost_tracking", ["job_id"])


def downgrade() -> None:
    op.drop_index("idx_cost_job_id", table_name="cost_tracking")
    op.drop_index("idx_cost_agent_date", table_name="cost_tracking")
    op.drop_table("cost_tracking")
