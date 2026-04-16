"""Add Tier 1 acreage data source tables (drought, RMA, CRP, exports).

Revision ID: 004
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    # State-level drought severity index (USDM DSCI)
    op.create_table(
        "drought_index",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("state_fips", sa.String(2), nullable=False),
        sa.Column("year", sa.SmallInteger, nullable=False),
        sa.Column("dsci_nov", sa.Numeric(6, 1), nullable=True),
        sa.Column("dsci_fall_avg", sa.Numeric(6, 1), nullable=True),
        sa.Column("dsci_winter_avg", sa.Numeric(6, 1), nullable=True),
        sa.Column("drought_weeks_d2plus", sa.SmallInteger, nullable=True),
        sa.UniqueConstraint("state_fips", "year", name="uq_drought_index"),
    )

    # RMA crop insurance insured acreage (Summary of Business)
    op.create_table(
        "rma_insured_acres",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("state_fips", sa.String(2), nullable=False),
        sa.Column("commodity", sa.String(10), nullable=False),
        sa.Column("crop_year", sa.SmallInteger, nullable=False),
        sa.Column("net_reported_acres", sa.Numeric(12, 1), nullable=True),
        sa.Column("policies_earning", sa.Integer, nullable=True),
        sa.Column("liability_amount", sa.Numeric(14, 2), nullable=True),
        sa.UniqueConstraint(
            "state_fips", "commodity", "crop_year", name="uq_rma_insured"
        ),
    )

    # FSA Conservation Reserve Program enrollment & expirations
    op.create_table(
        "crp_enrollment",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("state_fips", sa.String(2), nullable=False),
        sa.Column("year", sa.SmallInteger, nullable=False),
        sa.Column("enrolled_acres", sa.Numeric(12, 1), nullable=True),
        sa.Column("expiring_acres", sa.Numeric(12, 1), nullable=True),
        sa.Column("new_enrollment_acres", sa.Numeric(12, 1), nullable=True),
        sa.UniqueConstraint("state_fips", "year", name="uq_crp_enrollment"),
    )

    # FAS weekly export sales commitments
    op.create_table(
        "export_commitments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("commodity", sa.String(10), nullable=False),
        sa.Column("marketing_year", sa.String(20), nullable=False),
        sa.Column("as_of_date", sa.Date, nullable=False),
        sa.Column("outstanding_sales_mt", sa.Numeric(12, 1), nullable=True),
        sa.Column("accumulated_exports_mt", sa.Numeric(12, 1), nullable=True),
        sa.Column("net_sales_mt", sa.Numeric(12, 1), nullable=True),
        sa.UniqueConstraint(
            "commodity", "marketing_year", "as_of_date",
            name="uq_export_commits",
        ),
    )


def downgrade():
    op.drop_table("export_commitments")
    op.drop_table("crp_enrollment")
    op.drop_table("rma_insured_acres")
    op.drop_table("drought_index")
