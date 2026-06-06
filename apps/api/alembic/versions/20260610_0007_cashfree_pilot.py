"""add Cashfree pilot subscription fields and webhook inbox

Revision ID: 0007_cashfree_pilot
Revises: 20260605_0002
"""

from alembic import op


revision = "0007_cashfree_pilot"
down_revision = "20260605_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cashfree_webhook_events (
            id BIGSERIAL PRIMARY KEY,
            cf_event_id VARCHAR(128) NOT NULL,
            cf_event_type VARCHAR(64),
            factory_id INTEGER REFERENCES factories(id) ON DELETE SET NULL,
            payload JSONB,
            signature VARCHAR(512),
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at TIMESTAMPTZ,
            status VARCHAR(16) NOT NULL DEFAULT 'received',
            error_message TEXT,
            CONSTRAINT uq_cashfree_webhook_events_cf_event_id UNIQUE (cf_event_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_cashfree_webhook_events_status ON cashfree_webhook_events (status, received_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_cashfree_webhook_events_factory ON cashfree_webhook_events (factory_id)")
    for statement in (
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS cashfree_customer_id VARCHAR(64)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS cashfree_subscription_id VARCHAR(64)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS cashfree_plan_code VARCHAR(32)",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS trial_end TIMESTAMPTZ",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS current_period_start TIMESTAMPTZ",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS next_billing_at TIMESTAMPTZ",
        "ALTER TABLE factories ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ",
        "ALTER TABLE subscription_payments ADD COLUMN IF NOT EXISTS cf_order_id VARCHAR(64)",
        "ALTER TABLE subscription_payments ADD COLUMN IF NOT EXISTS cf_payment_id VARCHAR(64)",
        "ALTER TABLE subscription_payments ADD COLUMN IF NOT EXISTS cf_invoice_id VARCHAR(64)",
        "ALTER TABLE subscription_payments ADD COLUMN IF NOT EXISTS cf_event_id VARCHAR(128)",
    ):
        op.execute(statement)
    op.execute("DROP INDEX IF EXISTS uq_factories_cashfree_sub")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_factories_cashfree_sub ON factories (cashfree_subscription_id) WHERE cashfree_subscription_id IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_factories_cashfree_customer ON factories (cashfree_customer_id)")
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_subscription_payment_cf_event') THEN
            ALTER TABLE subscription_payments
            ADD CONSTRAINT fk_subscription_payment_cf_event
            FOREIGN KEY (cf_event_id) REFERENCES cashfree_webhook_events(cf_event_id) ON DELETE SET NULL;
          END IF;
        END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_subscription_payment_cf_event ON subscription_payments (cf_event_id)")
    op.execute("ALTER TABLE factories DROP CONSTRAINT IF EXISTS ck_factories_subscription_status")
    op.execute(
        """
        ALTER TABLE factories ADD CONSTRAINT ck_factories_subscription_status
        CHECK (subscription_status IN (
          'trial_active','trial_expired','active','inactive','expired','cancelled',
          'payment_pending','trial','suspended','pending','past_due'
        ))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE subscription_payments DROP CONSTRAINT IF EXISTS fk_subscription_payment_cf_event")
    op.execute("DROP INDEX IF EXISTS ix_subscription_payment_cf_event")
    for column in ("cf_event_id", "cf_invoice_id", "cf_payment_id", "cf_order_id"):
        op.execute(f"ALTER TABLE subscription_payments DROP COLUMN IF EXISTS {column}")
    op.execute("DROP TABLE IF EXISTS cashfree_webhook_events")
    op.execute("DROP INDEX IF EXISTS uq_factories_cashfree_sub")
    op.execute("DROP INDEX IF EXISTS ix_factories_cashfree_customer")
    for column in (
        "cancelled_at", "next_billing_at", "current_period_end", "current_period_start",
        "trial_end", "cashfree_plan_code", "cashfree_subscription_id", "cashfree_customer_id",
    ):
        op.execute(f"ALTER TABLE factories DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE factories DROP CONSTRAINT IF EXISTS ck_factories_subscription_status")
    op.execute(
        """
        ALTER TABLE factories ADD CONSTRAINT ck_factories_subscription_status
        CHECK (subscription_status IN (
          'trial_active','trial_expired','active','inactive','expired','cancelled',
          'payment_pending','trial','suspended'
        ))
        """
    )
