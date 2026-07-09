"""add generated document export assets

Revision ID: n1o2p3q4r5s6
Revises: m8n9o0p1q2r3
"""
from alembic import op
import sqlalchemy as sa

revision = "n1o2p3q4r5s6"
down_revision = "m8n9o0p1q2r3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_document_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("application_id", sa.String(36), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_id", sa.String(36), nullable=False),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("generated_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("path_or_blob_ref", sa.String(512), nullable=False),
        sa.Column("generation_status", sa.String(32), nullable=False),
        sa.Column("error_message", sa.String(512)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("idx_generated_document_assets_application_id", "generated_document_assets", ["application_id"])
    op.create_index("idx_generated_document_assets_source_document_id", "generated_document_assets", ["source_document_id"])
    op.create_index("idx_generated_document_assets_status", "generated_document_assets", ["generation_status"])


def downgrade() -> None:
    op.drop_index("idx_generated_document_assets_status", table_name="generated_document_assets")
    op.drop_index("idx_generated_document_assets_source_document_id", table_name="generated_document_assets")
    op.drop_index("idx_generated_document_assets_application_id", table_name="generated_document_assets")
    op.drop_table("generated_document_assets")
