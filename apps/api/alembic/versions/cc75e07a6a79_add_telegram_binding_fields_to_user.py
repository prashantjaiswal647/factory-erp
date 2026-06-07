"""add telegram binding fields to user

Revision ID: cc75e07a6a79
Revises: 0009_morning_briefing_log
"""

from alembic import op


revision = "cc75e07a6a79"
down_revision = "0009_morning_briefing_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(255)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_binding_code VARCHAR(50)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_binding_expiry TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_users_telegram_binding_code "
        "ON users (telegram_binding_code)"
    )


def downgrade() -> None:
    # These columns are part of the runtime baseline. Removing them from a
    # baseline-created database would make the schema inconsistent.
    pass
