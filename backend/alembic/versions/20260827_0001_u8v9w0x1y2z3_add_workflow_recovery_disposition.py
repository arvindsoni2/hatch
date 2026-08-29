"""add workflow recovery disposition

Revision ID: u8v9w0x1y2z3
Revises: t7u8v9w0x1y2
Create Date: 2026-08-27
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u8v9w0x1y2z3"
down_revision: Union[str, None] = "t7u8v9w0x1y2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_execution_claims",
        sa.Column("recovery_not_before", sa.DateTime()),
    )
    op.add_column(
        "runtime_execution_claims",
        sa.Column(
            "recovery_failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "runtime_execution_claims",
        sa.Column("last_recovery_error_code", sa.String(length=128)),
    )


def downgrade() -> None:
    with op.batch_alter_table("runtime_execution_claims") as batch_op:
        batch_op.drop_column("last_recovery_error_code")
        batch_op.drop_column("recovery_failure_count")
        batch_op.drop_column("recovery_not_before")
