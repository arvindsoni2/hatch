"""add durable pre-invocation execution intent

Revision ID: v9w0x1y2z3a4
Revises: u8v9w0x1y2z3
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "v9w0x1y2z3a4"
down_revision: Union[str, None] = "u8v9w0x1y2z3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_task_attempts",
        sa.Column("side_effect_class", sa.String(length=64)),
    )
    op.add_column(
        "runtime_task_attempts",
        sa.Column(
            "execution_intent_active",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("runtime_task_attempts") as batch_op:
        batch_op.drop_column("execution_intent_active")
        batch_op.drop_column("side_effect_class")
