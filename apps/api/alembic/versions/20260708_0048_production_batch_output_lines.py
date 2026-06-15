"""add nested production batch output lines

Revision ID: 20260708_0048
Revises: 20260707_0047
"""

from alembic import op
import sqlalchemy as sa


revision = "20260708_0048"
down_revision = "20260707_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "production_batch_output_lines" in set(inspector.get_table_names()):
        return
    op.create_table(
        "production_batch_output_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("factory_id", sa.String(length=100), nullable=False),
        sa.Column(
            "worker_line_id",
            sa.Integer(),
            sa.ForeignKey("production_batch_worker_lines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("finished_good_id", sa.Integer(), sa.ForeignKey("final_product_stock.id"), nullable=False),
        sa.Column(
            "daily_production_id",
            sa.Integer(),
            sa.ForeignKey("daily_productions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("boxes_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loose_packets_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("boxes_from_loose", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_production_batch_output_lines_worker_line_id",
        "production_batch_output_lines",
        ["worker_line_id"],
    )
    op.create_index(
        "ix_production_batch_output_lines_finished_good_id",
        "production_batch_output_lines",
        ["finished_good_id"],
    )


def downgrade() -> None:
    op.drop_table("production_batch_output_lines")
