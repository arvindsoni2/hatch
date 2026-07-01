"""add persistent tailoring reviews

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
"""
from alembic import op
import sqlalchemy as sa

revision = "m8n9o0p1q2r3"
down_revision = "l7m8n9o0p1q2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tailoring_reviews",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cv_document_id", sa.String(36), sa.ForeignKey("generated_documents.id", ondelete="SET NULL")),
        sa.Column("cl_document_id", sa.String(36), sa.ForeignKey("generated_documents.id", ondelete="SET NULL")),
        sa.Column("review_json", sa.JSON(), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("variant", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_tailoring_reviews_application_created", "tailoring_reviews", ["application_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_tailoring_reviews_application_created", table_name="tailoring_reviews")
    op.drop_table("tailoring_reviews")
