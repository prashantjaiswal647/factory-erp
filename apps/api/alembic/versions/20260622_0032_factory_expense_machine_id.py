"""add factory_expenses machine_id column

Revision ID: 0032_factory_expense_machine_id
Revises: 0031_customer_opening_balances
Create Date: 2026-06-22

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0032_factory_expense_machine_id"
down_revision = "0031_customer_opening_balances"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    
    # Ensure factory_expenses table exists.
    if "factory_expenses" not in inspector.get_table_names():
        op.create_table(
            "factory_expenses",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("expense_name", sa.String(255), nullable=False, index=True),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("category", sa.String(100), nullable=False, server_default="General", index=True),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
            sa.Column("machine_id", sa.Integer(), nullable=True),
            sa.Column("factory_id", sa.Integer(), nullable=False),
        )
        op.create_foreign_key(
            "fk_factory_expenses_factory_id",
            source_table="factory_expenses",
            referent_table="factories",
            local_cols=["factory_id"],
            remote_cols=["id"]
        )
        op.create_foreign_key(
            "fk_factory_expenses_machine_id",
            source_table="factory_expenses",
            referent_table="machines",
            local_cols=["machine_id"],
            remote_cols=["id"],
            ondelete="SET NULL"
        )
        op.create_index(
            "ix_factory_expenses_machine_id",
            "factory_expenses",
            ["machine_id"],
            unique=False
        )
        return

    # Check for missing columns
    columns = {col["name"]: col for col in inspector.get_columns("factory_expenses")}
    
    if "factory_id" not in columns:
        op.add_column("factory_expenses", sa.Column("factory_id", sa.Integer(), nullable=True))
        fkeys = inspector.get_foreign_keys("factory_expenses")
        has_fk = any(
            fk["referred_table"] == "factories" and "factory_id" in fk["constrained_columns"]
            for fk in fkeys
        )
        if not has_fk:
            op.create_foreign_key(
                "fk_factory_expenses_factory_id",
                source_table="factory_expenses",
                referent_table="factories",
                local_cols=["factory_id"],
                remote_cols=["id"]
            )
        
    if "expense_name" not in columns:
        op.add_column("factory_expenses", sa.Column("expense_name", sa.String(255), nullable=True))
    if "amount" not in columns:
        op.add_column("factory_expenses", sa.Column("amount", sa.Numeric(14, 2), nullable=True))
    if "category" not in columns:
        op.add_column("factory_expenses", sa.Column("category", sa.String(100), nullable=False, server_default="General"))
    if "timestamp" not in columns:
        op.add_column("factory_expenses", sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    # Ensure machine_id exists
    if "machine_id" not in columns:
        op.add_column("factory_expenses", sa.Column("machine_id", sa.Integer(), nullable=True))

    # Ensure foreign key exists for machine_id
    fkeys = inspector.get_foreign_keys("factory_expenses")
    has_fk_machine = any(
        fk["referred_table"] == "machines" and "machine_id" in fk["constrained_columns"]
        for fk in fkeys
    )
    if not has_fk_machine:
        op.create_foreign_key(
            "fk_factory_expenses_machine_id",
            source_table="factory_expenses",
            referent_table="machines",
            local_cols=["machine_id"],
            remote_cols=["id"],
            ondelete="SET NULL"
        )

    # Ensure index exists for machine_id
    indexes = inspector.get_indexes("factory_expenses")
    has_idx_machine = any("machine_id" in idx["column_names"] for idx in indexes)
    if not has_idx_machine:
        op.create_index(
            "ix_factory_expenses_machine_id",
            "factory_expenses",
            ["machine_id"],
            unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "factory_expenses" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("factory_expenses")]
        if "machine_id" in columns:
            dialect = bind.dialect.name
            if dialect != "sqlite":
                try:
                    op.drop_constraint("fk_factory_expenses_machine_id", "factory_expenses", type_="foreignkey")
                except Exception:
                    pass
                try:
                    op.drop_index("ix_factory_expenses_machine_id", "factory_expenses")
                except Exception:
                    pass
            op.drop_column("factory_expenses", "machine_id")
