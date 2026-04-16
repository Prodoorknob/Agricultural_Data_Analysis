"""Widen commodity columns to VARCHAR(20) to fit wheat_winter / wheat_spring.

Original schemas used VARCHAR(10) which is too short for the 12-character
labels wheat_winter and wheat_spring. Affects acreage_forecasts and
acreage_accuracy. Encountered during §7.4 WI-1 deployment (2026-04-14).

Revision ID: 006
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "acreage_forecasts", "commodity",
        existing_type=sa.String(10),
        type_=sa.String(20),
    )
    op.alter_column(
        "acreage_accuracy", "commodity",
        existing_type=sa.String(10),
        type_=sa.String(20),
    )


def downgrade():
    op.alter_column(
        "acreage_accuracy", "commodity",
        existing_type=sa.String(20),
        type_=sa.String(10),
    )
    op.alter_column(
        "acreage_forecasts", "commodity",
        existing_type=sa.String(20),
        type_=sa.String(10),
    )
