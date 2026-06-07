"""add user preferred language

Revision ID: 0011_user_preferred_language
Revises: 0010_briefing_observability
"""

from alembic import op


revision = "0011_user_preferred_language"
down_revision = "0010_briefing_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "preferred_language VARCHAR(20) NOT NULL DEFAULT 'hinglish'"
    )
    op.execute(
        "ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_preferred_language"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_preferred_language "
        "CHECK (preferred_language IN ('en', 'hi', 'hinglish'))"
    )


def downgrade() -> None:
    # The runtime baseline may already include this preference column.
    pass
