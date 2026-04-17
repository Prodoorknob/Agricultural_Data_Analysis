"""Widen ers_production_costs.yield_units to accommodate ERS phrases.

ERS publishes yield-unit strings like "bushels per planted acre" (24 chars)
and "pounds per planted acre" (23 chars). The 20-char limit in 008 rejected
every row with those units. Widening to 40 covers every phrase the ERS
tidy data uses and leaves headroom for future additions.

Revision ID: 009
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "ers_production_costs", "yield_units",
        existing_type=sa.String(20),
        type_=sa.String(40),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "ers_production_costs", "yield_units",
        existing_type=sa.String(40),
        type_=sa.String(20),
        existing_nullable=True,
    )
