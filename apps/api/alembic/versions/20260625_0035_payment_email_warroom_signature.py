"""payment email war room verification

Revision ID: 20260625_0035
Revises: 20260624_0034
"""
from alembic import op
import sqlalchemy as sa

revision = "20260625_0035"
down_revision = "0034_customer_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("email", sa.String(length=255), nullable=True))
    op.create_index("ix_customers_email", "customers", ["email"], unique=False)
    op.add_column("outstanding_bills", sa.Column("owner_verification_status", sa.String(length=20), server_default="pending", nullable=False))
    op.add_column("outstanding_bills", sa.Column("owner_verified_paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outstanding_bills", sa.Column("owner_verified_paid_by", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE outstanding_bills
        SET owner_verification_status = 'verified_paid',
            owner_verified_paid_at = COALESCE(updated_at, created_at)
        WHERE balance_amount <= 0
        """
    )
    op.create_index("ix_outstanding_bills_owner_verification_status", "outstanding_bills", ["owner_verification_status"], unique=False)
    op.create_foreign_key("fk_outstanding_bills_owner_verified_paid_by", "outstanding_bills", "users", ["owner_verified_paid_by"], ["id"])
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
