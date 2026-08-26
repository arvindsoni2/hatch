"""add durable ambiguous-outcome reconciliation binding

Revision ID: t7u8v9w0x1y2
Revises: s6t7u8v9w0x
Create Date: 2026-08-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "t7u8v9w0x1y2"
down_revision: Union[str, None] = "s6t7u8v9w0x"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runtime_task_attempts", sa.Column("capability_id", sa.String(length=128)))
    op.add_column("runtime_task_attempts", sa.Column("capability_version", sa.Integer()))
    op.add_column("runtime_task_attempts", sa.Column("idempotency_class", sa.String(length=64)))
    op.add_column("runtime_task_attempts", sa.Column("reconciliation_reference", sa.String(length=128)))
    op.add_column(
        "runtime_execution_claims",
        sa.Column("purpose", sa.String(length=24), nullable=False, server_default="execution"),
    )


def downgrade() -> None:
    with op.batch_alter_table("runtime_execution_claims") as batch_op:
        batch_op.drop_column("purpose")
    with op.batch_alter_table("runtime_task_attempts") as batch_op:
        batch_op.drop_column("reconciliation_reference")
        batch_op.drop_column("idempotency_class")
        batch_op.drop_column("capability_version")
        batch_op.drop_column("capability_id")
