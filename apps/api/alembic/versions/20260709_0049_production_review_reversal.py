"""Add production review and reversal audit fields."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql


revision = "20260709_0049"
down_revision = "20260708_0048"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("daily_productions")}
    json_type = postgresql.JSONB(astext_type=sa.Text()) if bind.dialect.name == "postgresql" else sa.JSON()

    columns = [
        ("reversed_by_user_id", sa.Column("reversed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)),
        ("reversed_at", sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True)),
        ("reversal_reason", sa.Column("reversal_reason", sa.Text(), nullable=True)),
        ("reversal_of_entry_id", sa.Column("reversal_of_entry_id", sa.Integer(), sa.ForeignKey("daily_productions.id", ondelete="SET NULL"), nullable=True)),
        ("verified_by_user_id", sa.Column("verified_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)),
        ("verified_at", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True)),
        ("stock_before_json", sa.Column("stock_before_json", json_type, nullable=True)),
        ("stock_after_json", sa.Column("stock_after_json", json_type, nullable=True)),
    ]
    for name, column in columns:
        if name not in existing_columns:
            op.add_column("daily_productions", column)

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE daily_productions DROP CONSTRAINT IF EXISTS ck_daily_productions_status")
        op.create_check_constraint(
            "ck_daily_productions_status",
            "daily_productions",
            "status IN ('ACTIVE', 'REJECTED', 'pending_review', 'verified', 'reversed')",
        )
        for column_name in ("reversed_by_user_id", "reversal_of_entry_id", "verified_by_user_id"):
            index_name = f"ix_daily_productions_{column_name}"
            exists = bind.execute(
                text("SELECT 1 FROM pg_indexes WHERE schemaname = current_schema() AND indexname = :name"),
                {"name": index_name},
            ).first()
            if exists is None:
                op.create_index(index_name, "daily_productions", [column_name])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE daily_productions DROP CONSTRAINT IF EXISTS ck_daily_productions_status")
        op.create_check_constraint(
            "ck_daily_productions_status",
            "daily_productions",
            "status IN ('ACTIVE', 'REJECTED')",
        )
    for column_name in (
        "stock_after_json",
        "stock_before_json",
        "verified_at",
        "verified_by_user_id",
        "reversal_of_entry_id",
        "reversal_reason",
        "reversed_at",
        "reversed_by_user_id",
    ):
        if _has_column(inspect(bind), "daily_productions", column_name):
            op.drop_column("daily_productions", column_name)
