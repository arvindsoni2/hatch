"""add coach derived text cache

Revision ID: 54f861f6f61d
Revises: f4f4b2b410de
Create Date: 2026-11-17 13:23:24.338709+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54f861f6f61d'
down_revision: Union[str, None] = 'f4f4b2b410de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coach_derived_text",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("cache_key", sa.String(200), nullable=False, unique=True),
        sa.Column("text_json", sa.JSON(), nullable=False),
        sa.Column("model_identity", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "coach_derived_sources",
        sa.Column(
            "derived_text_id",
            sa.String(36),
            sa.ForeignKey("coach_derived_text.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_kind", sa.String(32), primary_key=True),
        sa.Column("source_id", sa.String(64), primary_key=True),
        sa.Column("source_version", sa.String(80), nullable=False),
    )
    op.create_index(
        "idx_coach_derived_sources_source",
        "coach_derived_sources",
        ["source_kind", "source_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_coach_derived_sources_source", table_name="coach_derived_sources"
    )
    op.drop_table("coach_derived_sources")
    op.drop_table("coach_derived_text")
