"""add morning briefing delivery observability

Revision ID: 0010_briefing_observability
Revises: cc75e07a6a79
"""

from alembic import op


revision = "0010_briefing_observability"
down_revision = "cc75e07a6a79"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE morning_briefing_log "
        "ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE morning_briefing_log "
        "ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_morning_briefing_log_sent_at "
        "ON morning_briefing_log (sent_at)"
    )
    op.execute(
        "ALTER TABLE morning_briefing_log "
        "DROP CONSTRAINT IF EXISTS ck_morning_briefing_status"
    )
    op.execute(
        "ALTER TABLE morning_briefing_log ADD CONSTRAINT ck_morning_briefing_status "
        "CHECK (status IN ('generated', 'sent', 'failed', 'skipped'))"
    )
    op.execute(
        "ALTER TABLE morning_briefing_log "
        "DROP CONSTRAINT IF EXISTS ck_morning_briefing_retry_count"
    )
    op.execute(
        "ALTER TABLE morning_briefing_log ADD CONSTRAINT ck_morning_briefing_retry_count "
        "CHECK (retry_count >= 0)"
    )


def downgrade() -> None:
    # The runtime baseline may already contain these observability columns.
    # Production rollback uses the pre-migration database backup.
    pass
