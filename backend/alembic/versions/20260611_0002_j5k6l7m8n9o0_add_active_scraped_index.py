"""Add idx_job_postings_active_scraped for hot list query.

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-06-11 00:00:02.000000
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "j5k6l7m8n9o0"
down_revision = "i4j5k6l7m8n9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_postings") as batch_op:
        batch_op.create_index(
            "idx_job_postings_active_scraped",
            ["is_active", "scraped_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("job_postings") as batch_op:
        batch_op.drop_index("idx_job_postings_active_scraped")
