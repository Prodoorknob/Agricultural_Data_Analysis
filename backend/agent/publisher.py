"""Publisher (§9 of analyst-agent-tech-spec.md).

Stages and (optionally) publishes the week's issue:
  1. Render chart specs to PNGs via matplotlib (project palette)
  2. Upload markdown + chart PNGs to S3 newsletters/draft/<slug>/
  3. Persist agent_runs row with cost, dossier_hash, slug, status
  4. Persist agent_picks (1 per story) for dedup memory
  5. Persist agent_mood
  6. Generate one-shot magic-link token, ping Slack
  7. Auto-promote if the trust-streak (§9.1) is met

`promote(run_id)` is the idempotent function called both on auto-publish
and from the manual Approve button.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
from sqlalchemy import text

from backend.agent.editor import EditorPlan
from backend.agent.factcheck import CheckResult
from backend.agent.llm import CallStats
from backend.agent.mood import Mood, persist_mood
from backend.agent.notify import notify_draft_ready, notify_published
from backend.agent.researcher import FullDossier
from backend.agent.writer import WrittenDraft
from backend.config import get_settings
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slug + path helpers.
# ---------------------------------------------------------------------------


def issue_slug(as_of: date) -> str:
    """fieldpulse-2026-w19 — week-of-year slug."""
    iso_year, iso_week, _ = as_of.isocalendar()
    return f"fieldpulse-{iso_year}-w{iso_week:02d}"


def draft_s3_prefix(slug: str) -> str:
    settings = get_settings()
    return f"{settings.NEWSLETTER_S3_PREFIX}draft/{slug}/"


def published_s3_prefix(as_of: date, slug: str) -> str:
    settings = get_settings()
    return f"{settings.NEWSLETTER_S3_PREFIX}{as_of.year:04d}/{as_of.month:02d}/{slug}/"


# ---------------------------------------------------------------------------
# Stage: write to S3 + DB (status='draft' or 'published' depending on auto).
# ---------------------------------------------------------------------------


@dataclass
class StageResult:
    run_id: int
    slug: str
    draft_url_path: str       # /insights/draft/<slug>
    public_url_path: str      # /insights/<slug>
    auto_published: bool
    one_shot_token: str | None  # only set when auto_published is False
    s3_prefix: str            # final S3 prefix (draft or published)


def stage_issue(
    *,
    as_of_date: date,
    plan: EditorPlan,
    mood: Mood,
    dossier: FullDossier,
    draft: WrittenDraft,
    fact_check: CheckResult,
    stats: CallStats,
    duration_sec: int,
) -> StageResult:
    """Top-level entrypoint after fact-check passes.

    Decides auto-publish based on §9.1 trust streak, writes to S3, persists
    DB rows, generates magic-link token, fires Slack ping.
    """
    slug = issue_slug(as_of_date)
    auto = should_auto_publish()

    # Render charts first so the markdown's {{chart_id}} placeholders can
    # resolve to actual files in S3.
    chart_pngs = _render_charts(draft.chart_specs)

    # Insert agent_runs first so we have a run_id.
    run_id = _insert_agent_run(
        run_date=as_of_date,
        slug=slug,
        status="draft",  # always "draft" until promote() flips it
        stats=stats,
        dossier=dossier,
        n_signals_scanned=len(plan.all_picks()) * 0,  # placeholder; runner overwrites
        duration_sec=duration_sec,
    )

    # Write related rows.
    _insert_agent_picks(run_id, plan)
    persist_mood(run_id, mood)

    # Upload markdown + charts to draft/ first.
    draft_prefix = draft_s3_prefix(slug)
    md_with_chart_urls = _resolve_chart_urls(draft.markdown, draft_prefix, chart_pngs.keys())
    _upload_markdown(draft_prefix + f"{slug}.md", md_with_chart_urls)
    for chart_id, png_bytes in chart_pngs.items():
        _upload_bytes(draft_prefix + f"{chart_id}.png", png_bytes, "image/png")

    one_shot_token: str | None = None
    final_prefix = draft_prefix
    if auto:
        # Auto path: copy draft -> published, update DB row.
        final_prefix = promote(run_id)
    else:
        one_shot_token = _generate_draft_token(run_id, slug)

    settings = get_settings()
    public_url_path = f"/insights/{slug}"
    draft_url_path = f"/insights/draft/{slug}"

    # Slack ping.
    headline = plan.lead.signal.headline
    if auto:
        notify_published(run_id=run_id, slug=slug, headline=headline)
    else:
        notify_draft_ready(
            run_id=run_id,
            slug=slug,
            headline=headline,
            cost_usd=stats.cost_usd,
            n_tool_calls=stats.n_tool_calls,
            one_shot_token=one_shot_token or "",
        )

    return StageResult(
        run_id=run_id,
        slug=slug,
        draft_url_path=draft_url_path,
        public_url_path=public_url_path,
        auto_published=auto,
        one_shot_token=one_shot_token,
        s3_prefix=final_prefix,
    )


# ---------------------------------------------------------------------------
# Promote: copy draft -> published, flip DB status.
# ---------------------------------------------------------------------------


def promote(run_id: int) -> str:
    """Idempotently promote a run from draft to published.

    Copies S3 objects from newsletters/draft/<slug>/ to
    newsletters/YYYY/MM/<slug>/, updates agent_runs.status to 'published',
    sets approved_at and newsletter_path.

    Returns the final S3 prefix.
    """
    settings = get_settings()
    s3 = boto3.client("s3", region_name=settings.AWS_REGION)

    with get_sync_session() as s:
        run = s.execute(
            text("SELECT id, slug, run_date, status FROM agent_runs WHERE id = :id"),
            {"id": run_id},
        ).first()
        if run is None:
            raise ValueError(f"promote: no agent_runs row for id={run_id}")
        if run.status == "published":
            logger.info("promote: run %d already published; idempotent no-op", run_id)
            return published_s3_prefix(run.run_date, run.slug)
        slug = run.slug
        run_date = run.run_date

    src_prefix = draft_s3_prefix(slug)
    dst_prefix = published_s3_prefix(run_date, slug)

    # List + copy each draft object.
    paginator = s3.get_paginator("list_objects_v2")
    copied = 0
    for page in paginator.paginate(Bucket=settings.S3_BUCKET, Prefix=src_prefix):
        for obj in page.get("Contents", []) or []:
            src_key = obj["Key"]
            dst_key = src_key.replace(src_prefix, dst_prefix, 1)
            s3.copy_object(
                Bucket=settings.S3_BUCKET,
                Key=dst_key,
                CopySource={"Bucket": settings.S3_BUCKET, "Key": src_key},
            )
            copied += 1
    logger.info("promote: copied %d objects %s -> %s", copied, src_prefix, dst_prefix)

    with get_sync_session() as s:
        s.execute(
            text(
                """
                UPDATE agent_runs
                SET status = 'published',
                    approved_at = NOW(),
                    approved_by = COALESCE(approved_by, 'auto'),
                    newsletter_path = :path
                WHERE id = :id
                """
            ),
            {"id": run_id, "path": dst_prefix},
        )
        s.commit()

    # Best-effort revalidate Next.js ISR (the route is on the frontend).
    _revalidate_next("/insights")
    _revalidate_next(f"/insights/{slug}")
    return dst_prefix


def _revalidate_next(path: str) -> None:
    """Hit Next.js's revalidation endpoint with the project's secret.

    Skips silently if VERCEL_REVALIDATE_TOKEN or PUBLIC_BASE_URL is missing.
    """
    settings = get_settings()
    token = (settings.FIELDPULSE_DRAFT_SECRET or "")[:24]  # cheap shared secret
    base = (settings.PUBLIC_BASE_URL or "").rstrip("/")
    if not base or not token:
        return
    try:
        import urllib.request

        url = f"{base}/api/revalidate?path={path}&secret={token}"
        req = urllib.request.Request(url, method="POST")
        urllib.request.urlopen(req, timeout=8).read()  # noqa: S310
    except Exception as exc:  # noqa: BLE001
        logger.debug("revalidate failed for %s: %s", path, exc)


# ---------------------------------------------------------------------------
# Trust streak (§9.1).
# ---------------------------------------------------------------------------


def should_auto_publish() -> bool:
    """Auto-publish when force_manual=false AND last N runs are 'published'.

    N = settings.AGENT_TRUST_STREAK_REQUIRED (default 6).
    """
    settings = get_settings()
    n = settings.AGENT_TRUST_STREAK_REQUIRED
    with get_sync_session() as s:
        row = s.execute(
            text(
                "SELECT force_manual, auto_publish_enabled FROM agent_settings WHERE id = 1"
            )
        ).first()
        if row and row.force_manual:
            return False
        if row and row.auto_publish_enabled:
            return True
        # No explicit override; check streak.
        rows = s.execute(
            text(
                "SELECT status FROM agent_runs ORDER BY run_date DESC LIMIT :n"
            ),
            {"n": n},
        ).all()
    if len(rows) < n:
        return False
    return all(r.status == "published" for r in rows)


# ---------------------------------------------------------------------------
# DB writes.
# ---------------------------------------------------------------------------


def _insert_agent_run(
    *,
    run_date: date,
    slug: str,
    status: str,
    stats: CallStats,
    dossier: FullDossier,
    n_signals_scanned: int,
    duration_sec: int,
) -> int:
    payload = {
        "run_date": run_date,
        "status": status,
        "newsletter_path": draft_s3_prefix(slug),
        "slug": slug,
        "n_signals_scanned": n_signals_scanned,
        "n_tool_calls": stats.n_tool_calls,
        "input_tokens": stats.input_tokens,
        "output_tokens": stats.output_tokens,
        "cost_usd": round(stats.cost_usd, 4),
        "duration_sec": duration_sec,
        "dossier_hash": _dossier_hash(dossier),
    }
    sql = text(
        """
        INSERT INTO agent_runs (
            run_date, status, newsletter_path, slug,
            n_signals_scanned, n_tool_calls,
            input_tokens, output_tokens, cost_usd, duration_sec, dossier_hash
        ) VALUES (
            :run_date, :status, :newsletter_path, :slug,
            :n_signals_scanned, :n_tool_calls,
            :input_tokens, :output_tokens, :cost_usd, :duration_sec, :dossier_hash
        )
        ON CONFLICT (run_date) DO UPDATE SET
            status = EXCLUDED.status,
            newsletter_path = EXCLUDED.newsletter_path,
            slug = EXCLUDED.slug,
            n_signals_scanned = EXCLUDED.n_signals_scanned,
            n_tool_calls = EXCLUDED.n_tool_calls,
            input_tokens = EXCLUDED.input_tokens,
            output_tokens = EXCLUDED.output_tokens,
            cost_usd = EXCLUDED.cost_usd,
            duration_sec = EXCLUDED.duration_sec,
            dossier_hash = EXCLUDED.dossier_hash
        RETURNING id
        """
    )
    with get_sync_session() as s:
        row = s.execute(sql, payload).first()
        s.commit()
    return int(row.id)


def _insert_agent_picks(run_id: int, plan: EditorPlan) -> None:
    rows = []
    for pick in plan.all_picks():
        rows.append(
            {
                "run_id": run_id,
                "role": pick.role,
                "signal_id": pick.signal.id,
                "signal_domain": pick.signal.domain,
                "signal_scope": pick.signal.scope,
                "score": round(pick.signal.score, 2),
                "mood_boost": round(pick.signal.mood_boost, 2),
                "headline": pick.signal.headline,
            }
        )
    sql = text(
        """
        INSERT INTO agent_picks (
            run_id, role, signal_id, signal_domain, signal_scope,
            score, mood_boost, headline
        ) VALUES (
            :run_id, :role, :signal_id, :signal_domain, :signal_scope,
            :score, :mood_boost, :headline
        )
        """
    )
    with get_sync_session() as s:
        # Wipe any prior picks for this run (idempotent re-runs).
        s.execute(text("DELETE FROM agent_picks WHERE run_id = :id"), {"id": run_id})
        s.execute(sql, rows)
        s.commit()


def _generate_draft_token(run_id: int, slug: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    with get_sync_session() as s:
        s.execute(
            text(
                """
                INSERT INTO agent_draft_tokens (token, run_id, slug, expires_at)
                VALUES (:token, :run_id, :slug, :expires)
                """
            ),
            {"token": token, "run_id": run_id, "slug": slug, "expires": expires},
        )
        s.commit()
    return token


def _dossier_hash(dossier: FullDossier) -> str:
    summary = []
    for story in dossier.all():
        summary.append(story.signal_id)
        summary.extend(story.claims)
        summary.extend(story.peer_context)
        summary.append(story.what_to_watch)
    blob = "\n".join(summary).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# S3 helpers.
# ---------------------------------------------------------------------------


def _upload_bytes(key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    s3 = boto3.client("s3", region_name=settings.AWS_REGION)
    s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=data, ContentType=content_type)


def _upload_markdown(key: str, markdown: str) -> None:
    _upload_bytes(key, markdown.encode("utf-8"), "text/markdown; charset=utf-8")


# ---------------------------------------------------------------------------
# Chart placeholder resolution.
# ---------------------------------------------------------------------------


_PLACEHOLDER_RE = re.compile(r"\{\{(chart_\w+)\}\}")


def _resolve_chart_urls(markdown: str, prefix: str, available_ids: Any) -> str:
    """Replace `{{chart_id}}` with `![](/insights/charts/<slug>/chart_id.png)`.

    The frontend serves /insights/charts/<slug>/<id>.png as a static proxy
    that fetches from S3 (newsletters/{draft|YYYY/MM}/<slug>/<id>.png).
    """
    available = set(available_ids)

    def _sub(m: re.Match) -> str:
        cid = m.group(1)
        if cid not in available:
            return m.group(0)  # leave placeholder; writer might just not have a chart
        # The frontend route is the same for draft + published; the proxy
        # resolves which S3 path to pull from.
        return f"![]({_chart_public_path(prefix, cid)})"

    return _PLACEHOLDER_RE.sub(_sub, markdown)


def _chart_public_path(s3_prefix: str, chart_id: str) -> str:
    """Map an S3 prefix back to a frontend-relative chart URL.

    Examples:
      newsletters/draft/<slug>/        -> /insights/charts/draft/<slug>/<id>.png
      newsletters/2026/05/<slug>/      -> /insights/charts/<slug>/<id>.png
    """
    settings = get_settings()
    suffix = s3_prefix.removeprefix(settings.NEWSLETTER_S3_PREFIX)
    parts = [p for p in suffix.split("/") if p]
    if parts and parts[0] == "draft":
        slug = parts[1] if len(parts) > 1 else "unknown"
        return f"/insights/charts/draft/{slug}/{chart_id}.png"
    # newsletters/2026/05/<slug>/
    slug = parts[2] if len(parts) >= 3 else "unknown"
    return f"/insights/charts/{slug}/{chart_id}.png"


# ---------------------------------------------------------------------------
# Chart rendering (matplotlib).
# ---------------------------------------------------------------------------

# Project palette (kept compact; mirror web_app/src/utils/design.ts).
_PALETTE = {
    "primary": "#3F8F55",
    "accent": "#C26A2A",
    "neutral": "#6B7280",
    "ink": "#222926",
    "soil": "#8B7355",
    "sky": "#5B8DEF",
}
_BAR_COLORS = ["#3F8F55", "#C26A2A", "#5B8DEF", "#8B7355", "#6B7280"]


def _render_charts(specs: list[dict[str, Any]]) -> dict[str, bytes]:
    """Render each chart spec to a PNG byte string."""
    if not specs:
        return {}
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401  (used in helpers)
    except ImportError:
        logger.warning("matplotlib missing; skipping chart render")
        return {}

    out: dict[str, bytes] = {}
    for spec in specs:
        cid = spec.get("id")
        kind = spec.get("kind", "")
        if not cid:
            continue
        try:
            png = _render_one(spec)
        except Exception as exc:  # noqa: BLE001
            logger.warning("chart %s (%s) render failed: %s", cid, kind, exc)
            continue
        out[cid] = png
    return out


def _render_one(spec: dict[str, Any]) -> bytes:
    import matplotlib.pyplot as plt

    kind = spec.get("kind", "line")
    title = str(spec.get("title", ""))
    data = spec.get("data") or []
    x_label = spec.get("x", "")
    y_label = spec.get("y", "")

    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)

    if kind in ("line", "bar"):
        xs = [row.get("x") for row in data]
        ys = [row.get("y") for row in data]
        if kind == "line":
            ax.plot(xs, ys, color=_PALETTE["primary"], linewidth=2.5)
        else:
            ax.bar(
                range(len(xs)), ys,
                color=[_BAR_COLORS[i % len(_BAR_COLORS)] for i in range(len(xs))],
            )
            ax.set_xticks(range(len(xs)))
            ax.set_xticklabels([str(x) for x in xs], rotation=30, ha="right")
    else:
        # Choropleth + complex types: punt to a "title slide" placeholder.
        ax.text(
            0.5, 0.5,
            f"{kind} chart\n(rendered separately)",
            ha="center", va="center",
            fontsize=11, color=_PALETTE["neutral"],
            transform=ax.transAxes,
        )
        ax.set_axis_off()

    ax.set_title(title, color=_PALETTE["ink"], fontsize=12)
    if x_label:
        ax.set_xlabel(x_label, color=_PALETTE["neutral"])
    if y_label:
        ax.set_ylabel(y_label, color=_PALETTE["neutral"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
