"""Create acreage prediction module tables.

Revision ID: 002
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "acreage_forecasts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("forecast_year", sa.SmallInteger, nullable=False),
        sa.Column("state_fips", sa.String(2), nullable=False),
        sa.Column("commodity", sa.String(10), nullable=False),
        sa.Column("forecast_acres", sa.Numeric(10, 1), nullable=False),
        sa.Column("p10_acres", sa.Numeric(10, 1), nullable=True),
        sa.Column("p90_acres", sa.Numeric(10, 1), nullable=True),
        sa.Column("corn_soy_ratio", sa.Numeric(6, 4), nullable=True),
        sa.Column("key_driver", sa.String(100), nullable=True),
        sa.Column("model_ver", sa.String(20), nullable=False),
        sa.Column("published_at", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "forecast_year", "state_fips", "commodity", "model_ver",
            name="uq_acreage_forecasts",
        ),
    )

    op.create_table(
        "acreage_accuracy",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("forecast_year", sa.SmallInteger, nullable=False),
        sa.Column("state_fips", sa.String(2), nullable=False),
        sa.Column("commodity", sa.String(10), nullable=False),
        sa.Column("model_forecast", sa.Numeric(10, 1), nullable=False),
        sa.Column("usda_prospective", sa.Numeric(10, 1), nullable=True),
        sa.Column("usda_june_actual", sa.Numeric(10, 1), nullable=True),
        sa.Column("model_vs_usda_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("model_vs_actual_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "forecast_year", "state_fips", "commodity",
            name="uq_acreage_accuracy",
        ),
    )

    op.create_table(
        "ers_fertilizer_prices",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("quarter", sa.String(7), nullable=False),
        sa.Column("anhydrous_ammonia_ton", sa.Numeric(8, 2), nullable=True),
        sa.Column("dap_ton", sa.Numeric(8, 2), nullable=True),
        sa.Column("potash_ton", sa.Numeric(8, 2), nullable=True),
        sa.UniqueConstraint("quarter", name="uq_fertilizer_prices"),
    )

    # Add fertilizer_cost_acre column to existing ers_production_costs table
    op.add_column(
        "ers_production_costs",
        sa.Column("fertilizer_cost_acre", sa.Numeric(8, 2), nullable=True),
    )


def downgrade():
    op.drop_column("ers_production_costs", "fertilizer_cost_acre")
    op.drop_table("ers_fertilizer_prices")
    op.drop_table("acreage_accuracy")
    op.drop_table("acreage_forecasts")
