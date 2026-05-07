"""Mood Synthesizer (§5 of analyst-agent-tech-spec.md).

Pulls a numeric context snapshot from the DB (no PDF parsing — see §5 v0.3),
hands it to Claude Sonnet 4.6, and parses a strict JSON mood object back.

The mood drives the SignalBoard's mood_boost via biases per domain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

from backend.agent.llm import CallStats, call_json, load_prompt
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)


# Domains the LLM emits biases for. Exactly the set used by the SignalBoard.
EXPECTED_DOMAINS = {
    "yield", "price", "acreage", "weather", "drought", "wasde",
    "exports", "futures", "trend_break", "accuracy", "calendar",
}


@dataclass
class Mood:
    """Parsed + validated mood JSON, ready to feed to apply_mood_boost()."""

    mood_tags: list[str]
    primary_narrative: str
    biases: dict[str, float]
    avoid_unless_dramatic: list[str] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)


def synthesize_mood(as_of_date: date, *, stats: CallStats | None = None) -> Mood:
    """Build the context snapshot, call Claude, parse + validate."""
    snapshot = build_context_snapshot(as_of_date)
    user_msg = _format_snapshot(snapshot)
    logger.info("mood: snapshot has %d sections", len(snapshot))

    raw = call_json(
        system=load_prompt("mood_system"),
        user=user_msg,
        max_tokens=1024,
        stats=stats,
    )
    return _validate(raw)


def _validate(raw: dict[str, Any]) -> Mood:
    biases = raw.get("biases", {})
    if not isinstance(biases, dict):
        raise ValueError(f"mood.biases must be a dict, got {type(biases).__name__}")

    # Fill any missing domains with 1.0; clamp to [0.7, 1.5].
    cleaned: dict[str, float] = {}
    for d in EXPECTED_DOMAINS:
        v = biases.get(d, 1.0)
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = 1.0
        cleaned[d] = max(0.7, min(1.5, v))

    # Warn on unexpected domains.
    extra = set(biases.keys()) - EXPECTED_DOMAINS
    if extra:
        logger.warning("mood: ignoring unknown bias domains: %s", extra)

    tags = raw.get("mood_tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t).lower().strip() for t in tags if str(t).strip()]

    narrative = str(raw.get("primary_narrative", "")).strip()

    avoid = raw.get("avoid_unless_dramatic") or []
    if not isinstance(avoid, list):
        avoid = []
    avoid = [str(t).lower().strip() for t in avoid if str(t).strip() in EXPECTED_DOMAINS]

    return Mood(
        mood_tags=tags,
        primary_narrative=narrative,
        biases=cleaned,
        avoid_unless_dramatic=avoid,
        raw_json=raw,
    )


# ---------------------------------------------------------------------------
# Context snapshot — pure SQL, no LLM.
# ---------------------------------------------------------------------------


def build_context_snapshot(as_of: date) -> dict[str, Any]:
    """Pull all numeric inputs needed to write the mood prompt.

    Each section is a small dict the prompt formatter renders into prose.
    Failures in any single section log a warning but do not abort — the LLM
    can synthesize from partial inputs.
    """
    snap: dict[str, Any] = {"as_of_date": as_of.isoformat(), "season": _season(as_of)}
    try:
        snap["wasde_deltas"] = _wasde_deltas(as_of)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mood snapshot wasde failed: %s", exc)
        snap["wasde_deltas"] = []
    try:
        snap["futures_recap"] = _futures_recap(as_of)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mood snapshot futures failed: %s", exc)
        snap["futures_recap"] = []
    try:
        snap["macro"] = _macro(as_of)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mood snapshot macro failed: %s", exc)
        snap["macro"] = {}
    try:
        snap["drought"] = _drought_summary(as_of)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mood snapshot drought failed: %s", exc)
        snap["drought"] = {}
    try:
        snap["exports"] = _export_pace(as_of)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mood snapshot exports failed: %s", exc)
        snap["exports"] = []
    return snap


def _season(as_of: date) -> str:
    m = as_of.month
    if m in (3, 4, 5):
        return "planting"
    if m == 6:
        return "emergence"
    if m == 7:
        return "pollination"
    if m == 8:
        return "grain-fill"
    if m in (9, 10):
        return "harvest"
    if m == 11:
        return "post-harvest"
    return "winter"


def _wasde_deltas(as_of: date) -> list[dict[str, Any]]:
    """For each commodity, compute the latest STU delta vs prior release."""
    sql = text(
        """
        WITH r AS (
            SELECT commodity, marketing_year, release_date,
                   stocks_to_use, ending_stocks, world_production,
                   ROW_NUMBER() OVER (
                       PARTITION BY commodity, marketing_year
                       ORDER BY release_date DESC
                   ) AS rn
            FROM wasde_releases
            WHERE release_date <= :as_of
        )
        SELECT cur.commodity, cur.marketing_year, cur.release_date,
               cur.stocks_to_use AS stu_cur,
               prev.stocks_to_use AS stu_prev,
               cur.ending_stocks AS es_cur,
               prev.ending_stocks AS es_prev
        FROM r cur
        LEFT JOIN r prev
            ON cur.commodity = prev.commodity
            AND cur.marketing_year = prev.marketing_year
            AND prev.rn = 2
        WHERE cur.rn = 1
        """
    )
    out: list[dict[str, Any]] = []
    with get_sync_session() as s:
        for row in s.execute(sql, {"as_of": as_of}).all():
            stu_delta = (
                float(row.stu_cur) - float(row.stu_prev)
                if row.stu_cur is not None and row.stu_prev is not None
                else None
            )
            out.append(
                {
                    "commodity": row.commodity,
                    "marketing_year": row.marketing_year,
                    "release_date": str(row.release_date),
                    "stocks_to_use_pct": (
                        round(float(row.stu_cur) * 100, 2)
                        if row.stu_cur is not None
                        else None
                    ),
                    "stocks_to_use_delta_pp": (
                        round(stu_delta * 100, 2) if stu_delta is not None else None
                    ),
                    "ending_stocks": float(row.es_cur) if row.es_cur is not None else None,
                }
            )
    return out


def _futures_recap(as_of: date) -> list[dict[str, Any]]:
    """30-day price + volatility recap per commodity."""
    sql = text(
        """
        WITH series AS (
            SELECT commodity, trade_date, settlement,
                   ROW_NUMBER() OVER (
                       PARTITION BY commodity ORDER BY trade_date DESC
                   ) AS rn
            FROM futures_daily
            WHERE trade_date <= :as_of
              AND trade_date >= (DATE :as_of - INTERVAL '60 days')
        )
        SELECT commodity,
               MAX(CASE WHEN rn = 1 THEN settlement END) AS px_now,
               MAX(CASE WHEN rn = 22 THEN settlement END) AS px_30d_ago,
               STDDEV_SAMP(settlement) AS sigma_60d,
               COUNT(*) AS n_days
        FROM series
        GROUP BY commodity
        """
    )
    out: list[dict[str, Any]] = []
    with get_sync_session() as s:
        for row in s.execute(sql, {"as_of": as_of}).all():
            now = float(row.px_now) if row.px_now is not None else None
            then = float(row.px_30d_ago) if row.px_30d_ago is not None else None
            move = (
                round((now - then) / then * 100, 2)
                if now and then and then > 0
                else None
            )
            out.append(
                {
                    "commodity": row.commodity,
                    "front_month_settlement": now,
                    "pct_30d": move,
                    "sigma_60d": (
                        round(float(row.sigma_60d), 2) if row.sigma_60d else None
                    ),
                    "n_days": int(row.n_days),
                }
            )
    return out


def _macro(as_of: date) -> dict[str, Any]:
    """DXY 30-day change."""
    sql = text(
        """
        WITH series AS (
            SELECT trade_date, dxy,
                   ROW_NUMBER() OVER (ORDER BY trade_date DESC) AS rn
            FROM dxy_daily
            WHERE trade_date <= :as_of
              AND trade_date >= (DATE :as_of - INTERVAL '60 days')
        )
        SELECT
            MAX(CASE WHEN rn = 1 THEN dxy END) AS dxy_now,
            MAX(CASE WHEN rn = 22 THEN dxy END) AS dxy_30d_ago
        FROM series
        """
    )
    with get_sync_session() as s:
        row = s.execute(sql, {"as_of": as_of}).first()
    if not row or row.dxy_now is None:
        return {}
    now = float(row.dxy_now)
    then = float(row.dxy_30d_ago) if row.dxy_30d_ago is not None else None
    return {
        "dxy_now": round(now, 2),
        "dxy_30d_ago": round(then, 2) if then else None,
        "dxy_pct_30d": round((now - then) / then * 100, 2) if then and then > 0 else None,
    }


def _drought_summary(as_of: date) -> dict[str, Any]:
    """National-percentile and top-3 dry major-producer states."""
    # drought_index is annualized; use the most recent year row available.
    sql_top = text(
        """
        SELECT state_fips, dsci_fall_avg, year
        FROM drought_index
        WHERE year = (
            SELECT MAX(year) FROM drought_index WHERE year <= EXTRACT(YEAR FROM DATE :as_of)
        )
          AND dsci_fall_avg IS NOT NULL
        ORDER BY dsci_fall_avg DESC
        LIMIT 5
        """
    )
    with get_sync_session() as s:
        rows = s.execute(sql_top, {"as_of": as_of}).all()
    if not rows:
        return {}
    return {
        "year": int(rows[0].year),
        "top_states": [
            {"state_fips": r.state_fips, "dsci_fall_avg": float(r.dsci_fall_avg)}
            for r in rows
        ],
    }


def _export_pace(as_of: date) -> list[dict[str, Any]]:
    """Latest-week outstanding-sales pace vs same-week 5-year average."""
    sql = text(
        """
        WITH cur AS (
            SELECT DISTINCT ON (commodity) commodity, as_of_date,
                   marketing_year, outstanding_sales_mt
            FROM export_commitments
            WHERE as_of_date <= :as_of
              AND outstanding_sales_mt IS NOT NULL
            ORDER BY commodity, as_of_date DESC
        ),
        baseline AS (
            SELECT commodity,
                   AVG(outstanding_sales_mt) AS avg_sales,
                   COUNT(DISTINCT marketing_year) AS n_years
            FROM export_commitments
            WHERE outstanding_sales_mt IS NOT NULL
              AND as_of_date < :as_of
              AND as_of_date >= (DATE :as_of - INTERVAL '6 years')
              AND EXTRACT(WEEK FROM as_of_date) = (
                  SELECT EXTRACT(WEEK FROM MAX(c2.as_of_date))
                  FROM export_commitments c2
                  WHERE c2.commodity = export_commitments.commodity
                    AND c2.as_of_date <= :as_of
              )
            GROUP BY commodity
            HAVING COUNT(DISTINCT marketing_year) >= 3
        )
        SELECT cur.commodity, cur.as_of_date, cur.marketing_year,
               cur.outstanding_sales_mt, baseline.avg_sales, baseline.n_years
        FROM cur LEFT JOIN baseline USING (commodity)
        """
    )
    out: list[dict[str, Any]] = []
    with get_sync_session() as s:
        for row in s.execute(sql, {"as_of": as_of}).all():
            cur_v = float(row.outstanding_sales_mt) if row.outstanding_sales_mt else None
            avg = float(row.avg_sales) if row.avg_sales else None
            pace_pct = (
                round((cur_v - avg) / avg * 100, 1)
                if cur_v is not None and avg and avg > 0
                else None
            )
            out.append(
                {
                    "commodity": row.commodity,
                    "as_of_date": str(row.as_of_date),
                    "outstanding_sales_mt": cur_v,
                    "pace_pct_vs_5yr": pace_pct,
                    "n_baseline_years": int(row.n_years) if row.n_years else None,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Format snapshot into the LLM user message.
# ---------------------------------------------------------------------------


def _format_snapshot(snap: dict[str, Any]) -> str:
    """Render the snapshot into a compact, factual prose block for the LLM.

    Goal: ~3-4K tokens of dense facts the model can synthesize. No prose
    interpretation here — keep it numeric.
    """
    lines: list[str] = []
    lines.append(f"AS_OF_DATE: {snap['as_of_date']}")
    lines.append(f"SEASON: {snap['season']}")
    lines.append("")
    lines.append("WASDE_DELTAS (most recent release per commodity):")
    for w in snap.get("wasde_deltas", []):
        lines.append(
            f"  - {w['commodity']} MY {w['marketing_year']} ({w['release_date']}): "
            f"STU={w['stocks_to_use_pct']}% (delta vs prior release: "
            f"{w['stocks_to_use_delta_pp']:+.2f} pp), ending_stocks={w['ending_stocks']}"
            if w["stocks_to_use_delta_pp"] is not None
            else f"  - {w['commodity']} MY {w['marketing_year']} ({w['release_date']}): "
            f"STU={w['stocks_to_use_pct']}% (no prior release)"
        )
    lines.append("")
    lines.append("FUTURES_RECAP (60-day window, front-month):")
    for f in snap.get("futures_recap", []):
        lines.append(
            f"  - {f['commodity']}: settlement={f['front_month_settlement']}, "
            f"30d_change={f['pct_30d']}%, 60d_sigma={f['sigma_60d']}"
        )
    lines.append("")
    macro = snap.get("macro", {})
    if macro:
        lines.append(
            f"MACRO: DXY={macro.get('dxy_now')} "
            f"(30d_change={macro.get('dxy_pct_30d')}%)"
        )
    else:
        lines.append("MACRO: (no DXY data)")
    lines.append("")
    drought = snap.get("drought", {})
    if drought:
        lines.append(f"DROUGHT (year {drought.get('year')}, top-5 states by DSCI fall avg):")
        from backend.agent.signals._fips_label import state_label

        for d in drought.get("top_states", []):
            lines.append(
                f"  - {state_label(d['state_fips'])}: DSCI={d['dsci_fall_avg']:.0f}"
            )
    else:
        lines.append("DROUGHT: (no data)")
    lines.append("")
    lines.append("EXPORTS (current marketing year vs 5-year same-week baseline):")
    for e in snap.get("exports", []):
        if e.get("pace_pct_vs_5yr") is not None:
            lines.append(
                f"  - {e['commodity']} MY {e['marketing_year']}: "
                f"outstanding={e['outstanding_sales_mt']:.0f} mt, "
                f"pace={e['pace_pct_vs_5yr']:+.1f}% vs {e['n_baseline_years']}y avg"
            )
        else:
            lines.append(
                f"  - {e['commodity']}: outstanding={e['outstanding_sales_mt']}, "
                "no baseline"
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence (called from publisher.py once a run completes).
# ---------------------------------------------------------------------------


def persist_mood(run_id: int, mood: Mood) -> None:
    """Insert one row into agent_mood. Idempotent via ON CONFLICT (run_id)."""
    sql = text(
        """
        INSERT INTO agent_mood (run_id, mood_tags, primary_narrative, biases, avoid_unless_dramatic)
        VALUES (:run_id, CAST(:tags AS jsonb), :narrative, CAST(:biases AS jsonb), CAST(:avoid AS jsonb))
        """
    )
    with get_sync_session() as s:
        s.execute(
            sql,
            {
                "run_id": run_id,
                "tags": json.dumps(mood.mood_tags),
                "narrative": mood.primary_narrative,
                "biases": json.dumps(mood.biases),
                "avoid": json.dumps(mood.avoid_unless_dramatic),
            },
        )
        s.commit()
