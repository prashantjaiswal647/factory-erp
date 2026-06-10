"""add unified alerts

Revision ID: 0026_unified_alerts
Revises: 0025_supplier_and_purchase
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision = "0026_unified_alerts"
down_revision = "0025_supplier_and_purchase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if "unified_alerts" not in tables:
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

    # Make index creation idempotent
    existing_indexes = []
    if "unified_alerts" in tables or "unified_alerts" not in tables: # table exists now if created above
        # Check again in tables to get the correct state
        inspector = inspect(bind)
        tables = inspector.get_table_names()
        if "unified_alerts" in tables:
            existing_indexes = [idx["name"] for idx in inspector.get_indexes("unified_alerts")]

    indexes_to_create = [
        ("ix_unified_alerts_factory_id", ["factory_id"]),
        ("ix_unified_alerts_severity", ["severity"]),
        ("ix_unified_alerts_status", ["status"]),
        ("ix_unified_alerts_source_module", ["source_module"]),
        ("ix_unified_alerts_assigned_role", ["assigned_role"]),
        ("ix_unified_alerts_last_detected_at", ["last_detected_at"]),
        ("idx_unified_alert_factory_status_severity", ["factory_id", "status", "severity"]),
    ]

    for index_name, columns in indexes_to_create:
        if index_name not in existing_indexes:
            op.create_index(index_name, "unified_alerts", columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    
    if "unified_alerts" in tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("unified_alerts")]
        indexes_to_drop = [
            "ix_unified_alerts_factory_id",
            "ix_unified_alerts_severity",
            "ix_unified_alerts_status",
            "ix_unified_alerts_source_module",
            "ix_unified_alerts_assigned_role",
            "ix_unified_alerts_last_detected_at",
            "idx_unified_alert_factory_status_severity",
        ]
        for index_name in indexes_to_drop:
            if index_name in existing_indexes:
                op.drop_index(index_name, table_name="unified_alerts")
        
        # Safe drop: only drop the table if it is completely empty to prevent data loss
        has_data = bind.execute(sa.text("SELECT 1 FROM unified_alerts LIMIT 1")).fetchone() is not None
        if not has_data:
            op.drop_table("unified_alerts")
