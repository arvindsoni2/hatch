"""Add needs_enrichment column to job_postings.

Revision ID: f1g2h3i4j5k6
Revises: e1f2g3h4i5j6
Create Date: 2026-05-29 00:01:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f1g2h3i4j5k6"
down_revision = "e1f2g3h4i5j6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("needs_enrichment", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("job_postings", "needs_enrichment")
