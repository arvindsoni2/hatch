"""add coach pattern dismissals

Revision ID: ebfc0afaf8c9
Revises: f57c6504bbca
Create Date: 2026-11-10 12:41:32.930545+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ebfc0afaf8c9'
down_revision: Union[str, None] = 'f57c6504bbca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coach_pattern_dismissals",
        sa.Column("fingerprint", sa.String(64), primary_key=True),
        sa.Column("dismissed_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("coach_pattern_dismissals")
