"""add shift wastages table

Revision ID: 20260703_0043
Revises: 20260702_0042
"""

from alembic import op
import sqlalchemy as sa


revision = "20260703_0043"
down_revision = "20260702_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "shift_wastages" not in tables:
        op.create_table(
            "shift_wastages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("factory_id", sa.String(length=100), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("shift", sa.String(length=50), nullable=False),
            sa.Column("wastage_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("factory_id", "date", "shift", name="uq_shift_wastage_factory_date_shift"),
        )
    inspector = sa.inspect(bind)
    if "shift_wastages" in set(inspector.get_table_names()):
        op.create_index("ix_shift_wastages_factory_id", "shift_wastages", ["factory_id"], if_not_exists=True)
        op.create_index("ix_shift_wastages_date", "shift_wastages", ["date"], if_not_exists=True)
        op.create_index("ix_shift_wastages_shift", "shift_wastages", ["shift"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("shift_wastages")
