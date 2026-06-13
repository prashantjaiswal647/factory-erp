"""add shift production batches

Revision ID: 20260702_0042
Revises: 20260701_0041
"""

from alembic import op
import sqlalchemy as sa


revision = "20260702_0042"
down_revision = "20260701_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "production_batches" not in tables:
        op.create_table(
            "production_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("factory_id", sa.String(length=100), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("shift", sa.String(length=50), nullable=False),
            sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=False),
            sa.Column("finished_good_id", sa.Integer(), sa.ForeignKey("final_product_stock.id"), nullable=False),
            sa.Column("carton_type", sa.String(length=100), nullable=False),
            sa.Column("total_boxes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_loose_packets", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("converted_boxes_from_loose", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("remaining_loose_packets", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_blank_bora", sa.Numeric(14, 3), nullable=False, server_default="0"),
            sa.Column("total_bottom_roll", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("shift_wastage_kg", sa.Numeric(14, 3), nullable=False, server_default="0"),
            sa.Column("wastage_note", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    inspector = sa.inspect(bind)
    if "production_batch_worker_lines" not in set(inspector.get_table_names()):
        op.create_table(
            "production_batch_worker_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("factory_id", sa.String(length=100), nullable=False),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("production_batches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("worker_id", sa.Integer(), sa.ForeignKey("workers.id", ondelete="SET NULL"), nullable=True),
            sa.Column("daily_production_id", sa.Integer(), sa.ForeignKey("daily_productions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("boxes_made", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("loose_packets_made", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("blank_used_bora", sa.Numeric(14, 3), nullable=False, server_default="0"),
            sa.Column("bottom_used_roll", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("note", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("production_batch_worker_lines")
    op.drop_table("production_batches")
