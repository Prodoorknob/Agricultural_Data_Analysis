"""Create price forecasting module tables.

Revision ID: 001
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "futures_daily",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("commodity", sa.String(10), nullable=False),
        sa.Column("contract_month", sa.String(7), nullable=False),
        sa.Column("settlement", sa.Numeric(8, 4), nullable=False),
        sa.Column("open_interest", sa.Integer, nullable=True),
        sa.Column("volume", sa.Integer, nullable=True),
        sa.Column("source", sa.String(30), server_default="nasdaq_dl"),
        sa.Column("ingest_ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("trade_date", "commodity", "contract_month", name="uq_futures_daily"),
    )

    op.create_table(
        "wasde_releases",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("release_date", sa.Date, nullable=False),
        sa.Column("commodity", sa.String(10), nullable=False),
        sa.Column("marketing_year", sa.String(9), nullable=False),
        sa.Column("us_production", sa.Numeric(10, 2), nullable=True),
        sa.Column("us_exports", sa.Numeric(10, 2), nullable=True),
        sa.Column("ending_stocks", sa.Numeric(10, 2), nullable=True),
        sa.Column("stocks_to_use", sa.Numeric(6, 4), nullable=True),
        sa.Column("world_production", sa.Numeric(10, 2), nullable=True),
        sa.Column("source", sa.String(30), server_default="usda_wasde"),
        sa.UniqueConstraint("release_date", "commodity", "marketing_year", name="uq_wasde_releases"),
    )

    op.create_table(
        "price_forecasts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_date", sa.Date, nullable=False),
        sa.Column("commodity", sa.String(10), nullable=False),
        sa.Column("horizon_month", sa.String(7), nullable=False),
        sa.Column("p10", sa.Numeric(8, 4), nullable=False),
        sa.Column("p50", sa.Numeric(8, 4), nullable=False),
        sa.Column("p90", sa.Numeric(8, 4), nullable=False),
        sa.Column("prob_above_threshold", sa.Numeric(5, 4), nullable=True),
        sa.Column("threshold_price", sa.Numeric(8, 4), nullable=True),
        sa.Column("key_driver", sa.String(100), nullable=True),
        sa.Column("divergence_flag", sa.Boolean, server_default=sa.text("false")),
        sa.Column("model_ver", sa.String(20), nullable=False),
        sa.Column("regime_anomaly", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("run_date", "commodity", "horizon_month", "model_ver", name="uq_price_forecasts"),
    )

    op.create_table(
        "ers_production_costs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("commodity", sa.String(10), nullable=False),
        sa.Column("variable_cost_per_bu", sa.Numeric(8, 4), nullable=True),
        sa.Column("total_cost_per_bu", sa.Numeric(8, 4), nullable=True),
        sa.UniqueConstraint("year", "commodity", name="uq_ers_costs"),
    )

    op.create_table(
        "dxy_daily",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("trade_date", sa.Date, nullable=False, unique=True),
        sa.Column("dxy", sa.Numeric(8, 4), nullable=False),
        sa.Column("source", sa.String(30), server_default="fred"),
        sa.Column("ingest_ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("dxy_daily")
    op.drop_table("ers_production_costs")
    op.drop_table("price_forecasts")
    op.drop_table("wasde_releases")
    op.drop_table("futures_daily")
