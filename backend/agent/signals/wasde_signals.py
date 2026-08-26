"""WASDE-domain signal source.

Spec §4.1 source 4: stocks-to-use surprise > X bps, national, monthly post-WASDE.

Triggers when the most-recent release (within the last 14 days of as_of_date)
shows a stocks-to-use change > 2 percentage points vs prior release for any
major commodity. The threshold is intentionally generous — most WASDE
releases produce at least one move per commodity.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import text

from backend.agent.signal_board import Signal
from backend.agent.signals._common import (
    ScoreParts,
    calendar_fit_score,
    compute_score,
    novelty_score,
    reach_score,
)
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)

# The agent runs weekly (Sundays), so an 8-day lookback means each WASDE
# release can fire on exactly one run. The old 14-day window let the same
# release lead two consecutive issues (w28/w29 repeat, 2026-08-03 review).
WASDE_LOOKBACK_DAYS = 8

# Thresholds are calibrated to the CORRECT stocks-to-use definition
# (ending stocks / total use, ~10-15% for corn, ~40% for wheat). A 0.5 pp
# month-over-month move is a genuine story at that scale; 3 pp is a shock.
# (The old 2 pp trigger dated from the buggy stocks/exports ratio, which ran
# ~6x too high.)
STU_DELTA_TRIGGER_PP = 0.005    # 0.5 percentage points
MAGNITUDE_DELTA_CAP_PP = 0.03   # ±3 pp -> magnitude 100


def collect(as_of_date: date) -> list[Signal]:
    cutoff = as_of_date - timedelta(days=WASDE_LOOKBACK_DAYS)
    sql = text(
        """
        WITH releases AS (
            SELECT commodity, release_date, marketing_year, stocks_to_use,
                   ROW_NUMBER() OVER (
                       PARTITION BY commodity, marketing_year
                       ORDER BY release_date DESC
                   ) AS rn
            FROM wasde_releases
            WHERE stocks_to_use IS NOT NULL
              AND release_date <= :as_of
        )
        SELECT cur.commodity, cur.release_date, cur.marketing_year,
               cur.stocks_to_use AS stu_cur,
               prev.stocks_to_use AS stu_prev
        FROM releases cur
        JOIN releases prev ON cur.commodity = prev.commodity
                          AND cur.marketing_year = prev.marketing_year
                          AND cur.rn = 1 AND prev.rn = 2
        WHERE cur.release_date >= :cutoff
          AND ABS(cur.stocks_to_use - prev.stocks_to_use) >= :trigger
        """
    )

    out: list[Signal] = []
    with get_sync_session() as session:
        rows = session.execute(
            sql, {"as_of": as_of_date, "cutoff": cutoff, "trigger": STU_DELTA_TRIGGER_PP}
        ).all()

    for r in rows:
        delta = float(r.stu_cur) - float(r.stu_prev)
        magnitude = min(100.0, abs(delta) / MAGNITUDE_DELTA_CAP_PP * 100)
        scope = "national"
        domain = "wasde"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.commodity),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of_date),
            calendar=calendar_fit_score(domain, as_of_date),
        )
        score = compute_score(parts)

        # Negative STU change = tighter supply = bullish.
        direction = "positive" if delta < 0 else "negative"

        out.append(
            Signal(
                id=f"wasde-stu:{r.commodity}:{r.release_date}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{r.commodity.capitalize()} stocks-to-use moved "
                    f"{delta * 100:+.2f} pp in the {r.release_date} WASDE "
                    f"({float(r.stu_prev) * 100:.1f}% → {float(r.stu_cur) * 100:.1f}%)"
                ),
                score=score,
                direction=direction,
                evidence={
                    "commodity": r.commodity,
                    "release_date": str(r.release_date),
                    "marketing_year": r.marketing_year,
                    "stocks_to_use_current": float(r.stu_cur),
                    "stocks_to_use_prior": float(r.stu_prev),
                    "delta_pp": round(delta * 100, 3),
                    "score_parts": parts.__dict__,
                },
                sources=["wasde_releases"],
            )
        )
    return out
