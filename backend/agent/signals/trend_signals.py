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
        WHERE history.hist_std > 0
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
    """Yield trend break: county-level z > 2 vs 30y history of actuals.

    Restricted to county+crop pairs where yield_accuracy has at least 8
    observed years inside the window. The history window strictly excludes
    the year being tested — otherwise that year inflates the std and
    crushes the z-score.
    """
    cutoff_year = as_of.year - HISTORY_WINDOW_YEARS

    sql = text(
        """
        WITH latest_year AS (
            SELECT MAX(forecast_year) AS yr
            FROM yield_accuracy
            WHERE actual_yield IS NOT NULL AND updated_at <= :as_of
        ),
        history AS (
            SELECT fips, crop,
                   AVG(actual_yield) AS hist_mean,
                   STDDEV_SAMP(actual_yield) AS hist_std,
                   COUNT(*) AS n
            FROM yield_accuracy
            WHERE actual_yield IS NOT NULL
              AND forecast_year BETWEEN :cutoff AND (SELECT yr - 1 FROM latest_year)
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
              AND forecast_year = (SELECT yr FROM latest_year)
            ORDER BY fips, crop, updated_at DESC
        )
        SELECT latest.fips, latest.crop, latest.forecast_year,
               latest.actual_yield, history.hist_mean, history.hist_std, history.n
        FROM latest
        JOIN history USING (fips, crop)
        WHERE history.hist_std > 0
          AND ABS((latest.actual_yield - history.hist_mean) / history.hist_std) >= :z_trigger
        ORDER BY ABS((latest.actual_yield - history.hist_mean) / history.hist_std) DESC
        LIMIT 200
        """
    )

    out: list[Signal] = []
    try:
        with get_sync_session() as session:
            rows = session.execute(
                sql,
                {
                    "cutoff": cutoff_year,
                    "as_of": as_of,
                    "z_trigger": Z_TRIGGER,
                },
            ).all()
    except Exception as exc:
        logger.warning("yield trend break query failed: %s", exc)
        return []

    for r in rows:
        z = (float(r.actual_yield) - float(r.hist_mean)) / float(r.hist_std)
        if abs(z) < Z_TRIGGER:
            continue

        magnitude = min(100.0, abs(z) / MAGNITUDE_Z_CAP * 100)
        scope = f"county:{r.fips}"
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
                id=f"trend-yield:{r.crop}:{r.fips}:{r.forecast_year}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{county_label(r.fips)} {r.crop} {r.forecast_year} actual yield was "
                    f"{z:+.1f}σ from {int(r.n)}-year county history"
                ),
                score=score,
                direction="positive" if z > 0 else "negative",
                evidence={
                    "fips": r.fips,
                    "crop": r.crop,
                    "forecast_year": int(r.forecast_year),
                    "actual_yield": float(r.actual_yield),
                    "historical_mean": float(r.hist_mean),
                    "historical_std": float(r.hist_std),
                    "n_history_years": int(r.n),
                    "z_score": round(z, 2),
                    "score_parts": parts.__dict__,
                },
                sources=["yield_accuracy"],
            )
        )
    return out
