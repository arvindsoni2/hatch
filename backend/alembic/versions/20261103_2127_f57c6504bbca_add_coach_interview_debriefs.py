"""add coach interview debriefs

Revision ID: f57c6504bbca
Revises: 9a0421e6f32b
Create Date: 2026-11-03 21:27:05.977304+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f57c6504bbca'
down_revision: Union[str, None] = '9a0421e6f32b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coach_interview_debriefs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "interview_round_id",
            sa.String(36),
            sa.ForeignKey("interview_rounds.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("overall", sa.Integer(), nullable=True),
        sa.Column("expectation", sa.String(16), nullable=True),
        sa.Column("questions_json", sa.JSON(), nullable=True),
        sa.Column("went_well", sa.Text(), nullable=True),
        sa.Column("do_differently", sa.Text(), nullable=True),
        sa.Column("notes_text", sa.Text(), nullable=True),
        sa.Column("proposals_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_coach_interview_debriefs_status",
        "coach_interview_debriefs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_coach_interview_debriefs_status",
        table_name="coach_interview_debriefs",
    )
    op.drop_table("coach_interview_debriefs")
