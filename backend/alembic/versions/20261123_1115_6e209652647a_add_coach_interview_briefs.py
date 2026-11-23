"""add coach interview briefs

Revision ID: 6e209652647a
Revises: 54f861f6f61d
Create Date: 2026-11-23 11:15:09.144193+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e209652647a'
down_revision: Union[str, None] = '54f861f6f61d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coach_interview_briefs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "interview_round_id",
            sa.String(36),
            sa.ForeignKey("interview_rounds.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("enhancement_state", sa.String(16), nullable=False),
        sa.Column("enhancement_fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "enhanced_text_id",
            sa.String(36),
            sa.ForeignKey("coach_derived_text.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("coach_interview_briefs")
