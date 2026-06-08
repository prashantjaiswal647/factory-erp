"""telegram self-service onboarding

Revision ID: 0022_telegram_self_service
Revises: 0021_telegram_action_layer
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_telegram_self_service"
down_revision = "0021_telegram_action_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE factories ADD COLUMN IF NOT EXISTS telegram_username VARCHAR(255)")
    op.execute("ALTER TABLE factories ADD COLUMN IF NOT EXISTS telegram_connected_at TIMESTAMPTZ")
    op.execute("ALTER TABLE factories ADD COLUMN IF NOT EXISTS telegram_last_message_at TIMESTAMPTZ")
    op.execute("ALTER TABLE factories ADD COLUMN IF NOT EXISTS telegram_last_message_status VARCHAR(30)")

    bind = op.get_bind()
    if not sa.inspect(bind).has_table("telegram_connect_tokens"):
        op.create_table(
            "telegram_connect_tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.Integer(), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["factory_id"], ["factories.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash", name="uq_telegram_connect_token_hash"),
        )
    op.create_index("ix_telegram_connect_tokens_factory_id", "telegram_connect_tokens", ["factory_id"], if_not_exists=True)
    op.create_index("ix_telegram_connect_tokens_owner_id", "telegram_connect_tokens", ["owner_id"], if_not_exists=True)
    op.create_index("ix_telegram_connect_tokens_token_hash", "telegram_connect_tokens", ["token_hash"], unique=True, if_not_exists=True)
    op.create_index("ix_telegram_connect_tokens_expires_at", "telegram_connect_tokens", ["expires_at"], if_not_exists=True)
    op.create_index("idx_telegram_connect_factory_owner", "telegram_connect_tokens", ["factory_id", "owner_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("telegram_connect_tokens")
