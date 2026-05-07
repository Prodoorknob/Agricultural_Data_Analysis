"""Weather/drought-domain signal sources.

Spec §4.1:
    Source 5: drought_index DSCI jump > 20 in major producer state, weekly.
              drought_index is annualized in our schema, so we approximate by
              comparing year-over-year DSCI for the in-progress year to the
              prior year, scoped to top producer states.
    Source 6: NASS CCI week-over-week drop > 10 pts, state, weekly Apr-Oct.
              We approximate from feature_weekly.cci_cumul deltas.
    Source 9: NOAA precip anomaly > 30% from normal in major producer.
              feature_weekly.precip_deficit holds (observed - normal) in mm.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from backend.agent.signal_board import Signal
from backend.agent.signals._common import (
    ScoreParts,
    COMMODITY_STATE_REACH_FRACTION,
    calendar_fit_score,
    compute_score,
    novelty_score,
    reach_score,
)
from backend.agent.signals._fips_label import state_label
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)

DSCI_JUMP_TRIGGER = 75.0          # absolute DSCI jump points
CCI_DROP_TRIGGER_PTS = 10.0
PRECIP_ANOMALY_TRIGGER_PCT = 30.0


def collect(as_of_date: date) -> list[Signal]:
    out: list[Signal] = []
    out.extend(_collect_drought_jumps(as_of_date))
    out.extend(_collect_cci_drops(as_of_date))
    out.extend(_collect_precip_anomalies(as_of_date))
    return out


def _major_producer_states() -> set[str]:
    fips: set[str] = set()
    for cm in COMMODITY_STATE_REACH_FRACTION.values():
        fips.update(cm.keys())
    return fips


def _collect_drought_jumps(as_of: date) -> list[Signal]:
    """Source 5: year-over-year DSCI jump > threshold in a major producer state."""
    major = _major_producer_states()
    if not major:
        return []

    sql = text(
        """
        SELECT a.state_fips, a.year AS cur_year, a.dsci_fall_avg AS cur_dsci,
               b.year AS prev_year, b.dsci_fall_avg AS prev_dsci
        FROM drought_index a
        JOIN drought_index b ON a.state_fips = b.state_fips
                            AND b.year = a.year - 1
        WHERE a.year = :year
          AND a.state_fips = ANY(:major)
          AND a.dsci_fall_avg IS NOT NULL
          AND b.dsci_fall_avg IS NOT NULL
          AND ABS(a.dsci_fall_avg - b.dsci_fall_avg) >= :trigger
        """
    )

    out: list[Signal] = []
    with get_sync_session() as session:
        rows = session.execute(
            sql,
            {
                "year": as_of.year,
                "major": list(major),
                "trigger": DSCI_JUMP_TRIGGER,
            },
        ).all()

    for r in rows:
        delta = float(r.cur_dsci) - float(r.prev_dsci)
        magnitude = min(100.0, abs(delta) / 200.0 * 100)
        scope = f"state:{r.state_fips}"
        domain = "drought"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of),
            calendar=calendar_fit_score(domain, as_of),
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"drought-jump:{r.state_fips}:{r.cur_year}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{state_label(r.state_fips)} fall DSCI jumped {delta:+.0f} "
                    f"points year-over-year ({float(r.prev_dsci):.0f} → "
                    f"{float(r.cur_dsci):.0f})"
                ),
                score=score,
                direction="negative" if delta > 0 else "positive",
                evidence={
                    "state_fips": r.state_fips,
                    "current_year": int(r.cur_year),
                    "prior_year": int(r.prev_year),
                    "current_dsci_fall_avg": float(r.cur_dsci),
                    "prior_dsci_fall_avg": float(r.prev_dsci),
                    "delta_points": round(delta, 1),
                    "score_parts": parts.__dict__,
                },
                sources=["drought_index"],
            )
        )
    return out


def _collect_cci_drops(as_of: date) -> list[Signal]:
    """Source 6: w/w cci_cumul drop ≥ 10 pts, state-level (rolled up from
    counties via average), Apr–Oct only."""
    if as_of.month not in range(4, 11):
        return []

    sql = text(
        """
        WITH state_week AS (
            SELECT SUBSTRING(fips FROM 1 FOR 2) AS state_fips,
                   crop, crop_year, week,
                   AVG(cci_cumul) AS cci_state_avg
            FROM feature_weekly
            WHERE crop_year = :year
              AND ingest_ts <= :as_of
              AND cci_cumul IS NOT NULL
            GROUP BY 1, 2, 3, 4
        ),
        ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY state_fips, crop ORDER BY week DESC
                   ) AS rn
            FROM state_week
        )
        SELECT cur.state_fips, cur.crop, cur.week, cur.cci_state_avg AS cci_cur,
               prev.week AS prev_week, prev.cci_state_avg AS cci_prev
        FROM ranked cur
        JOIN ranked prev ON cur.state_fips = prev.state_fips
                        AND cur.crop = prev.crop
                        AND cur.rn = 1 AND prev.rn = 2
        WHERE prev.cci_state_avg - cur.cci_state_avg >= :trigger
        """
    )

    out: list[Signal] = []
    try:
        with get_sync_session() as session:
            rows = session.execute(
                sql,
                {
                    "year": as_of.year,
                    "as_of": as_of,
                    "trigger": CCI_DROP_TRIGGER_PTS,
                },
            ).all()
    except Exception as exc:
        logger.warning("CCI signal source failed (likely empty feature_weekly): %s", exc)
        return []

    for r in rows:
        drop = float(r.cci_prev) - float(r.cci_cur)
        magnitude = min(100.0, drop / 30.0 * 100)
        scope = f"state:{r.state_fips}"
        domain = "weather"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.crop),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of),
            calendar=calendar_fit_score(domain, as_of),
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"cci-drop:{r.crop}:{r.state_fips}:{r.week}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{state_label(r.state_fips)} {r.crop} crop condition fell "
                    f"{drop:.0f} points week-over-week (week {r.prev_week}→{r.week})"
                ),
                score=score,
                direction="negative",
                evidence={
                    "state_fips": r.state_fips,
                    "crop": r.crop,
                    "current_week": int(r.week),
                    "prior_week": int(r.prev_week),
                    "cci_current": float(r.cci_cur),
                    "cci_prior": float(r.cci_prev),
                    "drop_points": round(drop, 1),
                    "score_parts": parts.__dict__,
                },
                sources=["feature_weekly"],
            )
        )
    return out


def _collect_precip_anomalies(as_of: date) -> list[Signal]:
    """Source 9: precip anomaly > 30% from normal, county scope rolled up to
    state for top producers. precip_deficit is observed minus normal in mm."""
    major = _major_producer_states()
    if not major:
        return []

    sql = text(
        """
        SELECT SUBSTRING(fips FROM 1 FOR 2) AS state_fips,
               crop, crop_year, week,
               AVG(precip_deficit) AS deficit_avg,
               COUNT(*) AS n_counties
        FROM feature_weekly
        WHERE crop_year = :year
          AND ingest_ts <= :as_of
          AND precip_deficit IS NOT NULL
          AND SUBSTRING(fips FROM 1 FOR 2) = ANY(:major)
        GROUP BY 1, 2, 3, 4
        HAVING ABS(AVG(precip_deficit)) > 0
        """
    )

    out: list[Signal] = []
    try:
        with get_sync_session() as session:
            rows = session.execute(
                sql, {"year": as_of.year, "as_of": as_of, "major": list(major)}
            ).all()
    except Exception as exc:
        logger.warning("Precip signal source failed: %s", exc)
        return []

    # Crude: assume "normal" is ~75 mm/week growing season; deficit/normal *
    # 100 → anomaly %. This is a placeholder until we wire prism_normals.
    BASELINE_NORMAL_MM = 75.0

    for r in rows:
        deficit = float(r.deficit_avg)
        anomaly_pct = deficit / BASELINE_NORMAL_MM * 100
        if abs(anomaly_pct) < PRECIP_ANOMALY_TRIGGER_PCT:
            continue

        magnitude = min(100.0, abs(anomaly_pct) / 80.0 * 100)
        scope = f"state:{r.state_fips}"
        domain = "weather"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.crop),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of),
            calendar=calendar_fit_score(domain, as_of),
        )
        score = compute_score(parts)

        # Negative deficit = drier than normal = bearish on yield.
        direction = "negative" if deficit < 0 else "positive"

        out.append(
            Signal(
                id=f"precip-anomaly:{r.crop}:{r.state_fips}:{r.week}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{state_label(r.state_fips)} {r.crop} growing-season precip "
                    f"running {anomaly_pct:+.0f}% from normal at week {r.week}"
                ),
                score=score,
                direction=direction,
                evidence={
                    "state_fips": r.state_fips,
                    "crop": r.crop,
                    "week": int(r.week),
                    "precip_deficit_mm_avg": round(deficit, 1),
                    "anomaly_pct_vs_baseline": round(anomaly_pct, 1),
                    "n_counties": int(r.n_counties),
                    "score_parts": parts.__dict__,
                },
                sources=["feature_weekly"],
            )
        )
    return out
