"""Add legal_fields JSON column to job_postings for locale-aware compliance data.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-28 00:01:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("legal_fields", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("job_postings", "legal_fields")
