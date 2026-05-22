"""Add story bank tables (stories + story_usages).

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-01 00:01:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b7c8d9e0f1a2"
down_revision: str = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(220), nullable=False, unique=True),
        sa.Column("summary", sa.String(200), nullable=True),
        sa.Column("situation", sa.Text, nullable=True),
        sa.Column("task", sa.Text, nullable=True),
        sa.Column("action", sa.Text, nullable=True),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("reflection", sa.Text, nullable=True),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("skills", sa.JSON, nullable=True),
        sa.Column("metrics", sa.JSON, nullable=True),
        sa.Column("archetype_fit", sa.JSON, nullable=True),
        sa.Column("strength_score", sa.Float, nullable=False, server_default="5.0"),
        sa.Column("times_used", sa.Integer, nullable=False, server_default="0"),
        sa.Column("times_edited", sa.Integer, nullable=False, server_default="0"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("manual_rating", sa.Integer, nullable=True),
        sa.Column("source_session_id", sa.String(36),
                  sa.ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_question_id", sa.String(36),
                  sa.ForeignKey("session_questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("embedding", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("idx_stories_is_active", "stories", ["is_active"])
    op.create_index("idx_stories_strength_score", "stories", ["strength_score"])
    op.create_index("idx_stories_created_at", "stories", ["created_at"])

    op.create_table(
        "story_usages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("story_id", sa.String(36),
                  sa.ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(36),
                  sa.ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question_id", sa.String(36),
                  sa.ForeignKey("session_questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_confidence", sa.Float, nullable=True),
        sa.Column("match_stage", sa.String(20), nullable=True),
        sa.Column("used_at", sa.DateTime, nullable=False),
    )
    op.create_index("idx_story_usages_story_id", "story_usages", ["story_id"])
    op.create_index("idx_story_usages_session_id", "story_usages", ["session_id"])


def downgrade() -> None:
    op.drop_table("story_usages")
    op.drop_table("stories")
