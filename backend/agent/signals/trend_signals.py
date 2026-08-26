"""Long-history trend-break signal source.

Spec §4.1 source 10: long-history trend break (acres or yield z > 2 vs 30yr),
state, monthly.

Pulls state-level acreage_forecasts (current year) vs the rolling 30-year
historical mean and stdev computed from `acreage_accuracy.usda_june_actual`
where available; falls back to the realised `acreage_forecasts` series when
deeper history is missing.

Yield trend break is only computed for years where actuals are present in
`yield_accuracy` — typically a tail-of-year signal for the prior season.
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
from backend.agent.signals._fips_label import county_label, state_label
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)

Z_TRIGGER = 2.0
MAGNITUDE_Z_CAP = 4.0
HISTORY_WINDOW_YEARS = 30

# Guard against degenerate z-scores: a county series with a near-constant
# history (std < 5% of mean) produces meaningless ±100σ "breaks" that are
# data artifacts, not agronomy. Real county yield CV runs 10-25%.
MIN_HISTORY_CV = 0.05

# Yield trend breaks come from the same once-a-year yield_accuracy refresh
# as the accuracy source. Same quarantine: emit only while the refresh is
# recent, otherwise the static rows re-fire every Sunday (the post-accuracy
# firehose observed 2026-08-26: 18/20 candidates were 2024 county rows).
TREND_FRESHNESS_DAYS = 56


def collect(as_of_date: date) -> list[Signal]:
    out: list[Signal] = []
    out.extend(_collect_acreage_trend_breaks(as_of_date))
    out.extend(_collect_yield_trend_breaks(as_of_date))
    return out


def _collect_acreage_trend_breaks(as_of: date) -> list[Signal]:
    """Use acreage_accuracy.usda_june_actual as the long-history series."""
    cutoff_year = as_of.year - HISTORY_WINDOW_YEARS

    sql = text(
        """
        WITH history AS (
            SELECT state_fips, commodity,
                   AVG(usda_june_actual) AS hist_mean,
                   STDDEV_SAMP(usda_june_actual) AS hist_std,
                   COUNT(*) AS n
            FROM acreage_accuracy
            WHERE usda_june_actual IS NOT NULL
              AND forecast_year BETWEEN :cutoff AND :prev_year
              AND updated_at <= :as_of
            GROUP BY state_fips, commodity
            HAVING COUNT(*) >= 8
        ),
        latest AS (
            SELECT state_fips, commodity, forecast_year, forecast_acres
            FROM acreage_forecasts
            WHERE forecast_year = :cur_year
              AND created_at <= :as_of
              AND state_fips != '00'
        )
        SELECT latest.state_fips, latest.commodity, latest.forecast_year,
               latest.forecast_acres AS model_forecast,
               history.hist_mean, history.hist_std, history.n
        FROM latest
        JOIN history USING (state_fips, commodity)
        WHERE history.hist_mean > 0
          AND history.hist_std >= 0.03 * history.hist_mean
        """
    )

    out: list[Signal] = []
    try:
        with get_sync_session() as session:
            rows = session.execute(
                sql,
                {
                    "cutoff": cutoff_year,
                    "prev_year": as_of.year - 1,
                    "cur_year": as_of.year,
                    "as_of": as_of,
                },
            ).all()
    except Exception as exc:
        logger.warning("acreage trend break query failed: %s", exc)
        return []

    for r in rows:
        z = (float(r.model_forecast) - float(r.hist_mean)) / float(r.hist_std)
        if abs(z) < Z_TRIGGER:
            continue

        magnitude = min(100.0, abs(z) / MAGNITUDE_Z_CAP * 100)
        scope = f"state:{r.state_fips}"
        domain = "trend_break"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(
                domain, scope, commodity=(r.commodity or "").split("_")[0]
            ),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of),
            calendar=calendar_fit_score("acreage", as_of),
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"trend-acreage:{r.commodity}:{r.state_fips}:{r.forecast_year}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{state_label(r.state_fips)} {r.commodity} acres ran "
                    f"{z:+.1f}σ from {int(r.n)}-year history"
                ),
                score=score,
                direction="positive" if z > 0 else "negative",
                evidence={
                    "state_fips": r.state_fips,
                    "commodity": r.commodity,
                    "forecast_year": int(r.forecast_year),
                    "model_forecast_acres": float(r.model_forecast),
                    "historical_mean": float(r.hist_mean),
                    "historical_std": float(r.hist_std),
                    "n_history_years": int(r.n),
                    "z_score": round(z, 2),
                    "score_parts": parts.__dict__,
                },
                sources=["acreage_forecasts", "acreage_accuracy"],
            )
        )
    return out


def _collect_yield_trend_breaks(as_of: date) -> list[Signal]:
    """Yield trend break: county z > 2 vs 30y history, quarantined like the
    accuracy source (2026-08-26):

      1. Freshness gate — yield_accuracy is refreshed once a year; outside
         that window the same static rows would re-fire every Sunday.
      2. CV floor — near-constant county series produce ±100σ artifacts;
         require hist_std >= 5% of hist_mean.
      3. One signal per (crop, state) — the worst county anchors, the
         evidence carries how many counties in the state broke trend, which
         is the actual regional weather story worth writing.

    The history window strictly excludes the year being tested — otherwise
    that year inflates the std and crushes the z-score.
    """
    cutoff_year = as_of.year - HISTORY_WINDOW_YEARS

    freshness_sql = text(
        """
        SELECT MAX(forecast_year) AS yr, MAX(updated_at) AS last_update
        FROM yield_accuracy
        WHERE actual_yield IS NOT NULL AND updated_at <= :as_of
        """
    )

    sql = text(
        """
        WITH history AS (
            SELECT fips, crop,
                   AVG(actual_yield) AS hist_mean,
                   STDDEV_SAMP(actual_yield) AS hist_std,
                   COUNT(*) AS n
            FROM yield_accuracy
            WHERE actual_yield IS NOT NULL
              AND forecast_year BETWEEN :cutoff AND :prev_year
              AND updated_at <= :as_of
            GROUP BY fips, crop
            HAVING COUNT(*) >= 8
        ),
        latest AS (
            SELECT DISTINCT ON (fips, crop)
                   fips, crop, forecast_year, actual_yield
            FROM yield_accuracy
            WHERE actual_yield IS NOT NULL
              AND updated_at <= :as_of
              AND forecast_year = :year
            ORDER BY fips, crop, updated_at DESC
        ),
        scored AS (
            SELECT latest.fips, latest.crop, latest.forecast_year,
                   latest.actual_yield, history.hist_mean, history.hist_std,
                   history.n,
                   (latest.actual_yield - history.hist_mean) / history.hist_std AS z
            FROM latest
            JOIN history USING (fips, crop)
            WHERE history.hist_mean > 0
              AND history.hist_std >= :min_cv * history.hist_mean
              AND ABS((latest.actual_yield - history.hist_mean) / history.hist_std)
                  >= :z_trigger
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY crop, LEFT(fips, 2) ORDER BY ABS(z) DESC
                   ) AS rn,
                   COUNT(*) OVER (PARTITION BY crop, LEFT(fips, 2)) AS n_state,
                   AVG(z) OVER (PARTITION BY crop, LEFT(fips, 2)) AS state_avg_z
            FROM scored
        )
        SELECT * FROM ranked
        WHERE rn = 1
        ORDER BY ABS(z) DESC
        LIMIT 12
        """
    )

    out: list[Signal] = []
    try:
        with get_sync_session() as session:
            fresh = session.execute(freshness_sql, {"as_of": as_of}).first()
            if fresh is None or fresh.yr is None or fresh.last_update is None:
                return []
            last_update = fresh.last_update
            if hasattr(last_update, "date"):
                last_update = last_update.date()
            if (as_of - last_update).days > TREND_FRESHNESS_DAYS:
                logger.info(
                    "yield trend-break source quiet: year %s last refreshed %s",
                    fresh.yr, last_update,
                )
                return []

            rows = session.execute(
                sql,
                {
                    "cutoff": cutoff_year,
                    "prev_year": int(fresh.yr) - 1,
                    "year": int(fresh.yr),
                    "as_of": as_of,
                    "z_trigger": Z_TRIGGER,
                    "min_cv": MIN_HISTORY_CV,
                },
            ).all()
    except Exception as exc:
        logger.warning("yield trend break query failed: %s", exc)
        return []

    for r in rows:
        z = float(r.z)
        state_fips = str(r.fips)[:2]
        magnitude = min(100.0, abs(z) / MAGNITUDE_Z_CAP * 100)
        scope = f"state:{state_fips}"
        domain = "trend_break"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.crop),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of),
            calendar=0.0,
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"trend-yield:{r.crop}:{state_fips}:{r.forecast_year}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{state_label(state_fips)} {r.crop} {r.forecast_year}: "
                    f"{int(r.n_state)} counties broke their {int(r.n)}-year yield "
                    f"trend (worst: {county_label(r.fips)} at {z:+.1f}σ)"
                ),
                score=score,
                direction="positive" if float(r.state_avg_z) > 0 else "negative",
                evidence={
                    "fips": r.fips,
                    "state_fips": state_fips,
                    "crop": r.crop,
                    "forecast_year": int(r.forecast_year),
                    "actual_yield": float(r.actual_yield),
                    "historical_mean": float(r.hist_mean),
                    "historical_std": float(r.hist_std),
                    "n_history_years": int(r.n),
                    "z_score": round(z, 2),
                    "n_state_counties_flagged": int(r.n_state),
                    "state_avg_z": round(float(r.state_avg_z), 2),
                    "score_parts": parts.__dict__,
                },
                sources=["yield_accuracy"],
            )
        )
    return out
