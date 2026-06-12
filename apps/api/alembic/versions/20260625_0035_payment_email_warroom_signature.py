"""payment email war room verification

Revision ID: 20260625_0035
Revises: 20260624_0034
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260625_0035"
down_revision = "0034_customer_ledger"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    customer_columns = {col["name"] for col in inspector.get_columns("customers")}
    if "email" not in customer_columns:
        op.add_column("customers", sa.Column("email", sa.String(length=255), nullable=True))

    customer_indexes = {idx["name"] for idx in inspector.get_indexes("customers")}
    if "ix_customers_email" not in customer_indexes:
        op.create_index("ix_customers_email", "customers", ["email"], unique=False)

    bill_columns = {col["name"] for col in inspector.get_columns("outstanding_bills")}
    if "owner_verification_status" not in bill_columns:
        op.add_column("outstanding_bills", sa.Column("owner_verification_status", sa.String(length=20), server_default="pending", nullable=False))
    if "owner_verified_paid_at" not in bill_columns:
        op.add_column("outstanding_bills", sa.Column("owner_verified_paid_at", sa.DateTime(timezone=True), nullable=True))
    if "owner_verified_paid_by" not in bill_columns:
        op.add_column("outstanding_bills", sa.Column("owner_verified_paid_by", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE outstanding_bills
        SET owner_verification_status = 'verified_paid',
            owner_verified_paid_at = COALESCE(updated_at, created_at)
        WHERE balance_amount <= 0
          AND owner_verification_status = 'pending'
        """
    )

    bill_indexes = {idx["name"] for idx in inspector.get_indexes("outstanding_bills")}
    if "ix_outstanding_bills_owner_verification_status" not in bill_indexes:
        op.create_index("ix_outstanding_bills_owner_verification_status", "outstanding_bills", ["owner_verification_status"], unique=False)

    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys("outstanding_bills")}
    if "fk_outstanding_bills_owner_verified_paid_by" not in foreign_keys:
        op.create_foreign_key("fk_outstanding_bills_owner_verified_paid_by", "outstanding_bills", "users", ["owner_verified_paid_by"], ["id"])

    check_constraints = {ck["name"] for ck in inspector.get_check_constraints("outstanding_bills")}
    if "ck_outstanding_bills_owner_verification" not in check_constraints:
        op.create_check_constraint("ck_outstanding_bills_owner_verification", "outstanding_bills", "owner_verification_status IN ('pending', 'verified_paid')")


def downgrade():
    op.drop_constraint("ck_outstanding_bills_owner_verification", "outstanding_bills", type_="check")
    op.drop_constraint("fk_outstanding_bills_owner_verified_paid_by", "outstanding_bills", type_="foreignkey")
    op.drop_index("ix_outstanding_bills_owner_verification_status", table_name="outstanding_bills")
    op.drop_column("outstanding_bills", "owner_verified_paid_by")
    op.drop_column("outstanding_bills", "owner_verified_paid_at")
    op.drop_column("outstanding_bills", "owner_verification_status")
    op.drop_index("ix_customers_email", table_name="customers")
    op.drop_column("customers", "email")
