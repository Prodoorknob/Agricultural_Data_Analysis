"""Add bls_establishments table — QCEW state-year establishment + wage data.

Primary fill for Crops-tab OPERATIONS card (NASS has Census-year-only
coverage, QCEW is annual) and Land-&-Economy labor chart (NASS WAGE RATE
is sparse, QCEW covers every state-year 1990-present).

Revision ID: 011
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bls_establishments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("state_fips", sa.String(2), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("naics", sa.String(6), nullable=False),
        sa.Column("establishments", sa.Integer, nullable=True),
        sa.Column("employment", sa.Integer, nullable=True),
        sa.Column("avg_annual_pay", sa.Integer, nullable=True),
        sa.UniqueConstraint("state_fips", "year", "naics", name="uq_bls_establishments"),
    )
    op.create_index("idx_bls_state_year", "bls_establishments", ["state_fips", "year"])


def downgrade():
    op.drop_index("idx_bls_state_year", table_name="bls_establishments")
    op.drop_table("bls_establishments")
