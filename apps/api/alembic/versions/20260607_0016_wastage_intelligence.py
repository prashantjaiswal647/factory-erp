"""add deterministic daily wastage intelligence

Revision ID: 0016_wastage_intelligence
Revises: 0015_factory_health
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_wastage_intelligence"
down_revision = "0015_factory_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_wastage_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("cups_produced", sa.Integer(), server_default="0", nullable=False),
        sa.Column("blank_used_kg", sa.Numeric(14, 3), server_default="0", nullable=False),
        sa.Column("bottom_used_kg", sa.Numeric(14, 3), server_default="0", nullable=False),
        sa.Column("actual_wastage_kg", sa.Numeric(14, 3), server_default="0", nullable=False),
        sa.Column("expected_wastage_kg", sa.Numeric(14, 3), server_default="0", nullable=False),
        sa.Column("wastage_percentage", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("estimated_loss_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wastage_status", sa.String(20), server_default="NORMAL", nullable=False),
        sa.Column("primary_wastage_source", sa.String(20), server_default="Mixed", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("cups_produced >= 0", name="ck_daily_wastage_cups_non_negative"),
        sa.CheckConstraint("actual_wastage_kg >= 0", name="ck_daily_wastage_actual_non_negative"),
        sa.CheckConstraint("expected_wastage_kg >= 0", name="ck_daily_wastage_expected_non_negative"),
        sa.CheckConstraint("estimated_loss_paise >= 0", name="ck_daily_wastage_loss_non_negative"),
        sa.CheckConstraint("wastage_status IN ('NORMAL', 'WARNING', 'CRITICAL')", name="ck_daily_wastage_status"),
        sa.CheckConstraint("primary_wastage_source IN ('Blank', 'Bottom', 'Mixed')", name="ck_daily_wastage_source"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "snapshot_date", name="uq_daily_wastage_factory_date"),
    )
    op.create_index("ix_daily_wastage_snapshot_factory_id", "daily_wastage_snapshot", ["factory_id"])
    op.create_index("ix_daily_wastage_snapshot_snapshot_date", "daily_wastage_snapshot", ["snapshot_date"])
    op.create_index("ix_daily_wastage_snapshot_wastage_status", "daily_wastage_snapshot", ["wastage_status"])

    op.create_table(
        "wastage_alert_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("message_sent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('NORMAL', 'WARNING', 'CRITICAL')", name="ck_wastage_alert_status"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "snapshot_date", name="uq_wastage_alert_factory_date"),
    )
    op.create_index("ix_wastage_alert_log_factory_id", "wastage_alert_log", ["factory_id"])
    op.create_index("ix_wastage_alert_log_snapshot_date", "wastage_alert_log", ["snapshot_date"])
    op.create_index("ix_wastage_alert_log_status", "wastage_alert_log", ["status"])


def downgrade() -> None:
    op.drop_table("wastage_alert_log")
    op.drop_table("daily_wastage_snapshot")
