"""add explanation cache and replay storage

Revision ID: 0020_explanation_cache
Revises: 0019_per_size_daily
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0020_explanation_cache"
down_revision = "0019_per_size_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "explanation_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("factory_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False),
        sa.Column("language", sa.String(length=20), server_default="hinglish", nullable=False),
        sa.Column(
            "explanation_json",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("token_usage", sa.Integer(), server_default="0", nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("token_usage >= 0", name="ck_explanation_cache_token_usage_non_negative"),
        sa.CheckConstraint("hit_count >= 0", name="ck_explanation_cache_hit_count_non_negative"),
        sa.ForeignKeyConstraint(["factory_id"], ["factories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "factory_id",
            "snapshot_hash",
            "language",
            name="uq_explanation_cache_factory_hash_language",
        ),
    )
    op.create_index("ix_explanation_cache_snapshot_hash", "explanation_cache", ["snapshot_hash"])
    op.create_index("ix_explanation_cache_briefing_date", "explanation_cache", ["briefing_date"])
    op.create_index("ix_explanation_cache_factory_id", "explanation_cache", ["factory_id"])
    op.create_index(
        "ix_explanation_cache_factory_hash",
        "explanation_cache",
        ["factory_id", "snapshot_hash"],
    )
    op.create_index(
        "ix_explanation_cache_factory_date",
        "explanation_cache",
        ["factory_id", "briefing_date"],
    )


def downgrade() -> None:
    op.drop_table("explanation_cache")
