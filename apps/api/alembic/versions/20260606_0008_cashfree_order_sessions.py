"""store Cashfree payment sessions

Revision ID: 0008_cashfree_order_sessions
Revises: 0007_cashfree_pilot
"""

from alembic import op


revision = "0008_cashfree_order_sessions"
down_revision = "0007_cashfree_pilot"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE subscription_payments ADD COLUMN IF NOT EXISTS cf_payment_session_id VARCHAR(255)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscription_payments_cf_order_id ON subscription_payments (cf_order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscription_payments_cf_payment_id ON subscription_payments (cf_payment_id)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_subscription_payments_cf_payment_id")
    op.execute("DROP INDEX IF EXISTS ix_subscription_payments_cf_order_id")
    op.execute("ALTER TABLE subscription_payments DROP COLUMN IF EXISTS cf_payment_session_id")
