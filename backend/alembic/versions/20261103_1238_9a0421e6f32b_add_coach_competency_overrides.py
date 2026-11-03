"""add coach competency overrides

Revision ID: 9a0421e6f32b
Revises: a4b5c6d7e8f9
Create Date: 2026-11-03 12:38:43.394811+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a0421e6f32b'
down_revision: Union[str, None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coach_competency_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "application_id",
            sa.String(36),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original", sa.String(200), nullable=False),
        sa.Column("replacement", sa.String(200), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "idx_coach_competency_overrides_application_id",
        "coach_competency_overrides",
        ["application_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_coach_competency_overrides_application_id",
        table_name="coach_competency_overrides",
    )
    op.drop_table("coach_competency_overrides")
