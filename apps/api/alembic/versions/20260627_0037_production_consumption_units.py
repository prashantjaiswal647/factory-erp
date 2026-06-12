"""add production consumption unit snapshots

Revision ID: 20260627_0037
Revises: 20260626_0036
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260627_0037"
down_revision = "20260626_0036"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("daily_productions")}
    additions = {
        "blank_used_bora": sa.Column("blank_used_bora", sa.Numeric(14, 3), nullable=False, server_default="0"),
        "blank_weight_per_bora_kg": sa.Column("blank_weight_per_bora_kg", sa.Numeric(14, 3), nullable=True),
        "bottom_used_rolls": sa.Column("bottom_used_rolls", sa.Integer(), nullable=False, server_default="0"),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("daily_productions", column)

    existing_checks = {
        check.get("name") for check in inspect(bind).get_check_constraints("daily_productions")
    }
    checks = {
        "ck_daily_productions_blank_bora_non_negative": "blank_used_bora >= 0",
        "ck_daily_productions_blank_weight_positive": "blank_weight_per_bora_kg IS NULL OR blank_weight_per_bora_kg > 0",
        "ck_daily_productions_bottom_rolls_non_negative": "bottom_used_rolls >= 0",
    }
    for name, condition in checks.items():
        if name not in existing_checks:
            op.create_check_constraint(name, "daily_productions", condition)


def downgrade():
    pass
