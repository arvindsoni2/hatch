"""Add scoring_method, keyword_matches, keyword_misses to job_scores.

Revision ID: e1f2g3h4i5j6
Revises: c1d2e3f4a5b6
Create Date: 2026-05-29 00:00:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "e1f2g3h4i5j6"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_scores", sa.Column("scoring_method", sa.String(20), nullable=True))
    op.add_column("job_scores", sa.Column("keyword_matches", sa.JSON(), nullable=True))
    op.add_column("job_scores", sa.Column("keyword_misses", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_scores", "keyword_misses")
    op.drop_column("job_scores", "keyword_matches")
    op.drop_column("job_scores", "scoring_method")
