"""add deterministic cost variance snapshots and alert logs

Revision ID: 0013_cost_variance
Revises: 0012_cost_per_cup_daily
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_cost_variance"
down_revision = "0012_cost_per_cup_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_variance_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("today_cost", sa.Numeric(14, 6), nullable=True),
        sa.Column("seven_day_cost", sa.Numeric(14, 6), nullable=True),
        sa.Column("thirty_day_cost", sa.Numeric(14, 6), nullable=True),
        sa.Column("variance_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("variance_level", sa.String(20), server_default="NORMAL", nullable=False),
        sa.Column("primary_driver", sa.String(50), nullable=True),
        sa.Column("material_change_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("labour_change_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("electricity_change_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("overhead_change_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("variance_level IN ('NORMAL', 'WARNING', 'CRITICAL')", name="ck_daily_variance_level"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "snapshot_date", name="uq_daily_variance_factory_date"),
        if_not_exists=True,
    )
    op.create_index("ix_daily_variance_snapshot_factory_id", "daily_variance_snapshot", ["factory_id"], if_not_exists=True)
    op.create_index("ix_daily_variance_snapshot_snapshot_date", "daily_variance_snapshot", ["snapshot_date"], if_not_exists=True)
    op.create_index("ix_daily_variance_snapshot_variance_level", "daily_variance_snapshot", ["variance_level"], if_not_exists=True)

    op.create_table(
        "cost_variance_alert_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(30), server_default="telegram", nullable=False),
        sa.Column("status", sa.String(20), server_default="generated", nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('generated', 'sent', 'failed', 'skipped')", name="ck_cost_variance_alert_status"),
        sa.CheckConstraint("retry_count >= 0", name="ck_cost_variance_alert_retry_count"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "snapshot_date", "channel", name="uq_cost_variance_alert_factory_date_channel"),
        if_not_exists=True,
    )
    op.create_index("ix_cost_variance_alert_log_factory_id", "cost_variance_alert_log", ["factory_id"], if_not_exists=True)
    op.create_index("ix_cost_variance_alert_log_snapshot_date", "cost_variance_alert_log", ["snapshot_date"], if_not_exists=True)
    op.create_index("ix_cost_variance_alert_log_status", "cost_variance_alert_log", ["status"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("cost_variance_alert_log")
    op.drop_table("daily_variance_snapshot")
