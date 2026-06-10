"""add recovery followups table

Revision ID: 0029_recovery_followups
Revises: 0028_telegram_action_alerts
Create Date: 2026-06-19

"""

from alembic import op
import sqlalchemy as sa


revision = "0029_recovery_followups"
down_revision = "0028_telegram_action_alerts"
branch_labels = None
depends_on = None


from sqlalchemy import inspect

def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "recovery_followups" not in tables:
        op.create_table(
            "recovery_followups",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("factory_id", sa.BigInteger(), nullable=False, index=True),
            sa.Column(
                "customer_id", sa.BigInteger(),
                sa.ForeignKey("customers.id"), nullable=False, index=True,
            ),
            sa.Column(
                "outstanding_bill_id", sa.BigInteger(),
                sa.ForeignKey("outstanding_bills.id"), nullable=True,
            ),
            sa.Column("suggested_amount_paise", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("due_days", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="suggested", index=True),
            sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_by_user_id", sa.BigInteger(),
                sa.ForeignKey("users.id"), nullable=False, index=True,
            ),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.func.now(), nullable=False,
            ),
        )

    # Idempotent index creation
    existing_indexes = []
    tables = inspector.get_table_names()
    if "recovery_followups" in tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("recovery_followups")]

    if "ix_recovery_followups_factory_status" not in existing_indexes:
        op.create_index(
            "ix_recovery_followups_factory_status",
            "recovery_followups",
            ["factory_id", "status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "recovery_followups" in tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("recovery_followups")]
        if "ix_recovery_followups_factory_status" in existing_indexes:
            op.drop_index(
                "ix_recovery_followups_factory_status",
                table_name="recovery_followups",
            )
        
        has_data = bind.execute(sa.text("SELECT 1 FROM recovery_followups LIMIT 1")).fetchone() is not None
        if not has_data:
            op.drop_table("recovery_followups")