"""user-level telegram bindings

Revision ID: 0023_telegram_user_bindings
Revises: 0022_telegram_self_service
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_telegram_user_bindings"
down_revision = "0022_telegram_self_service"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("telegram_user_bindings"):
        op.create_table(
            "telegram_user_bindings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=50), nullable=False),
            sa.Column("telegram_chat_id", sa.String(length=255), nullable=False),
            sa.Column("telegram_username", sa.String(length=255), nullable=True),
            sa.Column("telegram_first_name", sa.String(length=255), nullable=True),
            sa.Column("telegram_connected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_message_status", sa.String(length=30), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("role IN ('Owner', 'Sub-Owner')", name="ck_telegram_user_binding_role"),
            sa.ForeignKeyConstraint(["factory_id"], ["factories.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("factory_id", "user_id", name="uq_telegram_user_binding_factory_user"),
            sa.UniqueConstraint("user_id", name="uq_telegram_user_bindings_user_id"),
            sa.UniqueConstraint("telegram_chat_id", name="uq_telegram_user_bindings_chat_id"),
        )
    op.create_index("ix_telegram_user_bindings_factory_id", "telegram_user_bindings", ["factory_id"], if_not_exists=True)
    op.create_index("ix_telegram_user_bindings_user_id", "telegram_user_bindings", ["user_id"], unique=True, if_not_exists=True)
    op.create_index("ix_telegram_user_bindings_role", "telegram_user_bindings", ["role"], if_not_exists=True)
    op.create_index("ix_telegram_user_bindings_chat_id", "telegram_user_bindings", ["telegram_chat_id"], unique=True, if_not_exists=True)
    op.create_index("ix_telegram_user_bindings_is_active", "telegram_user_bindings", ["is_active"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("telegram_user_bindings")
