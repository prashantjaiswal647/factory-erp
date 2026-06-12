"""add production lifecycle audit fields

Revision ID: 20260626_0036
Revises: 20260625_0035
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260626_0036"
down_revision = "20260625_0035"
branch_labels = None
depends_on = None


TABLE_NAME = "daily_productions"


def _inspector():
    return inspect(op.get_bind())


def _column_names():
    return {column["name"] for column in _inspector().get_columns(TABLE_NAME)}


def _index_names():
    return {index["name"] for index in _inspector().get_indexes(TABLE_NAME)}


def _foreign_key_names():
    return {foreign_key.get("name") for foreign_key in _inspector().get_foreign_keys(TABLE_NAME)}


def _check_constraint_names():
    return {constraint.get("name") for constraint in _inspector().get_check_constraints(TABLE_NAME)}


def _add_column_if_missing(column):
    if column.name not in _column_names():
        op.add_column(TABLE_NAME, column)


def _create_index_if_missing(name, columns):
    if name not in _index_names():
        op.create_index(name, TABLE_NAME, columns)


def _create_foreign_key_if_missing(name, local_columns):
    if name not in _foreign_key_names():
        op.create_foreign_key(name, TABLE_NAME, "users", local_columns, ["id"])


def upgrade():
    _add_column_if_missing(sa.Column("shift", sa.String(length=20), nullable=True))
    _add_column_if_missing(sa.Column("status", sa.String(length=20), server_default="ACTIVE", nullable=False))
    _add_column_if_missing(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    _add_column_if_missing(sa.Column("rejected_by_user_id", sa.Integer(), nullable=True))
    _add_column_if_missing(sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(sa.Column("rejection_reason", sa.Text(), nullable=True))
    _add_column_if_missing(
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )

    _create_index_if_missing("ix_daily_productions_status", ["status"])
    _create_index_if_missing("ix_daily_productions_created_by_user_id", ["created_by_user_id"])
    _create_index_if_missing("ix_daily_productions_rejected_by_user_id", ["rejected_by_user_id"])
    _create_foreign_key_if_missing("fk_daily_productions_created_by_user", ["created_by_user_id"])
    _create_foreign_key_if_missing("fk_daily_productions_rejected_by_user", ["rejected_by_user_id"])
    if "ck_daily_productions_status" not in _check_constraint_names():
        op.create_check_constraint(
            "ck_daily_productions_status",
            TABLE_NAME,
            "status IN ('ACTIVE', 'REJECTED')",
        )


def downgrade():
    if "ck_daily_productions_status" in _check_constraint_names():
        op.drop_constraint("ck_daily_productions_status", TABLE_NAME, type_="check")
    for constraint_name in (
        "fk_daily_productions_rejected_by_user",
        "fk_daily_productions_created_by_user",
    ):
        if constraint_name in _foreign_key_names():
            op.drop_constraint(constraint_name, TABLE_NAME, type_="foreignkey")
    for index_name in (
        "ix_daily_productions_rejected_by_user_id",
        "ix_daily_productions_created_by_user_id",
        "ix_daily_productions_status",
    ):
        if index_name in _index_names():
            op.drop_index(index_name, table_name=TABLE_NAME)
    for column in (
        "updated_at",
        "rejection_reason",
        "rejected_at",
        "rejected_by_user_id",
        "created_by_user_id",
        "status",
        "shift",
    ):
        if column in _column_names():
            op.drop_column(TABLE_NAME, column)
