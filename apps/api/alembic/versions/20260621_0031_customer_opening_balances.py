"""add customer opening outstanding and advance balance fields

Revision ID: 0031_customer_opening_balances
Revises: 0030_briefing_snapshots
Create Date: 2026-06-21

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from decimal import Decimal

revision = "0031_customer_opening_balances"
down_revision = "0030_briefing_snapshots"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("customers")]

    if "opening_outstanding_note" not in columns:
        op.add_column("customers", sa.Column("opening_outstanding_note", sa.Text(), nullable=True))
    if "opening_outstanding_date" not in columns:
        op.add_column("customers", sa.Column("opening_outstanding_date", sa.Date(), nullable=True))
    if "advance_balance" not in columns:
        op.add_column("customers", sa.Column("advance_balance", sa.Numeric(precision=14, scale=2), nullable=False, server_default="0.00"))
    if "advance_balance_note" not in columns:
        op.add_column("customers", sa.Column("advance_balance_note", sa.Text(), nullable=True))
    if "advance_balance_date" not in columns:
        op.add_column("customers", sa.Column("advance_balance_date", sa.Date(), nullable=True))

    # Update any existing records to ensure non-null values
    op.execute("UPDATE customers SET previous_due = 0 WHERE previous_due IS NULL")
    op.execute("UPDATE customers SET advance_balance = 0 WHERE advance_balance IS NULL")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("customers")]

    if "opening_outstanding_note" in columns:
        op.drop_column("customers", "opening_outstanding_note")
    if "opening_outstanding_date" in columns:
        op.drop_column("customers", "opening_outstanding_date")
    if "advance_balance" in columns:
        op.drop_column("customers", "advance_balance")
    if "advance_balance_note" in columns:
        op.drop_column("customers", "advance_balance_note")
    if "advance_balance_date" in columns:
        op.drop_column("customers", "advance_balance_date")
