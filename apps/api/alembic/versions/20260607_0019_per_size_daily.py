"""add per-size daily profit snapshots

Revision ID: 0019_per_size_daily
Revises: 0018_weekly_digest
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_per_size_daily"
down_revision = "0018_weekly_digest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "per_size_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("size_ml", sa.Integer(), nullable=False),
        sa.Column("revenue_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_paise", sa.Integer(), nullable=True),
        sa.Column("gross_profit_paise", sa.Integer(), nullable=True),
        sa.Column("margin_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("units_sold", sa.Integer(), server_default="0", nullable=False),
        sa.Column("units_produced", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("cost_source", sa.String(30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("size_ml > 0", name="ck_per_size_daily_size_positive"),
        sa.CheckConstraint("revenue_paise >= 0", name="ck_per_size_daily_revenue_non_negative"),
        sa.CheckConstraint("cost_paise IS NULL OR cost_paise >= 0", name="ck_per_size_daily_cost_non_negative"),
        sa.CheckConstraint("units_sold >= 0", name="ck_per_size_daily_units_sold_non_negative"),
        sa.CheckConstraint("units_produced >= 0", name="ck_per_size_daily_units_produced_non_negative"),
        sa.CheckConstraint(
            "status IN ('EXCELLENT', 'GOOD', 'WARNING', 'CRITICAL', 'DATA_NOT_AVAILABLE')",
            name="ck_per_size_daily_status",
        ),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "snapshot_date", "size_ml", name="uq_per_size_daily_factory_date_size"),
    )
    op.create_index("ix_per_size_daily_factory_id", "per_size_daily", ["factory_id"])
    op.create_index("ix_per_size_daily_snapshot_date", "per_size_daily", ["snapshot_date"])
    op.create_index("ix_per_size_daily_size_ml", "per_size_daily", ["size_ml"])
    op.create_index("ix_per_size_daily_status", "per_size_daily", ["status"])


def downgrade() -> None:
    op.drop_table("per_size_daily")
