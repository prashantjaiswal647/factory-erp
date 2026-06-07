"""add structured activity metadata for cost spike audit

Revision ID: 0014_cost_spike_activity
Revises: 0013_cost_variance
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0014_cost_spike_activity"
down_revision = "0013_cost_variance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("activity_logs")}
    if "metadata_json" not in columns:
        op.add_column(
            "activity_logs",
            sa.Column(
                "metadata_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_column("activity_logs", "metadata_json")
