"""Add story_title to agent_picks.

Powers the two-section /insights landing page (educational vs performance
story feeds). The pick row already knows the signal headline; story_title is
the WRITER's published section title, filled by the publisher at stage time
by parsing the fact-checked markdown (lead H2 + brief H3s in pick order).

Revision ID: 014
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_picks",
        sa.Column("story_title", sa.String(300), nullable=True),
    )


def downgrade():
    op.drop_column("agent_picks", "story_title")
