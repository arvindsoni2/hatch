"""add outcome learning tables

Revision ID: k6l7m8n9o0p1
Revises: j5k6l7m8n9o0
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "k6l7m8n9o0p1"
down_revision = "j5k6l7m8n9o0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_score_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_postings.id")),
        sa.Column("base_fit_score", sa.Float()), sa.Column("skill_match", sa.Float()),
        sa.Column("experience_match", sa.Float()), sa.Column("rate_match", sa.Float()),
        sa.Column("location_match", sa.Float()), sa.Column("source", sa.String(64)),
        sa.Column("role_family", sa.String(256)), sa.Column("seniority", sa.String(32)),
        sa.Column("working_pattern", sa.String(32)), sa.Column("employment_type", sa.String(32)),
        sa.Column("ir35_status", sa.String(32)), sa.Column("freshness_bucket", sa.String(32)),
        sa.Column("job_age_days", sa.Integer()), sa.Column("cv_variant", sa.String(8)),
        sa.Column("cl_variant", sa.String(8)), sa.Column("scoring_method", sa.String(20)),
        sa.Column("scorer_version", sa.String(32), nullable=False),
        sa.Column("snapshot_quality", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("application_id", name="uq_application_score_snapshots_application_id"),
    )
    for name, column in (("idx_application_score_snapshots_job_id", "job_id"), ("idx_application_score_snapshots_created_at", "created_at"), ("idx_application_score_snapshots_source", "source"), ("idx_application_score_snapshots_role_family", "role_family")):
        op.create_index(name, "application_score_snapshots", [column])
    op.create_table(
        "application_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("outcome_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("metadata_json", sa.JSON()), sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("application_id", "outcome_type", name="uq_application_outcomes_app_type"),
    )
    op.create_index("idx_application_outcomes_application_id", "application_outcomes", ["application_id"])
    op.create_index("idx_application_outcomes_type", "application_outcomes", ["outcome_type"])
    op.create_index("idx_application_outcomes_occurred_at", "application_outcomes", ["occurred_at"])
    op.create_table(
        "opportunity_scores",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("job_postings.id"), nullable=False),
        sa.Column("base_fit_score", sa.Float(), nullable=False),
        sa.Column("outcome_adjustment", sa.Float(), nullable=False),
        sa.Column("opportunity_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("raw_sample_size", sa.Integer(), nullable=False),
        sa.Column("effective_sample_size", sa.Float(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False), sa.Column("signal_contributions", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(32), nullable=False),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("job_id", name="uq_opportunity_scores_job_id"),
    )
    op.create_index("idx_opportunity_scores_score", "opportunity_scores", ["opportunity_score"])
    op.create_index("idx_opportunity_scores_calculated_at", "opportunity_scores", ["calculated_at"])


def downgrade() -> None:
    op.drop_index("idx_opportunity_scores_calculated_at", table_name="opportunity_scores")
    op.drop_index("idx_opportunity_scores_score", table_name="opportunity_scores")
    op.drop_table("opportunity_scores")
    op.drop_index("idx_application_outcomes_occurred_at", table_name="application_outcomes")
    op.drop_index("idx_application_outcomes_type", table_name="application_outcomes")
    op.drop_index("idx_application_outcomes_application_id", table_name="application_outcomes")
    op.drop_table("application_outcomes")
    for name in ("idx_application_score_snapshots_role_family", "idx_application_score_snapshots_source", "idx_application_score_snapshots_created_at", "idx_application_score_snapshots_job_id"):
        op.drop_index(name, table_name="application_score_snapshots")
    op.drop_table("application_score_snapshots")
