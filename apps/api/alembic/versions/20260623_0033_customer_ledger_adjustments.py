"""add customer ledger adjustments table

Revision ID: 0033_customer_ledger_adjustments
Revises: 0032_factory_expense_machine_id
Create Date: 2026-06-23

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0033_customer_ledger_adjustments"
down_revision = "0032_factory_expense_machine_id"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    
    if "customer_ledger_adjustments" not in inspector.get_table_names():
        op.create_table(
            "customer_ledger_adjustments",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.Integer(), nullable=False),
            sa.Column("adjustment_type", sa.String(20), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("linked_bill_id", sa.Integer(), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_by_name", sa.String(255), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("amount > 0", name="ck_ledger_adjustments_amount_positive"),
            sa.CheckConstraint(
                "adjustment_type IN ('add_balance', 'reduce_balance')",
                name="ck_ledger_adjustments_type_valid",
            ),
        )
        op.create_foreign_key(
            "fk_ledger_adjustments_customer_id",
            source_table="customer_ledger_adjustments",
            referent_table="customers",
            local_cols=["customer_id"],
            remote_cols=["id"]
        )
        op.create_foreign_key(
            "fk_ledger_adjustments_factory_id",
            source_table="customer_ledger_adjustments",
            referent_table="factories",
            local_cols=["factory_id"],
            remote_cols=["id"]
        )
        op.create_foreign_key(
            "fk_ledger_adjustments_linked_bill_id",
            source_table="customer_ledger_adjustments",
            referent_table="outstanding_bills",
            local_cols=["linked_bill_id"],
            remote_cols=["id"]
        )
        op.create_foreign_key(
            "fk_ledger_adjustments_created_by_user_id",
            source_table="customer_ledger_adjustments",
            referent_table="users",
            local_cols=["created_by_user_id"],
            remote_cols=["id"]
        )
        op.create_index(
            "ix_customer_ledger_adjustments_factory_id",
            "customer_ledger_adjustments",
            ["factory_id"]
        )
        op.create_index(
            "ix_customer_ledger_adjustments_customer_id",
            "customer_ledger_adjustments",
            ["customer_id"]
        )
        op.create_index(
            "ix_customer_ledger_adjustments_created_at",
            "customer_ledger_adjustments",
            ["created_at"]
        )
        op.create_index(
            "ix_customer_ledger_adjustments_linked_bill_id",
            "customer_ledger_adjustments",
            ["linked_bill_id"]
        )
        op.create_index(
            "ix_customer_ledger_adjustments_created_by_user_id",
            "customer_ledger_adjustments",
            ["created_by_user_id"]
        )
        op.create_index(
            "ix_customer_ledger_adjustments_factory_customer",
            "customer_ledger_adjustments",
            ["factory_id", "customer_id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "customer_ledger_adjustments" in inspector.get_table_names():
        op.drop_table("customer_ledger_adjustments")
