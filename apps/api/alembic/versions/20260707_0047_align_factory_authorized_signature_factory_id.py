"""align factory authorized signature factory id type

Revision ID: 20260707_0047
Revises: 20260706_0046
"""

from alembic import op
import sqlalchemy as sa


revision = "20260707_0047"
down_revision = "20260706_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop constraints and indexes referencing the column first
    try:
        op.drop_constraint("uq_factory_authorized_signature_role", "factory_authorized_signatures")
    except Exception:
        pass

    # Alter column type to integer
    op.execute(
        "ALTER TABLE factory_authorized_signatures ALTER COLUMN factory_id TYPE INTEGER USING factory_id::integer"
    )

    # Re-create UniqueConstraint
    op.create_unique_constraint(
        "uq_factory_authorized_signature_role",
        "factory_authorized_signatures",
        ["factory_id", "role"]
    )

    # Add Foreign Key
    op.create_foreign_key(
        "fk_factory_authorized_signatures_factory_id",
        "factory_authorized_signatures",
        "factories",
        ["factory_id"],
        ["id"]
    )


def downgrade() -> None:
    pass
