"""Durable CV artifact publication ownership and reconciliation.

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
"""

from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "z3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cv_publications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("runtime_workflow_runs.id"),
            nullable=False,
        ),
        sa.Column(
            "attempt_id",
            sa.String(36),
            sa.ForeignKey("runtime_task_attempts.id"),
            nullable=False,
        ),
        sa.Column("owner_fence", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("staged_path", sa.String(512), nullable=False),
        sa.Column("final_path", sa.String(512), nullable=False, unique=True),
        sa.Column("artifact_hash", sa.String(64)),
        sa.Column("byte_count", sa.Integer()),
        sa.Column("section_count", sa.Integer()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("projection_json", sa.JSON()),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("generated_documents.id"),
            unique=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cv_publications_run_id", "cv_publications", ["run_id"])
    op.create_index("ix_cv_publications_attempt_id", "cv_publications", ["attempt_id"])


def downgrade():
    op.drop_table("cv_publications")
