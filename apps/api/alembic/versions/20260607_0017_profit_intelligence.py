"""add deterministic daily profit intelligence

Revision ID: 0017_profit_intelligence
Revises: 0016_wastage_intelligence
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_profit_intelligence"
down_revision = "0016_wastage_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_profit_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("revenue_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("material_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("labour_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("electricity_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("overhead_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("gross_profit_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("profit_margin_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("profit_status", sa.String(30), nullable=False),
        sa.Column("largest_profit_risk", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revenue_paise >= 0", name="ck_daily_profit_revenue_non_negative"),
        sa.CheckConstraint("total_cost_paise >= 0", name="ck_daily_profit_cost_non_negative"),
        sa.CheckConstraint(
            "profit_status IN ('EXCELLENT', 'GOOD', 'WARNING', 'CRITICAL', 'DATA_NOT_AVAILABLE')",
            name="ck_daily_profit_status",
        ),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "snapshot_date", name="uq_daily_profit_factory_date"),
    )
    op.create_index("ix_daily_profit_snapshot_factory_id", "daily_profit_snapshot", ["factory_id"])
    op.create_index("ix_daily_profit_snapshot_snapshot_date", "daily_profit_snapshot", ["snapshot_date"])
    op.create_index("ix_daily_profit_snapshot_profit_status", "daily_profit_snapshot", ["profit_status"])

    op.create_table(
        "profit_alert_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message_sent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('WARNING', 'CRITICAL')", name="ck_profit_alert_status"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "snapshot_date", name="uq_profit_alert_factory_date"),
    )
    op.create_index("ix_profit_alert_log_factory_id", "profit_alert_log", ["factory_id"])
    op.create_index("ix_profit_alert_log_snapshot_date", "profit_alert_log", ["snapshot_date"])
    op.create_index("ix_profit_alert_log_status", "profit_alert_log", ["status"])


def downgrade() -> None:
    op.drop_table("profit_alert_log")
    op.drop_table("daily_profit_snapshot")
