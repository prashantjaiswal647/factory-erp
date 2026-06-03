"""runtime schema baseline

Revision ID: 20260603_0001
Revises:
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op


revision = "20260603_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the current model tables and apply legacy compatibility DDL.

    This baseline is intentionally additive/idempotent so it can be run against
    the existing production database without dropping or rewriting tenant data.
    """
    from models import Base
    from schema_compat import apply_runtime_compat_schema

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    apply_runtime_compat_schema(bind)


def downgrade() -> None:
    """No destructive rollback for the production baseline.

    Rollback for this first baseline must be handled through the pre-migration
    PostgreSQL backup because dropping tables/columns would destroy factory data.
    """
    return None
