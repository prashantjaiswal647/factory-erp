"""expand attendance statuses

Revision ID: 20260705_0045
Revises: 20260704_0044
"""

from alembic import op
import sqlalchemy as sa


revision = "20260705_0045"
down_revision = "20260704_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "attendance_logs" not in set(inspector.get_table_names()):
        return

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE attendance_logs DROP CONSTRAINT IF EXISTS ck_attendance_logs_status")
        op.execute(
            "ALTER TABLE attendance_logs ADD CONSTRAINT ck_attendance_logs_status "
            "CHECK (status IN ('Present','Absent','Weekly Off','Paid Holiday','Paid Leave','Half Day','Half-day'))"
        )


def downgrade() -> None:
    pass
