"""Price/futures-domain signal sources.

Spec §4.1:
    Source 3: price_forecasts regime distance > 3σ (national, daily).
              We surface rows where regime_anomaly = TRUE in the last 14 days.
    Source 8: futures_daily 5-day move > 2σ historical (national, daily).
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

REGIME_LOOKBACK_DAYS = 14
FUTURES_MOVE_TRIGGER_SIGMA = 2.0


def collect(as_of_date: date) -> list[Signal]:
    out: list[Signal] = []
    out.extend(_collect_regime_anomalies(as_of_date))
    out.extend(_collect_futures_moves(as_of_date))
    return out


def _collect_regime_anomalies(as_of: date) -> list[Signal]:
    """Source 3: regime_anomaly flag from the price ensemble."""
    cutoff = as_of - timedelta(days=REGIME_LOOKBACK_DAYS)
    sql = text(
        """
        SELECT DISTINCT ON (commodity)
               commodity, run_date, horizon_month,
               p10, p50, p90, key_driver, regime_anomaly, model_ver
        FROM price_forecasts
        WHERE created_at <= :as_of
          AND created_at >= :cutoff
          AND regime_anomaly = TRUE
        ORDER BY commodity, created_at DESC
        """
    )
    out: list[Signal] = []
    with get_sync_session() as session:
        rows = session.execute(sql, {"as_of": as_of, "cutoff": cutoff}).all()

    for r in rows:
        scope = "national"
        domain = "price"
        magnitude = 80.0  # regime anomalies are inherently high-magnitude
        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.commodity),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of),
            calendar=calendar_fit_score(domain, as_of),
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"price-regime:{r.commodity}:{r.run_date}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{r.commodity.capitalize()} price model flagged a regime "
                    f"anomaly on {r.run_date} (driver: {r.key_driver or 'unspecified'})"
                ),
                score=score,
                direction="neutral",
                evidence={
                    "commodity": r.commodity,
                    "run_date": str(r.run_date),
                    "horizon_month": r.horizon_month,
                    "p10": float(r.p10),
                    "p50": float(r.p50),
                    "p90": float(r.p90),
                    "key_driver": r.key_driver,
                    "model_ver": r.model_ver,
                    "score_parts": parts.__dict__,
                },
                sources=["price_forecasts"],
            )
        )
    return out


def _collect_futures_moves(as_of: date) -> list[Signal]:
    """Source 8: 5-day futures settlement move > 2σ of historical 5-day moves.

    For each commodity, compute the most recent 5-day return and compare to
    the historical distribution of 5-day returns (last ~5 years).
    """
    sql = text(
        """
        WITH recent AS (
            SELECT commodity, trade_date, settlement,
                   ROW_NUMBER() OVER (PARTITION BY commodity ORDER BY trade_date DESC) AS rn
            FROM futures_daily
            WHERE trade_date <= :as_of
              AND contract_month IN (
                  SELECT contract_month FROM futures_daily f2
                  WHERE f2.commodity = futures_daily.commodity AND f2.trade_date <= :as_of
                  ORDER BY f2.trade_date DESC LIMIT 1
              )
        )
        SELECT cur.commodity, cur.trade_date AS cur_date, cur.settlement AS cur_px,
               prev.trade_date AS prev_date, prev.settlement AS prev_px
        FROM recent cur
        JOIN recent prev ON cur.commodity = prev.commodity
                        AND cur.rn = 1 AND prev.rn = 6
        WHERE prev.settlement > 0
        """
    )

    # Historical 5-day return std per commodity (5y window).
    sigma_sql = text(
        """
        WITH series AS (
            SELECT commodity, trade_date, settlement,
                   LAG(settlement, 5) OVER (
                       PARTITION BY commodity ORDER BY trade_date
                   ) AS px_5d_ago
            FROM futures_daily
            WHERE trade_date BETWEEN :start AND :as_of
        )
        SELECT commodity, STDDEV_SAMP(LN(settlement / NULLIF(px_5d_ago, 0))) AS sigma
        FROM series
        WHERE px_5d_ago > 0
        GROUP BY commodity
        """
    )

    out: list[Signal] = []
    with get_sync_session() as session:
        recent_rows = session.execute(sql, {"as_of": as_of}).all()
        sigmas = {
            r.commodity: float(r.sigma) if r.sigma else None
            for r in session.execute(
                sigma_sql,
                {"as_of": as_of, "start": as_of - timedelta(days=365 * 5)},
            ).all()
        }

    import math

    for r in recent_rows:
        sigma = sigmas.get(r.commodity)
        if not sigma or sigma <= 0:
            continue
        log_ret = math.log(float(r.cur_px) / float(r.prev_px))
        z = log_ret / sigma
        if abs(z) < FUTURES_MOVE_TRIGGER_SIGMA:
            continue

        scope = "national"
        domain = "futures"
        magnitude = min(100.0, abs(z) / 4.0 * 100)  # 4σ -> 100
        parts = ScoreParts(
            magnitude=magnitude,
            reach=reach_score(domain, scope, commodity=r.commodity),
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of),
            calendar=calendar_fit_score(domain, as_of),
        )
        score = compute_score(parts)

        pct_move = (float(r.cur_px) / float(r.prev_px) - 1) * 100
        out.append(
            Signal(
                id=f"futures-move:{r.commodity}:{r.cur_date}",
                domain=domain,
                scope=scope,
                headline=(
                    f"{r.commodity.capitalize()} front-month futures moved "
                    f"{pct_move:+.1f}% over 5 sessions ({z:+.1f}σ)"
                ),
                score=score,
                direction="positive" if z > 0 else "negative",
                evidence={
                    "commodity": r.commodity,
                    "current_date": str(r.cur_date),
                    "prior_date": str(r.prev_date),
                    "current_settlement": float(r.cur_px),
                    "prior_settlement": float(r.prev_px),
                    "pct_move_5d": round(pct_move, 2),
                    "z_score": round(z, 2),
                    "historical_sigma": round(sigma, 4),
                    "score_parts": parts.__dict__,
                },
                sources=["futures_daily"],
            )
        )
    return out
