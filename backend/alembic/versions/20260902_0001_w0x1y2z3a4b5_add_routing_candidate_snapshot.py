"""Add explicit immutable routing candidate snapshots.

Revision ID: w0x1y2z3a4b5
Revises: v9w0x1y2z3a4
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "w0x1y2z3a4b5"
down_revision: Union[str, None] = "v9w0x1y2z3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_routing_decisions", sa.Column("task_id", sa.String(length=128))
    )
    op.add_column("runtime_routing_decisions", sa.Column("task_version", sa.Integer()))
    op.add_column(
        "runtime_routing_decisions", sa.Column("model_version", sa.String(length=128))
    )
    op.add_column(
        "runtime_routing_decisions", sa.Column("candidate_snapshot_json", sa.JSON())
    )
    op.add_column(
        "runtime_routing_decisions", sa.Column("routing_policy_version", sa.Integer())
    )
    op.add_column(
        "runtime_routing_decisions",
        sa.Column("evidence_snapshot_id", sa.String(length=128)),
    )


def downgrade() -> None:
    with op.batch_alter_table("runtime_routing_decisions") as batch:
        batch.drop_column("evidence_snapshot_id")
        batch.drop_column("routing_policy_version")
        batch.drop_column("candidate_snapshot_json")
        batch.drop_column("model_version")
        batch.drop_column("task_version")
        batch.drop_column("task_id")
