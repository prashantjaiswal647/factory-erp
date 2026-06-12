"""add onboarding restore keys and canonical material fields

Revision ID: 20260628_0038
Revises: 20260627_0037
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260628_0038"
down_revision = "20260627_0037"
branch_labels = None
depends_on = None


ADDITIONS = {
    "customers": [
        sa.Column("customer_restore_key", sa.String(length=100), nullable=True),
    ],
    "workers": [
        sa.Column("worker_restore_key", sa.String(length=100), nullable=True),
    ],
    "machines": [
        sa.Column("machine_restore_key", sa.String(length=100), nullable=True),
    ],
    "blank_stock": [
        sa.Column("material_restore_key", sa.String(length=100), nullable=True),
        sa.Column("material_name", sa.String(length=255), nullable=True),
    ],
    "bottom_stock": [
        sa.Column("material_restore_key", sa.String(length=100), nullable=True),
        sa.Column("price_per_kg", sa.Numeric(14, 2), nullable=False, server_default="0"),
    ],
    "final_product_stock": [
        sa.Column("product_restore_key", sa.String(length=100), nullable=True),
    ],
}

INDEXES = {
    "customers": ("ix_customers_customer_restore_key", "customer_restore_key"),
    "workers": ("ix_workers_worker_restore_key", "worker_restore_key"),
    "machines": ("ix_machines_machine_restore_key", "machine_restore_key"),
    "blank_stock": ("ix_blank_stock_material_restore_key", "material_restore_key"),
    "bottom_stock": ("ix_bottom_stock_material_restore_key", "material_restore_key"),
    "final_product_stock": ("ix_final_product_stock_product_restore_key", "product_restore_key"),
}

UNIQUES = {
    "customers": ("uq_customers_factory_restore_key", ["factory_id", "customer_restore_key"]),
    "workers": ("uq_workers_factory_restore_key", ["factory_id", "worker_restore_key"]),
    "machines": ("uq_machines_factory_restore_key", ["factory_id", "machine_restore_key"]),
    "blank_stock": ("uq_blank_stock_factory_restore_key", ["factory_id", "material_restore_key"]),
    "bottom_stock": ("uq_bottom_stock_factory_restore_key", ["factory_id", "material_restore_key"]),
    "final_product_stock": ("uq_final_product_factory_restore_key", ["factory_id", "product_restore_key"]),
}


def upgrade():
    bind = op.get_bind()
    packaging_uniques = {
        constraint["name"] for constraint in inspect(bind).get_unique_constraints("packaging_profiles")
    }
    if "uq_packaging_profiles_factory_profile_name" in packaging_uniques:
        op.drop_constraint("uq_packaging_profiles_factory_profile_name", "packaging_profiles", type_="unique")
    if "uq_packaging_profiles_factory_sku" not in packaging_uniques:
        op.create_unique_constraint(
            "uq_packaging_profiles_factory_sku",
            "packaging_profiles",
            ["factory_id", "cup_size_ml", "print_design_name", "profile_name"],
        )

    for table_name, constraint_name in (
        ("workers", "uq_workers_factory_name"),
        ("machines", "uq_machines_factory_name"),
    ):
        inspector = inspect(bind)
        existing_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
        if constraint_name in existing_uniques:
            op.drop_constraint(constraint_name, table_name, type_="unique")

    for table_name, columns in ADDITIONS.items():
        inspector = inspect(bind)
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column in columns:
            if column.name not in existing_columns:
                op.add_column(table_name, column)

        inspector = inspect(bind)
        index_name, column_name = INDEXES[table_name]
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, [column_name])

        inspector = inspect(bind)
        unique_name, unique_columns = UNIQUES[table_name]
        existing_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints(table_name)}
        if unique_name not in existing_uniques:
            op.create_unique_constraint(unique_name, table_name, unique_columns)


def downgrade():
    pass
