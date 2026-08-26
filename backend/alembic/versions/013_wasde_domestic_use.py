"""Add total_domestic_use to wasde_releases.

Part of the 2026-08 WASDE ingest correction: the PSD attribute for domestic
consumption never matched ("Total Domestic Cons." vs the real "Domestic
Consumption"), so stocks_to_use was silently computed as stocks / exports.
Storing domestic use makes the published ratio auditable from the table
alone. Units after the correction: million bushels for all quantity columns.

Revision ID: 013
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "wasde_releases",
        sa.Column("total_domestic_use", sa.Numeric(10, 2), nullable=True),
    )


def downgrade():
    op.drop_column("wasde_releases", "total_domestic_use")
