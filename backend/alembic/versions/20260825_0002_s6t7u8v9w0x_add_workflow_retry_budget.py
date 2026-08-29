"""add durable workflow retry budget snapshot

Revision ID: s6t7u8v9w0x
Revises: r5s6t7u8v9w0
Create Date: 2026-08-25
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s6t7u8v9w0x"
down_revision: Union[str, None] = "r5s6t7u8v9w0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_workflow_runs",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    with op.batch_alter_table("runtime_workflow_runs") as batch_op:
        batch_op.drop_column("max_attempts")
