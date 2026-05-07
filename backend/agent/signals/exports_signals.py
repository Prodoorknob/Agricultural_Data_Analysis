"""Exports-domain signal source.

Spec §4.1 source 7: export_commitments pace vs 5yr > ±15%, national, weekly.

For each commodity, take the most recent week's outstanding_sales_mt for the
current marketing year and compare to the same calendar week's average over
the prior 5 marketing years. Trigger if the deviation exceeds 15%.
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
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)

PACE_TRIGGER_PCT = 15.0
MAGNITUDE_PACE_CAP_PCT = 50.0


def collect(as_of_date: date) -> list[Signal]:
    sql = text(
        """
        WITH cur AS (
            SELECT DISTINCT ON (commodity) commodity, marketing_year, as_of_date,
                   outstanding_sales_mt
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
        SELECT cur.commodity, cur.marketing_year, cur.as_of_date,
               cur.outstanding_sales_mt, baseline.avg_sales, baseline.n_years
        FROM cur
        JOIN baseline USING (commodity)
        WHERE baseline.avg_sales > 0
        """
    )

    out: list[Signal] = []
    with get_sync_session() as session:
        rows = session.execute(sql, {"as_of": as_of_date}).all()

    for r in rows:
        cur_sales = float(r.outstanding_sales_mt)
        baseline = float(r.avg_sales)
        pace_pct = (cur_sales - baseline) / baseline * 100
        if abs(pace_pct) < PACE_TRIGGER_PCT:
            continue

        magnitude = min(100.0, abs(pace_pct) / MAGNITUDE_PACE_CAP_PCT * 100)
        scope = "national"
        domain = "exports"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.commodity),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of_date),
            calendar=calendar_fit_score(domain, as_of_date),
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"export-pace:{r.commodity}:{r.as_of_date}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{r.commodity.capitalize()} export commitments running "
                    f"{pace_pct:+.0f}% vs {int(r.n_years)}-year same-week average"
                ),
                score=score,
                direction="positive" if pace_pct > 0 else "negative",
                evidence={
                    "commodity": r.commodity,
                    "marketing_year": r.marketing_year,
                    "as_of_date": str(r.as_of_date),
                    "outstanding_sales_mt": cur_sales,
                    "baseline_avg_mt": baseline,
                    "n_baseline_years": int(r.n_years),
                    "pace_pct_vs_5yr": round(pace_pct, 1),
                    "score_parts": parts.__dict__,
                },
                sources=["export_commitments"],
            )
        )
    return out
