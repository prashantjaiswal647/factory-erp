"""Add universal daily sequence action events."""

from alembic import op
import sqlalchemy as sa


revision = "20260710_0050"
down_revision = "20260709_0049"
branch_labels = None
depends_on = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    return any(index["name"] == index_name for index in sa.inspect(bind).get_indexes(table_name))


def upgrade() -> None:
    if not _has_table("action_events"):
        op.create_table(
            "action_events",
            sa.Column("factory_id", sa.Integer(), nullable=False, index=True),
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("action_type", sa.String(length=100), nullable=False, index=True),
            sa.Column("module", sa.String(length=100), nullable=False, index=True),
            sa.Column("entity_type", sa.String(length=100), nullable=False, index=True),
            sa.Column("entity_id", sa.Integer(), nullable=True, index=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True, index=True),
            sa.Column("created_by_role", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False, index=True),
            sa.Column("shift", sa.String(length=50), nullable=True, index=True),
            sa.Column("before_payload_json", sa.JSON(), nullable=True),
            sa.Column("after_payload_json", sa.JSON(), nullable=True),
            sa.Column("impact_summary_json", sa.JSON(), nullable=True),
            sa.Column("rollback_payload_json", sa.JSON(), nullable=True),
            sa.Column("verified_by_user_id", sa.Integer(), nullable=True, index=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rolled_back_by_user_id", sa.Integer(), nullable=True, index=True),
            sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("rollback_reason", sa.Text(), nullable=True),
            sa.CheckConstraint("status IN ('pending', 'verified', 'rolled_back')", name="ck_action_events_status"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["verified_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["rolled_back_by_user_id"], ["users.id"]),
        )

    for index_name, columns in {
        "idx_action_events_factory_created": ["factory_id", "created_at"],
        "idx_action_events_factory_status": ["factory_id", "status"],
        "idx_action_events_entity": ["entity_type", "entity_id"],
    }.items():
        if not _has_index("action_events", index_name):
            op.create_index(index_name, "action_events", columns)


def downgrade() -> None:
    if _has_table("action_events"):
        op.drop_table("action_events")
