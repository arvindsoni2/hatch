"""Drop application_attempts table (auto-apply feature removed).

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-06-11 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "i4j5k6l7m8n9"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite does not support DROP TABLE inside batch_alter_table;
    # guard with a COUNT check so the migration is safe on DBs that
    # never had the auto-apply feature (table may not exist).
    conn = op.get_bind()
    table_exists = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='application_attempts'"
        )
    ).scalar()
    if table_exists:
        op.drop_table("application_attempts")


def downgrade() -> None:
    op.create_table(
        "application_attempts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("job_url", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
