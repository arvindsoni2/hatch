"""Persist replay-safe promoted model-evidence lineage.

Revision ID: x1y2z3a4b5c6
Revises: w0x1y2z3a4b5
"""
from collections.abc import Sequence
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, None] = "w0x1y2z3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("runtime_model_evidence", sa.Column("model_version", sa.String(length=128)))
    op.add_column("runtime_model_evidence", sa.Column("qualification_id", sa.String(length=128)))
    op.add_column("runtime_model_evidence", sa.Column("qualification_version", sa.Integer()))
    op.add_column("runtime_model_evidence", sa.Column("observation_ids_json", sa.JSON()))
    op.add_column("runtime_model_evidence", sa.Column("quality_score", sa.Numeric(precision=6, scale=5)))

def downgrade() -> None:
    with op.batch_alter_table("runtime_model_evidence") as batch:
        batch.drop_column("quality_score")
        batch.drop_column("observation_ids_json")
        batch.drop_column("qualification_version")
        batch.drop_column("qualification_id")
        batch.drop_column("model_version")
