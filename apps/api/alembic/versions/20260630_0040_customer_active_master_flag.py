"""add active flag for replaceable customer master data

Revision ID: 20260630_0040
Revises: 20260629_0039
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260630_0040"
down_revision = "20260629_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in inspect(bind).get_columns("customers")}
    if "is_active" not in columns:
        op.add_column(
            "customers",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.create_index("ix_customers_is_active", "customers", ["is_active"], unique=False)


def downgrade() -> None:
    pass
