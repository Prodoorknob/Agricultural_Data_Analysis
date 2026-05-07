"""Add agent tables for FieldPulse Weekly (Module 05).

Five tables:
  agent_runs         - one row per weekly run, status + cost + dossier hash
  agent_picks        - one row per published lead/brief; powers 8-week dedup
  agent_mood         - one row per run; weekly mood JSON for audit
  agent_settings     - single-row kill-switch table (force_manual)
  agent_draft_tokens - one-shot magic-link tokens for /insights/draft auth (§9.3)

Revision ID: 012
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    # --- agent_runs ---
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_date", sa.Date, nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        # 'pending' | 'draft' | 'approved' | 'rejected' | 'published' | 'failed'
        sa.Column("failed_at_step", sa.String(30), nullable=True),
        sa.Column("newsletter_path", sa.Text, nullable=True),
        sa.Column("slug", sa.String(80), nullable=True),
        sa.Column("n_signals_scanned", sa.Integer, nullable=True),
        sa.Column("n_tool_calls", sa.Integer, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(8, 4), nullable=True),
        sa.Column("duration_sec", sa.Integer, nullable=True),
        sa.Column("dossier_hash", sa.String(64), nullable=True),
        sa.Column("approved_by", sa.String(50), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status", "run_date"])

    # --- agent_picks ---
    op.create_table(
        "agent_picks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(10), nullable=False),  # 'lead' | 'brief'
        sa.Column("signal_id", sa.String(100), nullable=False),
        sa.Column("signal_domain", sa.String(20), nullable=False),
        sa.Column("signal_scope", sa.String(50), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("mood_boost", sa.Numeric(5, 2), nullable=True),
        sa.Column("headline", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_agent_picks_domain_scope",
        "agent_picks",
        ["signal_domain", "signal_scope", "created_at"],
    )

    # --- agent_mood ---
    op.create_table(
        "agent_mood",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mood_tags", sa.JSON, nullable=False),
        sa.Column("primary_narrative", sa.Text, nullable=True),
        sa.Column("biases", sa.JSON, nullable=False),
        sa.Column("avoid_unless_dramatic", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- agent_settings (single-row kill switch table) ---
    op.create_table(
        "agent_settings",
        sa.Column("id", sa.SmallInteger, primary_key=True),  # always 1
        sa.Column("force_manual", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("auto_publish_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("id = 1", name="ck_agent_settings_singleton"),
    )
    # Seed the single row.
    op.execute(
        "INSERT INTO agent_settings (id, force_manual, auto_publish_enabled) "
        "VALUES (1, TRUE, FALSE)"
    )

    # --- agent_draft_tokens (one-shot magic-link tokens) ---
    op.create_table(
        "agent_draft_tokens",
        sa.Column("token", sa.String(64), primary_key=True),  # url-safe random
        sa.Column(
            "run_id",
            sa.BigInteger,
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_draft_tokens_run", "agent_draft_tokens", ["run_id"])


def downgrade():
    op.drop_index("ix_agent_draft_tokens_run", table_name="agent_draft_tokens")
    op.drop_table("agent_draft_tokens")
    op.drop_table("agent_settings")
    op.drop_table("agent_mood")
    op.drop_index("ix_agent_picks_domain_scope", table_name="agent_picks")
    op.drop_table("agent_picks")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_table("agent_runs")
