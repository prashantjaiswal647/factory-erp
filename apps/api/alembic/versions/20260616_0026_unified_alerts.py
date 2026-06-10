"""add unified alerts

Revision ID: 0026_unified_alerts
Revises: 0025_supplier_and_purchase
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0026_unified_alerts"
down_revision = "0025_supplier_and_purchase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unified_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), server_default="INFO", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="OPEN", nullable=False),
        sa.Column("source_module", sa.String(length=50), nullable=False),
        sa.Column("related_entity_type", sa.String(length=100), nullable=True),
        sa.Column("related_entity_id", sa.String(length=100), nullable=True),
        sa.Column("related_route", sa.String(length=255), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("assigned_role", sa.String(length=50), server_default="Owner", nullable=False),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", sa.Integer(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("telegram_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("severity IN ('INFO', 'WARNING', 'CRITICAL')", name="ck_unified_alert_severity"),
        sa.CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')", name="ck_unified_alert_status"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.ForeignKeyConstraint(["acknowledged_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "dedupe_key", name="uq_unified_alert_factory_dedupe"),
    )
    op.create_index("ix_unified_alerts_factory_id", "unified_alerts", ["factory_id"])
    op.create_index("ix_unified_alerts_severity", "unified_alerts", ["severity"])
    op.create_index("ix_unified_alerts_status", "unified_alerts", ["status"])
    op.create_index("ix_unified_alerts_source_module", "unified_alerts", ["source_module"])
    op.create_index("ix_unified_alerts_assigned_role", "unified_alerts", ["assigned_role"])
    op.create_index("ix_unified_alerts_last_detected_at", "unified_alerts", ["last_detected_at"])
    op.create_index(
        "idx_unified_alert_factory_status_severity",
        "unified_alerts",
        ["factory_id", "status", "severity"],
    )


def downgrade() -> None:
    op.drop_table("unified_alerts")
