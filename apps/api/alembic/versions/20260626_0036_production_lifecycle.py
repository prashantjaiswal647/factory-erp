"""add production lifecycle audit fields

Revision ID: 20260626_0036
Revises: 20260625_0035
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260626_0036"
down_revision = "20260625_0035"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("daily_productions", sa.Column("shift", sa.String(length=20), nullable=True))
    op.add_column("daily_productions", sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False))
    op.add_column("daily_productions", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.add_column("daily_productions", sa.Column("rejected_by_user_id", sa.Integer(), nullable=True))
    op.add_column("daily_productions", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("daily_productions", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("daily_productions", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_daily_productions_status", "daily_productions", ["status"])
    op.create_index("ix_daily_productions_created_by_user_id", "daily_productions", ["created_by_user_id"])
    op.create_index("ix_daily_productions_rejected_by_user_id", "daily_productions", ["rejected_by_user_id"])
    op.create_foreign_key("fk_daily_productions_created_by_user", "daily_productions", "users", ["created_by_user_id"], ["id"])
    op.create_foreign_key("fk_daily_productions_rejected_by_user", "daily_productions", "users", ["rejected_by_user_id"], ["id"])
    op.create_check_constraint("ck_daily_productions_status", "daily_productions", "status IN ('ACTIVE', 'REJECTED')")


def downgrade():
    op.drop_constraint("ck_daily_productions_status", "daily_productions", type_="check")
    op.drop_constraint("fk_daily_productions_rejected_by_user", "daily_productions", type_="foreignkey")
    op.drop_constraint("fk_daily_productions_created_by_user", "daily_productions", type_="foreignkey")
    op.drop_index("ix_daily_productions_rejected_by_user_id", table_name="daily_productions")
    op.drop_index("ix_daily_productions_created_by_user_id", table_name="daily_productions")
    op.drop_index("ix_daily_productions_status", table_name="daily_productions")
    for column in (
        "updated_at",
        "rejection_reason",
        "rejected_at",
        "rejected_by_user_id",
        "created_by_user_id",
        "status",
        "shift",
    ):
        op.drop_column("daily_productions", column)
