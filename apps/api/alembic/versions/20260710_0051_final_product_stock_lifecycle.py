"""Add lifecycle metadata to final product stock."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = "20260710_0051"
down_revision = "20260710_0050"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_name = "final_product_stock"

    columns = [
        ("source", sa.Column("source", sa.String(length=50), nullable=False, server_default="unknown")),
        ("is_auto_created", sa.Column("is_auto_created", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("is_active", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())),
        ("archived_at", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)),
        ("created_at", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())),
    ]
    for name, column in columns:
        if not _has_column(inspector, table_name, name):
            op.add_column(table_name, column)

    # Backfill older explicit rows conservatively. Cleanup scripts mark known bad rows inactive.
    bind.execute(text("UPDATE final_product_stock SET source = 'unknown' WHERE source IS NULL OR trim(source) = ''"))
    bind.execute(text("UPDATE final_product_stock SET is_auto_created = false WHERE is_auto_created IS NULL"))
    bind.execute(text("UPDATE final_product_stock SET is_active = true WHERE is_active IS NULL"))

    inspector = inspect(bind)
    indexes = [
        ("ix_final_product_stock_source", ["source"]),
        ("ix_final_product_stock_is_auto_created", ["is_auto_created"]),
        ("ix_final_product_stock_is_active", ["is_active"]),
        ("ix_final_product_stock_archived_at", ["archived_at"]),
        ("ix_final_product_stock_created_at", ["created_at"]),
    ]
    for index_name, columns_ in indexes:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns_, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    table_name = "final_product_stock"
    for index_name in (
        "ix_final_product_stock_created_at",
        "ix_final_product_stock_archived_at",
        "ix_final_product_stock_is_active",
        "ix_final_product_stock_is_auto_created",
        "ix_final_product_stock_source",
    ):
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
    inspector = inspect(bind)
    for column_name in ("created_at", "archived_at", "is_active", "is_auto_created", "source"):
        if _has_column(inspector, table_name, column_name):
            op.drop_column(table_name, column_name)
