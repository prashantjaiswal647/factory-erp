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


from sqlalchemy import inspect

def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "invoice_delivery_logs" not in tables:
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

    # Idempotent index creation
    existing_indexes = []
    # Check again if table exists (it should now, if created above)
    tables = inspector.get_table_names()
    if "invoice_delivery_logs" in tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("invoice_delivery_logs")]

    indexes_to_create = [
        ("ix_invoice_delivery_logs_factory_id", ["factory_id"]),
        ("ix_invoice_delivery_logs_invoice_document_id", ["invoice_document_id"]),
        ("ix_invoice_delivery_logs_channel", ["channel"]),
        ("ix_invoice_delivery_logs_status", ["status"]),
        ("ix_invoice_delivery_logs_created_by_user_id", ["created_by_user_id"]),
        ("ix_invoice_delivery_logs_created_at", ["created_at"]),
        ("idx_invoice_delivery_factory_invoice", ["factory_id", "invoice_document_id", "created_at"]),
    ]

    for index_name, columns in indexes_to_create:
        if index_name not in existing_indexes:
            op.create_index(index_name, "invoice_delivery_logs", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "invoice_delivery_logs" in tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("invoice_delivery_logs")]
        indexes_to_drop = [
            "ix_invoice_delivery_logs_factory_id",
            "ix_invoice_delivery_logs_invoice_document_id",
            "ix_invoice_delivery_logs_channel",
            "ix_invoice_delivery_logs_status",
            "ix_invoice_delivery_logs_created_by_user_id",
            "ix_invoice_delivery_logs_created_at",
            "idx_invoice_delivery_factory_invoice",
        ]
        for index_name in indexes_to_drop:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="invoice_delivery_logs")

        has_data = bind.execute(sa.text("SELECT 1 FROM invoice_delivery_logs LIMIT 1")).fetchone() is not None
        if not has_data:
            op.drop_table("invoice_delivery_logs")
