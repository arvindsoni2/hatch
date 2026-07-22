"""add Coach C1 contract and snapshot fields

Revision ID: p3q4r5s6t7u8
Revises: o2p3q4r5s6t7
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p3q4r5s6t7u8"
down_revision = "o2p3q4r5s6t7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interview_sessions") as batch_op:
        batch_op.add_column(sa.Column("diagnostics", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("report_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "report_state",
                sa.String(length=16),
                nullable=False,
                server_default="not_started",
            )
        )
        batch_op.add_column(sa.Column("report_job_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("report_started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("activity_version", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_check_constraint(
            "ck_interview_sessions_report_state",
            "report_state IN ('not_started', 'building', 'completed', 'fallback', 'failed')",
        )

    with op.batch_alter_table("session_questions") as batch_op:
        batch_op.add_column(sa.Column("requirement_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("model_answer_diagnostics", sa.JSON(), nullable=True))

    with op.batch_alter_table("session_recordings") as batch_op:
        batch_op.add_column(sa.Column("evaluation_state", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("async_job_id", sa.String(length=36), nullable=True))
        batch_op.create_check_constraint(
            "ck_session_recordings_evaluation_state",
            "evaluation_state IS NULL OR evaluation_state IN "
            "('pending', 'completed', 'unavailable', 'invalid', 'skipped', 'failed')",
        )

    # Preserve explicit skips and embedded C1 states. Every other parseable
    # historical evaluation is completed per the compatibility contract;
    # malformed/absent data remains legacy/unknown rather than pending.
    op.execute(
        sa.text(
            """
            UPDATE session_recordings
            SET evaluation_state = CASE
                WHEN transcript = '[SKIPPED]' THEN 'skipped'
                WHEN evaluation_json IS NOT NULL AND json_valid(evaluation_json) = 1 THEN
                    CASE
                        WHEN json_extract(evaluation_json, '$.evaluation_state') IN
                            ('pending', 'completed', 'unavailable', 'invalid',
                             'skipped', 'failed')
                        THEN json_extract(evaluation_json, '$.evaluation_state')
                        ELSE 'completed'
                    END
                ELSE NULL
            END
            """
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("session_recordings") as batch_op:
        batch_op.drop_constraint(
            "ck_session_recordings_evaluation_state", type_="check"
        )
        batch_op.drop_column("async_job_id")
        batch_op.drop_column("evaluation_state")

    with op.batch_alter_table("session_questions") as batch_op:
        batch_op.drop_column("model_answer_diagnostics")
        batch_op.drop_column("requirement_id")

    with op.batch_alter_table("interview_sessions") as batch_op:
        batch_op.drop_constraint("ck_interview_sessions_report_state", type_="check")
        batch_op.drop_column("activity_version")
        batch_op.drop_column("report_started_at")
        batch_op.drop_column("report_job_id")
        batch_op.drop_column("report_state")
        batch_op.drop_column("report_json")
        batch_op.drop_column("diagnostics")
