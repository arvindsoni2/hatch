"""Add fit_reasoning, strengths, score_gaps to job_scores.

Revision ID: g2h3i4j5k6l7
Revises: f1g2h3i4j5k6
Create Date: 2026-05-29 00:02:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "g2h3i4j5k6l7"
down_revision = "f1g2h3i4j5k6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_scores", sa.Column("fit_reasoning", sa.Text(), nullable=True))
    op.add_column("job_scores", sa.Column("strengths", sa.JSON(), nullable=True))
    op.add_column("job_scores", sa.Column("score_gaps", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_scores", "score_gaps")
    op.drop_column("job_scores", "strengths")
    op.drop_column("job_scores", "fit_reasoning")
