"""Cron entry point for FieldPulse Weekly.

Pipeline (§3 of analyst-agent-tech-spec.md):
    1. SignalBoard          (deterministic)
    2. MoodSynthesizer      (LLM, no tools)
    3. Editor               (LLM, no tools, JSON only)
    4. Researcher           (LLM with tools, capped at 30 calls)
    5. Writer               (LLM, dossier only)
    6. FactChecker          (deterministic + LLM critique)
    7. Publisher            (deterministic — S3, DB, Slack)

Failure mode: each step is wrapped in try/except. On exception we record
`agent_runs.failed_at_step`, emit a Slack + email failure notification,
and exit non-zero. No half-baked newsletters get published.

Usage:
    python -m backend.agent.runner [--as-of YYYY-MM-DD] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from sqlalchemy import text

from backend.agent.editor import EditorPlan, pick_stories
from backend.agent.factcheck import CheckResult, fact_check
from backend.agent.llm import CallStats
from backend.agent.mood import Mood, synthesize_mood
from backend.agent.notify import notify_failure
from backend.agent.publisher import StageResult, stage_issue
from backend.agent.researcher import FullDossier, research
from backend.agent.signal_board import build_candidates
from backend.agent.writer import WrittenDraft, write_issue
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


@dataclass
class StepCtx:
    """Mutable context passed between steps."""

    as_of: date
    stats: CallStats = field(default_factory=CallStats)
    candidates: list = field(default_factory=list)
    mood: Mood | None = None
    plan: EditorPlan | None = None
    dossier: FullDossier | None = None
    draft: WrittenDraft | None = None
    fact_result: CheckResult | None = None
    stage: StageResult | None = None
    started_at: float = field(default_factory=time.time)


def run(as_of_date: date | None = None, *, dry_run: bool = False) -> int:
    """Run a single weekly pass. Returns exit code (0 = success)."""
    _setup_logging()
    as_of = as_of_date or _last_sunday()
    ctx = StepCtx(as_of=as_of)

    logger.info(
        "FieldPulse run starting (as_of=%s, dry_run=%s)", as_of, dry_run
    )

    if not dry_run and _run_already_completed(as_of):
        logger.info(
            "agent_runs row for %s already exists with terminal status; "
            "exiting idempotently",
            as_of,
        )
        return 0

    steps: list[tuple[str, Callable[[StepCtx], None]]] = [
        ("signal_board", _step_signal_board),
        ("mood_synthesizer", _step_mood),
        ("editor", _step_editor),
        ("researcher", _step_researcher),
        ("writer", _step_writer),
        ("fact_checker", lambda c: _step_fact_check(c, dry_run=dry_run)),
        ("publisher", lambda c: _step_publish(c, dry_run=dry_run)),
    ]

    for step_name, fn in steps:
        try:
            t0 = time.time()
            fn(ctx)
            logger.info("step %s ok (%.1fs, %s)", step_name, time.time() - t0, ctx.stats)
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc(limit=4)
            logger.error("step %s failed: %s\n%s", step_name, exc, tb)
            _record_failure(as_of, step_name, exc, ctx)
            return 2

    logger.info(
        "FieldPulse run complete (slug=%s, auto=%s, cost=$%.2f, %.0fs)",
        ctx.stage.slug if ctx.stage else "?",
        ctx.stage.auto_published if ctx.stage else False,
        ctx.stats.cost_usd,
        time.time() - ctx.started_at,
    )
    return 0


# ---------------------------------------------------------------------------
# Step wrappers — each populates one or more fields on StepCtx.
# ---------------------------------------------------------------------------


def _step_signal_board(ctx: StepCtx) -> None:
    cands = build_candidates(ctx.as_of, top_n=20)
    if not cands:
        raise RuntimeError("signal_board produced 0 candidates")
    ctx.candidates = cands


def _step_mood(ctx: StepCtx) -> None:
    ctx.mood = synthesize_mood(ctx.as_of, stats=ctx.stats)
    # Re-rank candidates with mood biases applied.
    from backend.agent.signal_board import apply_mood_boost, rank

    apply_mood_boost(ctx.candidates, ctx.mood.biases)
    ctx.candidates = rank(ctx.candidates, top_n=20)


def _step_editor(ctx: StepCtx) -> None:
    if ctx.mood is None:
        raise RuntimeError("editor: mood missing")
    ctx.plan = pick_stories(
        ctx.candidates, mood=ctx.mood, as_of_date=ctx.as_of, stats=ctx.stats
    )


def _step_researcher(ctx: StepCtx) -> None:
    if ctx.plan is None or ctx.mood is None:
        raise RuntimeError("researcher: plan or mood missing")
    ctx.dossier = research(
        ctx.plan, mood=ctx.mood, as_of_date=ctx.as_of, stats=ctx.stats
    )


def _step_writer(ctx: StepCtx) -> None:
    if ctx.dossier is None or ctx.mood is None:
        raise RuntimeError("writer: dossier or mood missing")
    ctx.draft = write_issue(
        ctx.dossier, mood=ctx.mood, as_of_date=ctx.as_of, stats=ctx.stats
    )
    _save_dry_run_artifact(ctx, "last_draft.md", ctx.draft.markdown)


def _step_fact_check(ctx: StepCtx, *, dry_run: bool = False) -> None:
    if ctx.draft is None or ctx.dossier is None:
        raise RuntimeError("fact_check: draft or dossier missing")
    ctx.fact_result = fact_check(
        ctx.draft.markdown, dossier=ctx.dossier, stats=ctx.stats
    )
    # Always persist the fact-check report on dry-runs so the operator can
    # iterate on writer prompt + dossier structure.
    if dry_run:
        import json as _json
        payload = {
            "passed": ctx.fact_result.passed,
            "issues": [
                {
                    "severity": i.severity, "source": i.source,
                    "detail": i.detail, "quote": i.quote,
                }
                for i in ctx.fact_result.all_issues
            ],
        }
        _save_dry_run_artifact(ctx, "last_factcheck.json", _json.dumps(payload, indent=2))
    if not ctx.fact_result.passed:
        majors = ctx.fact_result.major_issues
        msg = (
            f"fact_check failed with {len(majors)} major issue(s): "
            + "; ".join(m.detail for m in majors[:3])
        )
        if dry_run:
            # On dry-run, log + continue — the draft is the artifact, the
            # fact-check report is the diagnostic.
            logger.warning("DRY RUN: %s (continuing to publisher noop)", msg)
            return
        raise RuntimeError(msg)


def _save_dry_run_artifact(ctx: StepCtx, name: str, content: str) -> None:
    """Best-effort write of a dry-run intermediate to backend/agent/data/."""
    try:
        from pathlib import Path

        out = Path(__file__).parent / "data" / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        logger.info("wrote dry-run artifact: %s", out)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not save %s: %s", name, exc)


def _step_publish(ctx: StepCtx, *, dry_run: bool) -> None:
    if (
        ctx.plan is None
        or ctx.mood is None
        or ctx.dossier is None
        or ctx.draft is None
        or ctx.fact_result is None
    ):
        raise RuntimeError("publish: prior step output missing")
    if dry_run:
        logger.info("publish: dry_run=True, skipping S3 + DB writes")
        return
    duration = int(time.time() - ctx.started_at)
    ctx.stage = stage_issue(
        as_of_date=ctx.as_of,
        plan=ctx.plan,
        mood=ctx.mood,
        dossier=ctx.dossier,
        draft=ctx.draft,
        fact_check=ctx.fact_result,
        stats=ctx.stats,
        duration_sec=duration,
    )


# ---------------------------------------------------------------------------
# Failure handling.
# ---------------------------------------------------------------------------


def _record_failure(
    as_of: date, failed_at_step: str, exc: BaseException, ctx: StepCtx
) -> None:
    """Best-effort: write agent_runs failure row, fire Slack + email."""
    run_id: int | None = None
    try:
        with get_sync_session() as s:
            row = s.execute(
                text(
                    """
                    INSERT INTO agent_runs (
                        run_date, status, failed_at_step,
                        n_tool_calls, input_tokens, output_tokens, cost_usd
                    ) VALUES (
                        :run_date, 'failed', :step,
                        :n_tool, :in_tok, :out_tok, :cost
                    )
                    ON CONFLICT (run_date) DO UPDATE SET
                        status = 'failed',
                        failed_at_step = EXCLUDED.failed_at_step,
                        n_tool_calls = EXCLUDED.n_tool_calls,
                        input_tokens = EXCLUDED.input_tokens,
                        output_tokens = EXCLUDED.output_tokens,
                        cost_usd = EXCLUDED.cost_usd
                    RETURNING id
                    """
                ),
                {
                    "run_date": as_of,
                    "step": failed_at_step,
                    "n_tool": ctx.stats.n_tool_calls,
                    "in_tok": ctx.stats.input_tokens,
                    "out_tok": ctx.stats.output_tokens,
                    "cost": round(ctx.stats.cost_usd, 4),
                },
            ).first()
            s.commit()
            run_id = int(row.id) if row else None
    except Exception as db_exc:  # noqa: BLE001
        logger.exception("failed to record agent_runs failure row: %s", db_exc)

    issues = [f"{type(exc).__name__}: {exc}"]
    if ctx.fact_result is not None:
        for i in ctx.fact_result.major_issues[:5]:
            issues.append(f"[{i.source}/{i.severity}] {i.detail}")

    try:
        notify_failure(
            run_id=run_id,
            failed_at_step=failed_at_step,
            issues=issues,
            draft_url=None,
        )
    except Exception as notify_exc:  # noqa: BLE001
        logger.exception("failed to send failure notification: %s", notify_exc)


# ---------------------------------------------------------------------------
# Idempotency check.
# ---------------------------------------------------------------------------


def _run_already_completed(as_of: date) -> bool:
    sql = text(
        "SELECT status FROM agent_runs WHERE run_date = :d ORDER BY id DESC LIMIT 1"
    )
    with get_sync_session() as s:
        row = s.execute(sql, {"d": as_of}).first()
    if row is None:
        return False
    return row.status in {"draft", "published", "approved", "rejected"}


def _last_sunday() -> date:
    today = date.today()
    days_back = (today.weekday() + 1) % 7  # Mon=0 -> 1 day back to Sunday
    if days_back == 0:
        return today  # today IS Sunday
    from datetime import timedelta as _td

    return today - _td(days=days_back)


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="FieldPulse Weekly analyst-agent runner.")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Frozen point-in-time date (YYYY-MM-DD). Defaults to last Sunday.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all steps but do not write to S3, DB, or Slack.",
    )
    args = parser.parse_args()
    return run(as_of_date=args.as_of, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
