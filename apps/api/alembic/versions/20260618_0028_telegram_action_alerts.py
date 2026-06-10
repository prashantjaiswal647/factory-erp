"""add telegram action alert throttle

Revision ID: 0028_telegram_action_alerts
Revises: 0027_invoice_delivery_history
Create Date: 2026-06-18
"""

from alembic import op
import sqlalchemy as sa


revision = "0028_telegram_action_alerts"
down_revision = "0027_invoice_delivery_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_action_alert_throttle",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("factory_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("action_type", sa.String(length=40), nullable=False, index=True),
        sa.Column("hour_bucket", sa.String(length=13), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "factory_id",
            "actor_user_id",
            "action_type",
            "hour_bucket",
            name="uq_telegram_action_alert_throttle_bucket",
        ),
    )
    op.create_index(
        "ix_telegram_action_alert_throttle_factory_hour",
        "telegram_action_alert_throttle",
        ["factory_id", "hour_bucket"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_action_alert_throttle_factory_hour",
        table_name="telegram_action_alert_throttle",
    )
    op.drop_table("telegram_action_alert_throttle")
