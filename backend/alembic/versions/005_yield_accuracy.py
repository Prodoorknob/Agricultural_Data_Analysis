"""Add yield_accuracy table for walk-forward test prediction track record.

Stores per-(forecast_year, fips, crop, week) test predictions from
train_yield.py walk-forward evaluation. Powers the Forecasts tab accuracy
panel (§5.3.D in frontend-spec-v1.md).

Revision ID: 005
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "yield_accuracy",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("forecast_year", sa.SmallInteger, nullable=False),
        sa.Column("fips", sa.String(5), nullable=False),
        sa.Column("crop", sa.String(10), nullable=False),
        sa.Column("week", sa.SmallInteger, nullable=False),
        sa.Column("model_p50", sa.Numeric(6, 1), nullable=False),
        sa.Column("model_p10", sa.Numeric(6, 1), nullable=True),
        sa.Column("model_p90", sa.Numeric(6, 1), nullable=True),
        sa.Column("actual_yield", sa.Numeric(6, 1), nullable=True),
        sa.Column("county_5yr_mean", sa.Numeric(6, 1), nullable=True),
        sa.Column("abs_error", sa.Numeric(6, 2), nullable=True),
        sa.Column("pct_error", sa.Numeric(6, 2), nullable=True),
        sa.Column("in_interval", sa.Boolean, nullable=True),
        sa.Column("split", sa.String(10), nullable=True),  # 'val' | 'test'
        sa.Column("model_ver", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "forecast_year", "fips", "crop", "week", "model_ver",
            name="uq_yield_accuracy",
        ),
    )
    op.create_index("ix_yield_accuracy_crop_year", "yield_accuracy", ["crop", "forecast_year"])
    op.create_index("ix_yield_accuracy_crop_week", "yield_accuracy", ["crop", "week"])


def downgrade():
    op.drop_index("ix_yield_accuracy_crop_week", table_name="yield_accuracy")
    op.drop_index("ix_yield_accuracy_crop_year", table_name="yield_accuracy")
    op.drop_table("yield_accuracy")
