"""Acreage-domain signal source.

Spec §4.1 source 2: acreage_forecasts model vs USDA prospective gap > 5%,
state scope, after Mar/Jun reports.
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
from backend.agent.signals._fips_label import state_label
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)

GAP_TRIGGER_PCT = 5.0
MAGNITUDE_GAP_CAP_PCT = 15.0


def collect(as_of_date: date) -> list[Signal]:
    """Return acreage_accuracy rows where |model_vs_usda_pct| exceeds threshold,
    scoped to the most recent reported year."""
    sql = text(
        """
        SELECT forecast_year, state_fips, commodity,
               model_forecast, usda_prospective, usda_june_actual,
               model_vs_usda_pct, model_vs_actual_pct
        FROM acreage_accuracy
        WHERE updated_at <= :as_of
          AND ABS(model_vs_usda_pct) >= :trigger
          AND model_vs_usda_pct IS NOT NULL
          AND forecast_year = (
              SELECT MAX(forecast_year) FROM acreage_accuracy
              WHERE updated_at <= :as_of AND model_vs_usda_pct IS NOT NULL
          )
        ORDER BY ABS(model_vs_usda_pct) DESC
        LIMIT 30
        """
    )

    out: list[Signal] = []
    with get_sync_session() as session:
        rows = session.execute(sql, {"as_of": as_of_date, "trigger": GAP_TRIGGER_PCT}).all()

    for r in rows:
        gap = float(r.model_vs_usda_pct)
        magnitude = min(100.0, abs(gap) / MAGNITUDE_GAP_CAP_PCT * 100)
        scope = "national" if r.state_fips == "00" else f"state:{r.state_fips}"
        scope_label = "the U.S." if r.state_fips == "00" else state_label(r.state_fips)
        domain = "acreage"
        commodity = (r.commodity or "").split("_")[0]  # wheat_winter -> wheat

        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=commodity),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of_date),
            calendar=calendar_fit_score(domain, as_of_date),
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"acreage-gap:{r.commodity}:{r.state_fips}:{r.forecast_year}",
                domain=domain,
                scope=scope,
                headline=(
                    f"Model vs USDA Prospective Plantings gap of {gap:+.1f}% "
                    f"for {r.commodity} in {scope_label} ({r.forecast_year})"
                ),
                score=score,
                direction="positive" if gap > 0 else "negative",
                evidence={
                    "commodity": r.commodity,
                    "forecast_year": int(r.forecast_year),
                    "state_fips": r.state_fips,
                    "model_forecast": float(r.model_forecast) if r.model_forecast else None,
                    "usda_prospective": float(r.usda_prospective) if r.usda_prospective else None,
                    "usda_june_actual": (
                        float(r.usda_june_actual) if r.usda_june_actual else None
                    ),
                    "model_vs_usda_pct": round(gap, 2),
                    "model_vs_actual_pct": (
                        round(float(r.model_vs_actual_pct), 2)
                        if r.model_vs_actual_pct is not None else None
                    ),
                    "score_parts": parts.__dict__,
                },
                sources=["acreage_accuracy", "acreage_forecasts"],
            )
        )
    return out
