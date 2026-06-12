"""add source-aware outstanding metadata

Revision ID: 0034_customer_ledger
Revises: 0033_customer_ledger_adjustments
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0034_customer_ledger"
down_revision = "0033_customer_ledger_adjustments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("outstanding_bills")}
    additions = (
        ("note", sa.Text()),
        ("created_by_user_id", sa.Integer()),
        ("updated_by_user_id", sa.Integer()),
        ("deleted_at", sa.DateTime(timezone=True)),
        ("deleted_by_user_id", sa.Integer()),
        ("deletion_reason", sa.Text()),
    )
    for name, column_type in additions:
        if name not in columns:
            op.add_column("outstanding_bills", sa.Column(name, column_type, nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("outstanding_bills")}
    if "ix_outstanding_bills_deleted_at" not in indexes:
        op.create_index("ix_outstanding_bills_deleted_at", "outstanding_bills", ["deleted_at"])

    # One-time compatibility backfill. Existing rows remain canonical and are not duplicated.
    op.execute(
        "UPDATE outstanding_bills SET source_type = 'opening_outstanding' "
        "WHERE source_type = 'opening_balance'"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("outstanding_bills")}
    for name in (
        "deletion_reason",
        "deleted_by_user_id",
        "deleted_at",
        "updated_by_user_id",
        "created_by_user_id",
        "note",
    ):
        if name in columns:
            op.drop_column("outstanding_bills", name)
