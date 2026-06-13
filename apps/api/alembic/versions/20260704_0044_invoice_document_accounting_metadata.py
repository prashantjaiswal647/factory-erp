"""add invoice document accounting metadata

Revision ID: 20260704_0044
Revises: 20260703_0043
"""

from alembic import op
import sqlalchemy as sa


revision = "20260704_0044"
down_revision = "20260703_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "invoice_documents" not in set(inspector.get_table_names()):
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("invoice_documents")
    }
    columns = {
        "accounting_locked": sa.Column(
            "accounting_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        "exported_at": sa.Column(
            "exported_at", sa.DateTime(timezone=True), nullable=True
        ),
        "shared_at": sa.Column(
            "shared_at", sa.DateTime(timezone=True), nullable=True
        ),
        "emailed_at": sa.Column(
            "emailed_at", sa.DateTime(timezone=True), nullable=True
        ),
        "printed_at": sa.Column(
            "printed_at", sa.DateTime(timezone=True), nullable=True
        ),
    }
    for name, column in columns.items():
        if name not in existing_columns:
            op.add_column("invoice_documents", column)


def downgrade() -> None:
    # Accounting metadata may already contain production state. Rollback is
    # restore-from-backup; never discard invoice metadata automatically.
    pass
