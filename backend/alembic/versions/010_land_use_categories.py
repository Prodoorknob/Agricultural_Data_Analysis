"""Add land_use_categories table — ERS Major Land Uses state-level totals.

Feeds the Land & Economy tab's Land Use Mix chart with real pasture,
forest, urban, cropland, special, and other categories (was previously
hardcoded to zero beyond cropland).

Revision ID: 010
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "land_use_categories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("state_fips", sa.String(2), nullable=False),
        sa.Column("state_alpha", sa.String(2), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("acres", sa.Numeric(14, 1), nullable=True),
        sa.UniqueConstraint("state_fips", "year", "category", name="uq_land_use_categories"),
    )
    op.create_index("idx_land_use_state_year", "land_use_categories", ["state_fips", "year"])


def downgrade():
    op.drop_index("idx_land_use_state_year", table_name="land_use_categories")
    op.drop_table("land_use_categories")
