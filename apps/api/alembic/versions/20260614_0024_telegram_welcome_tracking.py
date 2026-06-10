"""telegram welcome tracking

Revision ID: 0024_telegram_welcome_tracking
Revises: 0023_telegram_user_bindings
"""

from alembic import op


revision = "0024_telegram_welcome_tracking"
down_revision = "0023_telegram_user_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE telegram_user_bindings ADD COLUMN IF NOT EXISTS welcome_sent_at TIMESTAMPTZ")


def downgrade() -> None:
    op.drop_column("telegram_user_bindings", "welcome_sent_at")
