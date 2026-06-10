"""add invoice delivery history

Revision ID: 0027_invoice_delivery_history
Revises: 0026_unified_alerts
"""

from alembic import op
import sqlalchemy as sa


revision = "0027_invoice_delivery_history"
down_revision = "0026_unified_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_delivery_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("invoice_document_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("destination_masked", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("channel IN ('DOWNLOAD', 'REPRINT', 'TELEGRAM', 'EMAIL')", name="ck_invoice_delivery_channel"),
        sa.CheckConstraint("status IN ('SENT', 'FAILED', 'COMPLETED')", name="ck_invoice_delivery_status"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.ForeignKeyConstraint(["invoice_document_id"], ["invoice_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invoice_delivery_logs_factory_id", "invoice_delivery_logs", ["factory_id"])
    op.create_index("ix_invoice_delivery_logs_invoice_document_id", "invoice_delivery_logs", ["invoice_document_id"])
    op.create_index("ix_invoice_delivery_logs_channel", "invoice_delivery_logs", ["channel"])
    op.create_index("ix_invoice_delivery_logs_status", "invoice_delivery_logs", ["status"])
    op.create_index("ix_invoice_delivery_logs_created_by_user_id", "invoice_delivery_logs", ["created_by_user_id"])
    op.create_index("ix_invoice_delivery_logs_created_at", "invoice_delivery_logs", ["created_at"])
    op.create_index(
        "idx_invoice_delivery_factory_invoice",
        "invoice_delivery_logs",
        ["factory_id", "invoice_document_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("invoice_delivery_logs")
