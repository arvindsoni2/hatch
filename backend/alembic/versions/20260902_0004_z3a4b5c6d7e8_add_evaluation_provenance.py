"""Add explicit bounded evaluation provenance and execution lineage.

Revision ID: z3a4b5c6d7e8
Revises: y2z3a4b5c6d7
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "z3a4b5c6d7e8"
down_revision: Union[str, None] = "y2z3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s",
}


def upgrade() -> None:
    with op.batch_alter_table(
        "runtime_evaluation_runs",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        for name, column in (
            ("evaluator_type", sa.String(length=24)),
            ("evaluation_spec_id", sa.String(length=128)),
            ("evaluation_spec_version", sa.Integer()),
            ("evaluator_model_id", sa.String(length=128)),
            ("evaluator_model_version", sa.String(length=128)),
            ("result", sa.String(length=24)),
            ("scores_json", sa.JSON()),
            ("reason_codes_json", sa.JSON()),
            ("validation_metrics_json", sa.JSON()),
            ("primary_execution_id", sa.String(length=36)),
            ("repair_execution_id", sa.String(length=36)),
            ("fallback_execution_id", sa.String(length=36)),
        ):
            batch.add_column(sa.Column(name, column))
        for name in (
            "primary_execution_id",
            "repair_execution_id",
            "fallback_execution_id",
        ):
            batch.create_foreign_key(
                f"fk_runtime_evaluation_runs_{name}",
                "runtime_execution_records",
                [name],
                ["id"],
            )
    op.add_column("runtime_validation_results", sa.Column("metrics_json", sa.JSON()))


def downgrade() -> None:
    with op.batch_alter_table(
        "runtime_evaluation_runs",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        for name in (
            "fallback_execution_id",
            "repair_execution_id",
            "primary_execution_id",
        ):
            batch.drop_constraint(
                f"fk_runtime_evaluation_runs_{name}", type_="foreignkey"
            )
        for name in (
            "fallback_execution_id",
            "repair_execution_id",
            "primary_execution_id",
            "validation_metrics_json",
            "reason_codes_json",
            "scores_json",
            "result",
            "evaluator_model_version",
            "evaluator_model_id",
            "evaluation_spec_version",
            "evaluation_spec_id",
            "evaluator_type",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("runtime_validation_results") as batch:
        batch.drop_column("metrics_json")
