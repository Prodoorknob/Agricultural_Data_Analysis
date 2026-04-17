"""Add per-acre cost columns to ers_production_costs + widen commodity.

The existing schema stored costs per bushel only — fine for corn/soy/wheat
price forecasting, but the frontend Crops-tab profit chart needs per-acre
costs to compute profit = (price * yield - cost_per_acre) across arbitrary
commodities (rice in lb/ac, cotton in lb/ac, etc.). Storing the per-acre
figure that ERS publishes directly avoids unit-conversion error and lets
each downstream consumer divide by its own yield unit.

Also widens commodity from VARCHAR(10) to VARCHAR(20) so ERS commodity
names longer than 10 chars (none today, but `wheat_winter`/`wheat_spring`
are the precedent) can land without another migration.

Revision ID: 008
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ers_production_costs") as b:
        b.alter_column(
            "commodity",
            existing_type=sa.String(10),
            type_=sa.String(20),
            existing_nullable=False,
        )
        b.add_column(sa.Column("variable_cost_per_acre", sa.Numeric(12, 2), nullable=True))
        b.add_column(sa.Column("total_cost_per_acre", sa.Numeric(12, 2), nullable=True))
        b.add_column(sa.Column("yield_units", sa.String(20), nullable=True))
        b.add_column(sa.Column("yield_value", sa.Numeric(12, 2), nullable=True))


def downgrade():
    with op.batch_alter_table("ers_production_costs") as b:
        b.drop_column("yield_value")
        b.drop_column("yield_units")
        b.drop_column("total_cost_per_acre")
        b.drop_column("variable_cost_per_acre")
        b.alter_column(
            "commodity",
            existing_type=sa.String(20),
            type_=sa.String(10),
            existing_nullable=False,
        )
