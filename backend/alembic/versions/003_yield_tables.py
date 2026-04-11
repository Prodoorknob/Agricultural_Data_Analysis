"""Create crop yield forecasting module tables.

Revision ID: 003
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    # Static soil features (one-time SSURGO load)
    op.create_table(
        "soil_features",
        sa.Column("fips", sa.String(5), primary_key=True),
        sa.Column("awc_cm", sa.Numeric(6, 4), nullable=True),
        sa.Column("drain_class", sa.SmallInteger, nullable=True),
    )

    # Weekly feature store (computed from weather + crop condition + drought + soil)
    op.create_table(
        "feature_weekly",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fips", sa.String(5), nullable=False),
        sa.Column("crop", sa.String(10), nullable=False),
        sa.Column("crop_year", sa.SmallInteger, nullable=False),
        sa.Column("week", sa.SmallInteger, nullable=False),
        sa.Column("gdd_ytd", sa.Numeric(8, 1), nullable=True),
        sa.Column("cci_cumul", sa.Numeric(6, 1), nullable=True),
        sa.Column("precip_deficit", sa.Numeric(8, 1), nullable=True),
        sa.Column("vpd_stress_days", sa.SmallInteger, nullable=True),
        sa.Column("drought_d3d4_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("soil_awc", sa.Numeric(6, 4), nullable=True),
        sa.Column("soil_drain", sa.SmallInteger, nullable=True),
        sa.Column(
            "ingest_ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "fips", "crop", "crop_year", "week", name="uq_feature_weekly"
        ),
    )

    # Yield forecast output (immutable per model version)
    op.create_table(
        "yield_forecasts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("fips", sa.String(5), nullable=False),
        sa.Column("crop", sa.String(10), nullable=False),
        sa.Column("crop_year", sa.SmallInteger, nullable=False),
        sa.Column("week", sa.SmallInteger, nullable=False),
        sa.Column("p10", sa.Numeric(6, 1), nullable=False),
        sa.Column("p50", sa.Numeric(6, 1), nullable=False),
        sa.Column("p90", sa.Numeric(6, 1), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False),
        sa.Column("model_ver", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "fips", "crop", "crop_year", "week", "model_ver",
            name="uq_yield_forecasts",
        ),
    )


def downgrade():
    op.drop_table("yield_forecasts")
    op.drop_table("feature_weekly")
    op.drop_table("soil_features")
