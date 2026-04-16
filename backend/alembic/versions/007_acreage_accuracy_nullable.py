"""Make acreage_accuracy.model_forecast nullable.

The Prospective Plantings ETL upserts USDA data for all 50 states, but we
only model a subset (top 15 states per commodity). Without nullable
model_forecast, the ETL can't insert USDA-only rows for non-modeled states.

Frontend accuracy panel reads only rows where both model_forecast AND the
USDA column are populated, so nullability is safe.

Revision ID: 007
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "acreage_accuracy", "model_forecast",
        existing_type=sa.Numeric(10, 1),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "acreage_accuracy", "model_forecast",
        existing_type=sa.Numeric(10, 1),
        nullable=False,
    )
