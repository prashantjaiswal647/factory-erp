"""allow legacy blank stock rows to remain unmapped

Revision ID: 20260629_0039
Revises: 20260628_0038
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260629_0039"
down_revision = "20260628_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]: column
        for column in inspect(bind).get_columns("blank_stock")
    }
    linked_bottom = columns.get("linked_bottom_size_mm")
    if linked_bottom is not None and not linked_bottom.get("nullable", True):
        op.alter_column(
            "blank_stock",
            "linked_bottom_size_mm",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    # Legacy rows may intentionally have no safe bottom mapping. A destructive
    # downgrade would require inventing an invalid ML-to-MM relationship.
    pass
