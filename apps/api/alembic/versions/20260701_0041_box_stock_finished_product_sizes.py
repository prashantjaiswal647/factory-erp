"""map finished goods to carton types and allowed product sizes

Revision ID: 20260701_0041
Revises: 20260630_0040
"""

from alembic import op
import sqlalchemy as sa


revision = "20260701_0041"
down_revision = "20260630_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    box_columns = {column["name"] for column in inspector.get_columns("box_stock")}
    if "size_for_finished_product" not in box_columns:
        op.add_column(
            "box_stock",
            sa.Column("size_for_finished_product", sa.String(length=500), nullable=False, server_default=""),
        )

    final_columns = {column["name"] for column in inspector.get_columns("final_product_stock")}
    if "carton_type" not in final_columns:
        op.add_column("final_product_stock", sa.Column("carton_type", sa.String(length=100), nullable=True))
        op.create_index("ix_final_product_stock_carton_type", "final_product_stock", ["carton_type"])


def downgrade() -> None:
    op.drop_index("ix_final_product_stock_carton_type", table_name="final_product_stock")
    op.drop_column("final_product_stock", "carton_type")
    op.drop_column("box_stock", "size_for_finished_product")
