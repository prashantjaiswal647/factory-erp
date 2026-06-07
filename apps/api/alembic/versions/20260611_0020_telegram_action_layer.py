"""telegram action layer tables

Revision ID: 0021_telegram_action_layer
Revises: 0020_explanation_cache
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_telegram_action_layer"
down_revision = "0020_explanation_cache"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "telegram_callback_dedupe",
        sa.Column("callback_id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("callback_id"),
        if_not_exists=True,
    )
    op.create_index("idx_tcd_factory", "telegram_callback_dedupe", ["factory_id"], if_not_exists=True)
    op.create_index("idx_tcd_received", "telegram_callback_dedupe", ["received_at"], if_not_exists=True)

    op.create_table(
        "telegram_action_session",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("step", sa.String(length=32), nullable=False),
        sa.Column(
            "payload_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("callback_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'committed', 'expired')",
            name="ck_telegram_action_session_status"
        ),
        if_not_exists=True,
    )
    op.create_index("idx_tas_factory_chat", "telegram_action_session", ["factory_id", "chat_id", "status"], if_not_exists=True)
    op.create_index(
        "idx_tas_expires",
        "telegram_action_session",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending'"),
        if_not_exists=True,
    )

def downgrade() -> None:
    op.drop_table("telegram_action_session")
    op.drop_table("telegram_callback_dedupe")
