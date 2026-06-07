"""add morning briefing log

Revision ID: 0009_morning_briefing_log
Revises: 0008_cashfree_order_sessions
"""

from alembic import op


revision = "0009_morning_briefing_log"
down_revision = "0008_cashfree_order_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS morning_briefing_log (
            id SERIAL PRIMARY KEY,
            factory_id INTEGER NOT NULL REFERENCES factories(id),
            briefing_date DATE NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            message_text TEXT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'generated',
            channel VARCHAR(30) NOT NULL DEFAULT 'telegram',
            error_message TEXT,
            CONSTRAINT uq_morning_briefing_factory_date_channel
                UNIQUE (factory_id, briefing_date, channel),
            CONSTRAINT ck_morning_briefing_status
                CHECK (status IN ('generated', 'sent', 'failed'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_morning_briefing_log_factory_id ON morning_briefing_log (factory_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_morning_briefing_log_briefing_date ON morning_briefing_log (briefing_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_morning_briefing_log_generated_at ON morning_briefing_log (generated_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS morning_briefing_log")
