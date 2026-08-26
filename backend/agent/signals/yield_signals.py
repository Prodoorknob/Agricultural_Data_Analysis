"""Yield-domain signal sources.

Spec §4.1:
    Source 1: yield_forecasts week-over-week p50 delta > 5%, county scope, weekly Apr-Oct.
    Source 11: yield_accuracy outliers — model big miss, county scope, weekly.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from backend.agent.signal_board import Signal
from backend.agent.signals._common import (
    ScoreParts,
    calendar_fit_score,
    compute_score,
    novelty_score,
    reach_score,
)
from backend.agent.signals._fips_label import county_label
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)


# Trigger thresholds.
WOW_DELTA_TRIGGER_PCT = 5.0
ACCURACY_MISS_TRIGGER_PCT = 15.0   # county model miss > 15%

# Magnitude scaling: cap %-deltas to a band so a single 50% county outlier
# doesn't dominate. Magnitude 0-100 from 0-30 abs %-delta.
MAGNITUDE_DELTA_CAP_PCT = 30.0

# Accuracy stories are a "report card", not weekly news: yield_accuracy is a
# static walk-forward backfill refreshed roughly once a year when new-season
# actuals land. Only emit accuracy signals while that refresh is recent;
# outside the window the same 2024 rows would re-fire every Sunday (the
# w24-w31 "model missed county X" flood diagnosed in the 2026-08-03 review).
ACCURACY_FRESHNESS_DAYS = 56


def collect(as_of_date: date) -> list[Signal]:
    """Run yield-domain sources. Returns combined signal list."""
    out: list[Signal] = []
    out.extend(_collect_wow_delta(as_of_date))
    out.extend(_collect_accuracy_outliers(as_of_date))
    return out


def _collect_wow_delta(as_of: date) -> list[Signal]:
    """Source 1: week-over-week p50 delta in yield_forecasts."""
    # Skip outside the growing season.
    if as_of.month not in range(4, 11):
        return []

    # For each (fips, crop), pick the two most recent weeks <= as_of and
    # compute (cur - prior) / prior. Filter |delta| > 5%.
    sql = text(
        """
        WITH ranked AS (
            SELECT fips, crop, week, p50,
                   ROW_NUMBER() OVER (
                       PARTITION BY fips, crop
                       ORDER BY week DESC, created_at DESC
                   ) AS rn
            FROM yield_forecasts
            WHERE crop_year = :year
              AND created_at <= :as_of
        )
        SELECT cur.fips, cur.crop, cur.week, cur.p50 AS p50_cur,
               prev.week AS prev_week, prev.p50 AS p50_prev
        FROM ranked cur
        JOIN ranked prev ON cur.fips = prev.fips
                        AND cur.crop = prev.crop
                        AND cur.rn = 1 AND prev.rn = 2
        WHERE prev.p50 > 0
          AND ABS(cur.p50 - prev.p50) / prev.p50 * 100 >= :trigger
        """
    )

    out: list[Signal] = []
    with get_sync_session() as session:
        rows = session.execute(
            sql,
            {"year": as_of.year, "as_of": as_of, "trigger": WOW_DELTA_TRIGGER_PCT},
        ).all()

    for r in rows:
        delta_pct = (float(r.p50_cur) - float(r.p50_prev)) / float(r.p50_prev) * 100
        magnitude = min(100.0, abs(delta_pct) / MAGNITUDE_DELTA_CAP_PCT * 100)
        scope = f"county:{r.fips}"
        domain = "yield"

        score_parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.crop),
            novelty=0.0,  # filled below
            calendar=calendar_fit_score(domain, as_of),
        )
        # Compute pre-novelty score so novelty fn can reason about whether
        # magnitude has materially changed since last publication.
        pre_novelty = compute_score(score_parts) * (1 - 0.15)  # crude
        score_parts.novelty = novelty_score(domain, scope, pre_novelty, as_of)
        score = compute_score(score_parts)

        direction = "negative" if delta_pct < 0 else "positive"
        headline = (
            f"{r.crop.capitalize()} yield forecast for {county_label(r.fips)} "
            f"moved {delta_pct:+.1f}% week-over-week (week {r.prev_week}→{r.week})"
        )

        out.append(
            Signal(
                id=f"yield-wow:{r.crop}:{r.fips}:{r.week}",
                domain=domain,
                scope=scope,
                headline=headline,
                score=score,
                direction=direction,
                evidence={
                    "fips": r.fips,
                    "crop": r.crop,
                    "current_week": int(r.week),
                    "prior_week": int(r.prev_week),
                    "p50_current": float(r.p50_cur),
                    "p50_prior": float(r.p50_prev),
                    "delta_pct": round(delta_pct, 2),
                    "score_parts": score_parts.__dict__,
                },
                sources=["yield_forecasts"],
            )
        )
    return out


def _collect_accuracy_outliers(as_of: date) -> list[Signal]:
    """Source 11: annual model report card, quarantined (2026-08-03 review).

    Three containment rules replace the old "top-50 worst counties" firehose
    that let a single static 2024 backfill headline four issues in a row:

      1. Freshness gate — emit nothing unless the latest forecast year's
         rows were refreshed within ACCURACY_FRESHNESS_DAYS. Accuracy is
         news when new actuals land, once a year, not every Sunday after.
      2. One signal per crop — the worst county anchors the story, and the
         evidence carries the state-level aggregate (how many counties in
         that state missed, average error) so the researcher can tell the
         "what happened in the field" story instead of one number.
      3. State-keyed identity — scope/id key on (crop, state, year) rather
         than county, so 37 outlier counties in one drought event count as
         one narrative for novelty and dedup purposes.
    """
    freshness_sql = text(
        """
        SELECT MAX(forecast_year) AS yr, MAX(updated_at) AS last_update
        FROM yield_accuracy
        WHERE pct_error IS NOT NULL AND updated_at <= :as_of
        """
    )

    # Collapse to one row per (fips, crop) for the target year using the
    # latest-week, most-recent-model prediction (end-of-season output), then
    # keep only the worst county per crop, with state + crop aggregates
    # computed over the flagged set.
    sql = text(
        """
        WITH dedup AS (
            SELECT DISTINCT ON (fips, crop)
                   fips, crop, forecast_year, week,
                   actual_yield, model_p50, pct_error
            FROM yield_accuracy
            WHERE pct_error IS NOT NULL
              AND ABS(pct_error) >= :trigger
              AND updated_at <= :as_of
              AND forecast_year = :year
            ORDER BY fips, crop, week DESC, updated_at DESC
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY crop ORDER BY ABS(pct_error) DESC
                   ) AS rn,
                   COUNT(*) OVER (PARTITION BY crop) AS n_crop_misses,
                   COUNT(*) OVER (
                       PARTITION BY crop, LEFT(fips, 2)
                   ) AS n_state_misses,
                   AVG(ABS(pct_error)) OVER (
                       PARTITION BY crop, LEFT(fips, 2)
                   ) AS state_avg_abs_error
            FROM dedup
        )
        SELECT * FROM ranked WHERE rn = 1
        """
    )

    out: list[Signal] = []
    with get_sync_session() as session:
        fresh = session.execute(freshness_sql, {"as_of": as_of}).first()
        if fresh is None or fresh.yr is None or fresh.last_update is None:
            return []
        last_update = fresh.last_update
        if hasattr(last_update, "date"):
            last_update = last_update.date()
        if (as_of - last_update).days > ACCURACY_FRESHNESS_DAYS:
            logger.info(
                "accuracy source quiet: yield_accuracy year %s last refreshed "
                "%s (> %d days before %s)",
                fresh.yr, last_update, ACCURACY_FRESHNESS_DAYS, as_of,
            )
            return []

        rows = session.execute(
            sql,
            {
                "trigger": ACCURACY_MISS_TRIGGER_PCT,
                "as_of": as_of,
                "year": int(fresh.yr),
            },
        ).all()

    for r in rows:
        state_fips = str(r.fips)[:2]
        magnitude = min(100.0, abs(float(r.pct_error)) / MAGNITUDE_DELTA_CAP_PCT * 100)
        scope = f"state:{state_fips}"
        domain = "accuracy"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.crop),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of),
            calendar=0.0,
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"yield-accuracy:{r.crop}:{state_fips}:{r.forecast_year}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{r.crop.capitalize()} {r.forecast_year} season report card: "
                    f"model missed {county_label(r.fips)} by "
                    f"{float(r.pct_error):+.1f}% (worst of {int(r.n_state_misses)} "
                    f"flagged counties in its state; {int(r.n_crop_misses)} nationwide)"
                ),
                score=score,
                direction="negative" if float(r.pct_error) < 0 else "positive",
                evidence={
                    "fips": r.fips,
                    "state_fips": state_fips,
                    "crop": r.crop,
                    "forecast_year": int(r.forecast_year),
                    "actual_yield": float(r.actual_yield),
                    "model_p50": float(r.model_p50),
                    "pct_error": round(float(r.pct_error), 2),
                    "n_state_misses": int(r.n_state_misses),
                    "state_avg_abs_error": round(float(r.state_avg_abs_error), 2),
                    "n_crop_misses": int(r.n_crop_misses),
                    "score_parts": parts.__dict__,
                },
                sources=["yield_accuracy"],
            )
        )
    return out
