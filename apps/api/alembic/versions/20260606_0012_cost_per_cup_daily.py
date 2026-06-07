"""add deterministic daily cost totals

Revision ID: 0012_cost_per_cup_daily
Revises: 0011_user_preferred_language
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_cost_per_cup_daily"
down_revision = "0011_user_preferred_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_per_cup_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("production_date", sa.Date(), nullable=False),
        sa.Column("size_ml", sa.Integer(), nullable=True),
        sa.Column("cups_produced_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_material_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_labour_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_electricity_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_overhead_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_production_cost_paise", sa.Integer(), server_default="0", nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source_quality", sa.String(length=20), server_default="partial", nullable=False),
        sa.Column(
            "missing_fields_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint("cups_produced_total >= 0", name="ck_cost_daily_cups_non_negative"),
        sa.CheckConstraint("total_material_cost_paise >= 0", name="ck_cost_daily_material_non_negative"),
        sa.CheckConstraint("total_labour_cost_paise >= 0", name="ck_cost_daily_labour_non_negative"),
        sa.CheckConstraint("total_electricity_cost_paise >= 0", name="ck_cost_daily_electricity_non_negative"),
        sa.CheckConstraint("total_overhead_cost_paise >= 0", name="ck_cost_daily_overhead_non_negative"),
        sa.CheckConstraint("total_production_cost_paise >= 0", name="ck_cost_daily_production_non_negative"),
        sa.CheckConstraint("source_quality IN ('complete', 'partial')", name="ck_cost_daily_source_quality"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cost_per_cup_daily_factory_id", "cost_per_cup_daily", ["factory_id"])
    op.create_index("ix_cost_per_cup_daily_production_date", "cost_per_cup_daily", ["production_date"])
    op.create_index("ix_cost_per_cup_daily_size_ml", "cost_per_cup_daily", ["size_ml"])
    op.create_index("ix_cost_per_cup_daily_source_quality", "cost_per_cup_daily", ["source_quality"])
    op.execute(
        "CREATE UNIQUE INDEX uq_cost_daily_factory_date_size "
        "ON cost_per_cup_daily (factory_id, production_date, COALESCE(size_ml, -1))"
    )


def downgrade() -> None:
    op.drop_table("cost_per_cup_daily")
