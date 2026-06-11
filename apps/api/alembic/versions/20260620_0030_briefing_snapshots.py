"""add briefing snapshots table

Revision ID: 0030_briefing_snapshots
Revises: 0029_recovery_followups
Create Date: 2026-06-20

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "0030_briefing_snapshots"
down_revision = "0029_recovery_followups"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # Determine JSON type based on dialect (PostgreSQL vs SQLite for tests)
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB if is_postgres else sa.JSON

    if "briefing_snapshots" not in tables:
        op.create_table(
            "briefing_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("factory_id", sa.Integer(), sa.ForeignKey("factories.id"), nullable=False, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, index=True),
            sa.Column("role", sa.String(length=50), nullable=False, index=True),
            sa.Column("briefing_date", sa.Date(), nullable=False, index=True),
            sa.Column("message_text", sa.Text(), nullable=False),
            sa.Column("snapshot_json", json_type, nullable=False),
            sa.Column("health_score", sa.Numeric(precision=5, scale=2), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="generated"),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

        op.create_unique_constraint(
            "uq_briefing_snapshots_factory_date_role_user",
            "briefing_snapshots",
            ["factory_id", "briefing_date", "role", "user_id"]
        )

    existing_indexes = []
    if "briefing_snapshots" in tables:
        try:
            existing_indexes = [idx["name"] for idx in inspector.get_indexes("briefing_snapshots")]
        except Exception:
            pass

    if "ix_briefing_snapshots_factory_role_date" not in existing_indexes:
        op.create_index(
            "ix_briefing_snapshots_factory_role_date",
            "briefing_snapshots",
            ["factory_id", "role", "briefing_date"]
        )

    if "ix_briefing_snapshots_factory_date" not in existing_indexes:
        op.create_index(
            "ix_briefing_snapshots_factory_date",
            "briefing_snapshots",
            ["factory_id", "briefing_date"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "briefing_snapshots" in tables:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("briefing_snapshots")]
        if "ix_briefing_snapshots_factory_role_date" in existing_indexes:
            op.drop_index("ix_briefing_snapshots_factory_role_date", table_name="briefing_snapshots")
        if "ix_briefing_snapshots_factory_date" in existing_indexes:
            op.drop_index("ix_briefing_snapshots_factory_date", table_name="briefing_snapshots")

        has_data = bind.execute(sa.text("SELECT 1 FROM briefing_snapshots LIMIT 1")).fetchone() is not None
        if not has_data:
            op.drop_table("briefing_snapshots")
