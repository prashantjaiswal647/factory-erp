"""add weekly profit digest delivery log

Revision ID: 0018_weekly_digest
Revises: 0017_profit_intelligence
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_weekly_digest"
down_revision = "0017_profit_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weekly_digest_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("week_end", sa.Date(), nullable=False),
        sa.Column("message_sent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("week_start <= week_end", name="ck_weekly_digest_dates"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("factory_id", "week_start", name="uq_weekly_digest_factory_week"),
    )
    op.create_index("ix_weekly_digest_log_factory_id", "weekly_digest_log", ["factory_id"])
    op.create_index("ix_weekly_digest_log_week_start", "weekly_digest_log", ["week_start"])
    op.create_index("ix_weekly_digest_log_week_end", "weekly_digest_log", ["week_end"])
    op.create_index("ix_weekly_digest_log_message_sent", "weekly_digest_log", ["message_sent"])


def downgrade() -> None:
    op.drop_table("weekly_digest_log")
