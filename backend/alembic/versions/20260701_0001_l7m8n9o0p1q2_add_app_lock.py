"""add app lock configuration and sessions

Revision ID: l7m8n9o0p1q2
Revises: k6l7m8n9o0p1
"""
from alembic import op
import sqlalchemy as sa

revision = "l7m8n9o0p1q2"
down_revision = "k6l7m8n9o0p1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_lock_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("last_unlocked_at", sa.DateTime()),
        sa.Column("last_password_changed_at", sa.DateTime()),
        sa.Column("failed_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_failed_attempt_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "app_lock_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_app_lock_sessions_session_hash", "app_lock_sessions", ["session_hash"])
    op.create_index("ix_app_lock_sessions_expires_at", "app_lock_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_app_lock_sessions_expires_at", table_name="app_lock_sessions")
    op.drop_index("ix_app_lock_sessions_session_hash", table_name="app_lock_sessions")
    op.drop_table("app_lock_sessions")
    op.drop_table("app_lock_config")
