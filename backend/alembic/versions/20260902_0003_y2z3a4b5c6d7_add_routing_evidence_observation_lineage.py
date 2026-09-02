"""Add typed routing-observation and qualification-threshold lineage.

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "y2z3a4b5c6d7"
down_revision: Union[str, None] = "x1y2z3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runtime_model_evidence", sa.Column("minimum_sample_size", sa.Integer())
    )
    for name, column in (
        ("routing_observation_type", sa.String(length=64)),
        ("task_id", sa.String(length=128)),
        ("task_version", sa.Integer()),
        ("model_id", sa.String(length=128)),
        ("model_version", sa.String(length=128)),
        ("provider", sa.String(length=64)),
        ("quality_score", sa.Numeric(precision=6, scale=5)),
        ("sample_size", sa.Integer()),
    ):
        op.add_column("runtime_evidence_observations", sa.Column(name, column))


def downgrade() -> None:
    with op.batch_alter_table("runtime_evidence_observations") as batch:
        for name in (
            "sample_size",
            "quality_score",
            "provider",
            "model_version",
            "model_id",
            "task_version",
            "task_id",
            "routing_observation_type",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("runtime_model_evidence") as batch:
        batch.drop_column("minimum_sample_size")
