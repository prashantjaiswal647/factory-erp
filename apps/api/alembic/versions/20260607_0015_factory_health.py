"""add deterministic daily factory health snapshots

Revision ID: 0015_factory_health
Revises: 0014_cost_spike_activity
"""

from alembic import op
import sqlalchemy as sa


revision = "0015_factory_health"
down_revision = "0014_cost_spike_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_factory_health_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("production_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("attendance_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("collections_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("inventory_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("cost_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("overall_score", sa.Numeric(5, 2), server_default="0", nullable=False),
        sa.Column("health_status", sa.String(20), nullable=False),
        sa.Column("largest_strength", sa.String(30), nullable=False),
        sa.Column("largest_risk", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("health_status IN ('CRITICAL', 'WARNING', 'GOOD', 'EXCELLENT')", name="ck_factory_health_status"),
        sa.CheckConstraint("overall_score >= 0 AND overall_score <= 100", name="ck_factory_health_overall_range"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "snapshot_date", name="uq_factory_health_factory_date"),
        if_not_exists=True,
    )
    op.create_index("ix_daily_factory_health_snapshot_factory_id", "daily_factory_health_snapshot", ["factory_id"], if_not_exists=True)
    op.create_index("ix_daily_factory_health_snapshot_snapshot_date", "daily_factory_health_snapshot", ["snapshot_date"], if_not_exists=True)
    op.create_index("ix_daily_factory_health_snapshot_overall_score", "daily_factory_health_snapshot", ["overall_score"], if_not_exists=True)
    op.create_index("ix_daily_factory_health_snapshot_health_status", "daily_factory_health_snapshot", ["health_status"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("daily_factory_health_snapshot")
