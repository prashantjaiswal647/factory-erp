"""add factory authorized signatures

Revision ID: 20260706_0046
Revises: 20260705_0045
"""

from alembic import op
import sqlalchemy as sa


revision = "20260706_0046"
down_revision = "20260705_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "factory_authorized_signatures" not in tables:
        op.create_table(
            "factory_authorized_signatures",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("factory_id", sa.String(length=100), nullable=False),
            sa.Column("role", sa.String(length=30), nullable=False),
            sa.Column("file_path", sa.String(length=500), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
            sa.UniqueConstraint("factory_id", "role", name="uq_factory_authorized_signature_role"),
            sa.CheckConstraint("role IN ('owner', 'sub_owner', 'supervisor')", name="ck_factory_authorized_signature_role"),
        )
        op.create_index("ix_factory_authorized_signatures_factory_id", "factory_authorized_signatures", ["factory_id"])
        op.create_index("ix_factory_authorized_signatures_role", "factory_authorized_signatures", ["role"])
        op.create_index("ix_factory_authorized_signatures_uploaded_by_user_id", "factory_authorized_signatures", ["uploaded_by_user_id"])

    invoice_columns = {column["name"] for column in inspector.get_columns("invoice_documents")}
    if "generated_by_role" not in invoice_columns:
        op.add_column("invoice_documents", sa.Column("generated_by_role", sa.String(length=50), nullable=True))
        op.create_index("ix_invoice_documents_generated_by_role", "invoice_documents", ["generated_by_role"])


def downgrade() -> None:
    pass
