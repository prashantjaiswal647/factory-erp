"""add supplier and purchase tables

Revision ID: 0025_supplier_and_purchase
Revises: 0024_telegram_welcome_tracking
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_supplier_and_purchase"
down_revision = "0024_telegram_welcome_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Suppliers
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("gst_number", sa.String(length=50), nullable=True),
        sa.Column("outstanding_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "name", name="uq_suppliers_factory_name"),
        if_not_exists=True,
    )

    # 2. Purchase Entries
    op.create_table(
        "purchase_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("item_category", sa.String(length=50), nullable=False),
        sa.Column("product_size_ml", sa.Integer(), nullable=True),
        sa.Column("variety_design", sa.String(length=100), nullable=True),
        sa.Column("packaging_size_name", sa.String(length=100), nullable=True),
        sa.Column("bottom_size_mm", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), server_default="0", nullable=False),
        sa.Column("rate", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), server_default="0", nullable=False),
        sa.Column("bill_number", sa.String(length=100), nullable=True),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("received_status", sa.String(length=50), server_default="Pending", nullable=False),
        sa.Column("received_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )

    # 3. Purchase Rate History
    op.create_table(
        "purchase_rate_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("item_category", sa.String(length=50), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("rate", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("purchase_rate_history")
    op.drop_table("purchase_entries")
    op.drop_table("suppliers")
