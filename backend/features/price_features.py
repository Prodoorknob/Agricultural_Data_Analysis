"""Feature engineering for commodity price forecasting.

Builds a single-row feature DataFrame for a given (commodity, as_of_date, horizon_months)
tuple by querying RDS tables populated by the ETL scripts (Steps 1-4).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import pandera as pa
from pandera import Check, Column, DataFrameSchema
from sqlalchemy import func, select

from backend.etl.common import get_sync_session, setup_logging
from backend.models.db_tables import (
    DxyDaily,
    ErsProductionCost,
    FuturesDaily,
    WasdeRelease,
)

logger = setup_logging("price_features")

VALID_COMMODITIES = ("corn", "soybean", "wheat")
VALID_HORIZONS = (1, 2, 3, 4, 5, 6)

# CME futures settlements are stored in cents/bushel; divide by this to get $/bu.
_CENTS_TO_DOLLARS = 100.0

# ---------------------------------------------------------------------------
# Pandera validation schema
# ---------------------------------------------------------------------------

PriceFeatureSchema = DataFrameSchema(
    {
        "commodity": Column(str, Check.isin(list(VALID_COMMODITIES))),
        "as_of_date": Column("datetime64[ns]"),
        "horizon_months": Column(int, Check.isin(list(VALID_HORIZONS))),
        "futures_spot": Column(float, [Check.gt(0), Check.le(25)], nullable=True),
        "futures_deferred": Column(float, [Check.gt(0), Check.le(25)], nullable=True),
        "basis": Column(float, nullable=True),
        "term_spread": Column(float, nullable=True),
        "open_interest_chg": Column(float, nullable=True),
        "stocks_to_use": Column(float, [Check.ge(0), Check.le(1)], nullable=True),
        "stocks_to_use_pctile": Column(float, [Check.ge(0), Check.le(100)], nullable=True),
        "wasde_surprise": Column(float, nullable=True),
        "world_stocks_to_use": Column(float, [Check.ge(0), Check.le(1)], nullable=True),
        "dxy": Column(float, [Check.gt(50), Check.lt(200)], nullable=True),
        "dxy_chg_30d": Column(float, nullable=True),
        "production_cost_bu": Column(float, Check.gt(0), nullable=True),
        "price_cost_ratio": Column(float, Check.gt(0), nullable=True),
        "corn_soy_ratio": Column(float, nullable=True),
        "prior_year_price": Column(float, Check.gt(0), nullable=True),
        "seasonal_factor": Column(float, nullable=True),
    },
    coerce=True,
)

# ---------------------------------------------------------------------------
# Helper: database queries
# ---------------------------------------------------------------------------


def _get_nearest_futures(
    session, commodity: str, as_of_date: date
) -> Optional[tuple[float, int | None]]:
    """Return (settlement, open_interest) for the nearest active contract."""
    row = session.execute(
        select(FuturesDaily.settlement, FuturesDaily.open_interest)
        .where(FuturesDaily.commodity == commodity)
        .where(FuturesDaily.trade_date <= as_of_date)
        .where(FuturesDaily.contract_month >= as_of_date.strftime("%Y-%m"))
        .order_by(FuturesDaily.contract_month.asc(), FuturesDaily.trade_date.desc())
        .limit(1)
    ).first()
    if row is None:
        # Fallback: most recent settlement regardless of contract month
        row = session.execute(
            select(FuturesDaily.settlement, FuturesDaily.open_interest)
            .where(FuturesDaily.commodity == commodity)
            .where(FuturesDaily.trade_date <= as_of_date)
            .order_by(FuturesDaily.trade_date.desc())
            .limit(1)
        ).first()
    return (float(row[0]) / _CENTS_TO_DOLLARS, row[1]) if row else None


def _get_deferred_futures(
    session, commodity: str, as_of_date: date, months_ahead: int = 6
) -> Optional[float]:
    """Return settlement for the deferred contract (~6 months out), in $/bu."""
    target_month = as_of_date + timedelta(days=months_ahead * 30)
    target_ym = target_month.strftime("%Y-%m")
    row = session.execute(
        select(FuturesDaily.settlement)
        .where(FuturesDaily.commodity == commodity)
        .where(FuturesDaily.trade_date <= as_of_date)
        .where(FuturesDaily.contract_month >= target_ym)
        .order_by(FuturesDaily.contract_month.asc(), FuturesDaily.trade_date.desc())
        .limit(1)
    ).first()
    if row is None:
        # Fallback: accept any contract beyond as_of even if < target (sparse wheat months)
        row = session.execute(
            select(FuturesDaily.settlement)
            .where(FuturesDaily.commodity == commodity)
            .where(FuturesDaily.trade_date <= as_of_date)
            .where(FuturesDaily.contract_month > as_of_date.strftime("%Y-%m"))
            .order_by(FuturesDaily.contract_month.desc(), FuturesDaily.trade_date.desc())
            .limit(1)
        ).first()
    return float(row[0]) / _CENTS_TO_DOLLARS if row else None


def _get_open_interest_change(
    session, commodity: str, as_of_date: date, lookback_days: int = 30
) -> Optional[float]:
    """Return change in open interest over the lookback window."""
    cutoff = as_of_date - timedelta(days=lookback_days)

    def _oi_near(d: date) -> Optional[int]:
        row = session.execute(
            select(FuturesDaily.open_interest)
            .where(FuturesDaily.commodity == commodity)
            .where(FuturesDaily.trade_date <= d)
            .where(FuturesDaily.open_interest.isnot(None))
            .order_by(FuturesDaily.trade_date.desc())
            .limit(1)
        ).first()
        return int(row[0]) if row else None

    oi_now = _oi_near(as_of_date)
    oi_past = _oi_near(cutoff)
    if oi_now is not None and oi_past is not None:
        return float(oi_now - oi_past)
    return None


def _get_latest_wasde(
    session, commodity: str, as_of_date: date
) -> Optional[WasdeRelease]:
    """Return the most recent WASDE row for commodity on or before as_of_date."""
    row = session.execute(
        select(WasdeRelease)
        .where(WasdeRelease.commodity == commodity)
        .where(WasdeRelease.release_date <= as_of_date)
        .order_by(WasdeRelease.release_date.desc())
        .limit(1)
    ).scalar()
    return row


def _compute_wasde_surprise(
    session, commodity: str, as_of_date: date
) -> Optional[float]:
    """Stocks-to-use change from prior WASDE to current. Negative = bullish."""
    current = _get_latest_wasde(session, commodity, as_of_date)
    if current is None or current.stocks_to_use is None:
        return None
    # Get the prior month's release
    prior_cutoff = current.release_date - timedelta(days=5)
    prior = _get_latest_wasde(session, commodity, prior_cutoff)
    if prior is None or prior.stocks_to_use is None:
        return 0.0
    return float(current.stocks_to_use) - float(prior.stocks_to_use)


def _get_stocks_to_use_percentile(
    session, commodity: str, current_stu: float
) -> Optional[float]:
    """Historical percentile rank of current STU vs. all history for commodity."""
    rows = session.execute(
        select(WasdeRelease.stocks_to_use)
        .where(WasdeRelease.commodity == commodity)
        .where(WasdeRelease.stocks_to_use.isnot(None))
    ).scalars().all()
    if not rows:
        return None
    historical = [float(v) for v in rows]
    pctile = sum(1 for v in historical if v <= current_stu) / len(historical) * 100
    return round(pctile, 1)


def _get_dxy(session, as_of_date: date) -> Optional[float]:
    """Return most recent DXY value on or before as_of_date."""
    row = session.execute(
        select(DxyDaily.dxy)
        .where(DxyDaily.trade_date <= as_of_date)
        .order_by(DxyDaily.trade_date.desc())
        .limit(1)
    ).first()
    return float(row[0]) if row else None


def _get_dxy_change(session, as_of_date: date, days: int = 30) -> Optional[float]:
    """30-day change in DXY."""
    dxy_now = _get_dxy(session, as_of_date)
    dxy_past = _get_dxy(session, as_of_date - timedelta(days=days))
    if dxy_now is not None and dxy_past is not None:
        return dxy_now - dxy_past
    return None


def _get_production_cost(
    session, commodity: str, year: int
) -> Optional[float]:
    """Return total cost per bushel for the given commodity and year."""
    row = session.execute(
        select(ErsProductionCost.total_cost_per_bu)
        .where(ErsProductionCost.commodity == commodity)
        .where(ErsProductionCost.year <= year)
        .order_by(ErsProductionCost.year.desc())
        .limit(1)
    ).first()
    return float(row[0]) if row else None


def _get_historical_price(
    session, commodity: str, target_date: date
) -> Optional[float]:
    """Return settlement price closest to target_date (within 7 days), in $/bu."""
    window_start = target_date - timedelta(days=7)
    row = session.execute(
        select(FuturesDaily.settlement)
        .where(FuturesDaily.commodity == commodity)
        .where(FuturesDaily.trade_date >= window_start)
        .where(FuturesDaily.trade_date <= target_date)
        .order_by(FuturesDaily.trade_date.desc())
        .limit(1)
    ).first()
    return float(row[0]) / _CENTS_TO_DOLLARS if row else None


def _compute_seasonal_factor(
    session, commodity: str, month: int
) -> Optional[float]:
    """Ratio of average price in `month` to overall average price."""
    all_avg = session.execute(
        select(func.avg(FuturesDaily.settlement))
        .where(FuturesDaily.commodity == commodity)
    ).scalar()
    month_avg = session.execute(
        select(func.avg(FuturesDaily.settlement))
        .where(FuturesDaily.commodity == commodity)
        .where(func.extract("month", FuturesDaily.trade_date) == month)
    ).scalar()
    if all_avg and month_avg and float(all_avg) > 0:
        return float(month_avg) / float(all_avg)
    return None


def _get_corn_soy_ratio(
    session, as_of_date: date
) -> Optional[float]:
    """Corn/soybean price ratio from nearest futures."""
    corn = _get_nearest_futures(session, "corn", as_of_date)
    soy = _get_nearest_futures(session, "soybean", as_of_date)
    if corn and soy and soy[0] > 0:
        return corn[0] / soy[0]
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def build_price_features(
    commodity: str,
    as_of_date: date,
    horizon_months: int,
) -> pd.DataFrame:
    """Build a single-row feature DataFrame for model input.

    Parameters
    ----------
    commodity : str
        One of "corn", "soybean", "wheat".
    as_of_date : date
        Point-in-time cutoff (no future data leakage).
    horizon_months : int
        Forecast horizon (1–6 months).

    Returns
    -------
    pd.DataFrame
        Single-row DataFrame with 18+ numeric features, validated by Pandera.
    """
    if commodity not in VALID_COMMODITIES:
        raise ValueError(f"commodity must be one of {VALID_COMMODITIES}, got {commodity!r}")
    if horizon_months not in VALID_HORIZONS:
        raise ValueError(f"horizon_months must be one of {VALID_HORIZONS}, got {horizon_months}")

    session = get_sync_session()
    missing: list[str] = []

    try:
        # --- Market features ---
        futures_result = _get_nearest_futures(session, commodity, as_of_date)
        futures_spot = futures_result[0] if futures_result else None
        open_interest = futures_result[1] if futures_result else None
        if futures_spot is None:
            missing.append("futures_spot")

        futures_deferred = _get_deferred_futures(session, commodity, as_of_date)
        if futures_deferred is None:
            missing.append("futures_deferred")

        # Basis: spot futures minus cash. MVP uses spot as proxy for cash.
        basis = 0.0  # No separate cash price source in MVP

        term_spread = None
        if futures_spot is not None and futures_deferred is not None:
            term_spread = futures_deferred - futures_spot

        oi_chg = _get_open_interest_change(session, commodity, as_of_date)

        # --- Fundamental features ---
        wasde = _get_latest_wasde(session, commodity, as_of_date)
        stu = float(wasde.stocks_to_use) if wasde and wasde.stocks_to_use else None
        world_stu = None  # world_stocks_to_use not in current schema; derive if possible
        if wasde:
            # Approximate world STU from available fields if possible
            if wasde.world_production and wasde.ending_stocks:
                world_stu = float(wasde.ending_stocks) / float(wasde.world_production)

        stu_pctile = None
        if stu is not None:
            stu_pctile = _get_stocks_to_use_percentile(session, commodity, stu)

        wasde_surprise = _compute_wasde_surprise(session, commodity, as_of_date)

        # --- Macro features ---
        dxy = _get_dxy(session, as_of_date)
        dxy_chg = _get_dxy_change(session, as_of_date)

        # --- Cost features ---
        prod_cost = _get_production_cost(session, commodity, as_of_date.year)
        price_cost_ratio = None
        if futures_spot is not None and prod_cost is not None and prod_cost > 0:
            price_cost_ratio = futures_spot / prod_cost

        # --- Interaction features ---
        corn_soy_ratio = None
        if commodity in ("corn", "soybean"):
            corn_soy_ratio = _get_corn_soy_ratio(session, as_of_date)

        # --- Seasonal / mean-reversion ---
        prior_year_price = _get_historical_price(
            session, commodity, as_of_date - timedelta(days=365)
        )
        seasonal_factor = _compute_seasonal_factor(
            session, commodity, as_of_date.month
        )

    finally:
        session.close()

    if missing:
        logger.warning(
            "Missing features for %s as_of=%s: %s", commodity, as_of_date, ", ".join(missing)
        )

    # --- Assemble row ---
    row = {
        "commodity": commodity,
        "as_of_date": pd.Timestamp(as_of_date),
        "horizon_months": horizon_months,
        "futures_spot": futures_spot,
        "futures_deferred": futures_deferred,
        "basis": basis,
        "term_spread": term_spread,
        "open_interest_chg": oi_chg,
        "stocks_to_use": stu,
        "stocks_to_use_pctile": stu_pctile,
        "wasde_surprise": wasde_surprise,
        "world_stocks_to_use": world_stu,
        "dxy": dxy,
        "dxy_chg_30d": dxy_chg,
        "production_cost_bu": prod_cost,
        "price_cost_ratio": price_cost_ratio,
        "corn_soy_ratio": corn_soy_ratio,
        "prior_year_price": prior_year_price,
        "seasonal_factor": seasonal_factor,
    }

    df = pd.DataFrame([row])

    # Validate — allow nullable columns to pass through
    try:
        df = PriceFeatureSchema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        logger.error("Pandera validation failed:\n%s", exc.failure_cases)
        raise

    logger.info(
        "Built features: commodity=%s, as_of=%s, horizon=%d, nulls=%d/%d",
        commodity,
        as_of_date,
        horizon_months,
        df.iloc[0].isna().sum(),
        len(df.columns),
    )
    return df


def build_training_features(
    commodity: str,
    start_date: date,
    end_date: date,
    horizon_months: int,
    freq_days: int = 30,
) -> pd.DataFrame:
    """Build feature matrix for model training over a date range.

    Parameters
    ----------
    commodity : str
        One of "corn", "soybean", "wheat".
    start_date, end_date : date
        Training window boundaries.
    horizon_months : int
        Forecast horizon (1–6).
    freq_days : int
        How often to sample feature snapshots (default: monthly).

    Returns
    -------
    pd.DataFrame
        Multi-row DataFrame with one feature row per sample date.
    """
    frames: list[pd.DataFrame] = []
    current = start_date
    while current <= end_date:
        try:
            row = build_price_features(commodity, current, horizon_months)
            frames.append(row)
        except Exception:
            logger.warning("Skipping %s for %s (feature build failed)", current, commodity)
        current += timedelta(days=freq_days)

    if not frames:
        raise ValueError(f"No features built for {commodity} between {start_date} and {end_date}")

    result = pd.concat(frames, ignore_index=True)
    logger.info(
        "Training features: commodity=%s, rows=%d, horizon=%d",
        commodity, len(result), horizon_months,
    )
    return result
