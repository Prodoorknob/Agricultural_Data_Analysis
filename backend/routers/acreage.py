"""API router for planted acreage predictions (Module 03).

Endpoints:
  GET /                 - National or state-level forecast
  GET /states           - All state forecasts for a commodity/year
  GET /accuracy         - Historical accuracy vs USDA
  GET /price-ratio      - Corn/soy ratio with historical context
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.features.acreage_features import FIPS_TO_STATE
from backend.models.schemas import (
    AcreageAccuracyItem,
    AcreageForecastResponse,
    PriceRatioResponse,
    StateAcreageItem,
    StatesAcreageResponse,
)

router = APIRouter()


def _get_acreage_ensemble(request: Request, commodity: str):
    """Retrieve loaded AcreageEnsemble from app state."""
    models = getattr(request.app.state, "acreage_models", {})
    ensemble = models.get(commodity)
    if ensemble is None:
        raise HTTPException(
            status_code=503,
            detail=f"Acreage model for {commodity} not loaded. Retrain or check artifacts.",
        )
    return ensemble


@router.get("/", response_model=AcreageForecastResponse)
async def get_acreage_forecast(
    request: Request,
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    year: Optional[int] = Query(default=None),
    level: str = Query(default="national", pattern="^(national|state)$"),
    state_fips: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Get planted acreage forecast (national or state-level)."""
    from backend.models.db_tables import AcreageForecast

    if year is None:
        year = date.today().year

    if level == "state" and state_fips is None:
        raise HTTPException(400, "state_fips required when level=state")

    target_fips = state_fips if level == "state" else "00"

    # Query existing forecast from DB
    stmt = (
        select(AcreageForecast)
        .where(
            AcreageForecast.forecast_year == year,
            AcreageForecast.state_fips == target_fips,
            AcreageForecast.commodity == commodity,
        )
        .order_by(AcreageForecast.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            404,
            f"No acreage forecast found for {commodity} {year} (fips={target_fips}). "
            "Run inference first.",
        )

    # Compute vs prior year
    stmt_prior = (
        select(AcreageForecast.forecast_acres)
        .where(
            AcreageForecast.forecast_year == year - 1,
            AcreageForecast.state_fips == target_fips,
            AcreageForecast.commodity == commodity,
        )
        .order_by(AcreageForecast.created_at.desc())
        .limit(1)
    )
    prior = await db.execute(stmt_prior)
    prior_acres = prior.scalar_one_or_none()

    vs_prior = None
    if prior_acres and float(prior_acres) > 0:
        vs_prior = round(
            (float(row.forecast_acres) - float(prior_acres)) / float(prior_acres) * 100, 1
        )

    # Corn/soy ratio percentile (from futures_daily historical data)
    ratio_pctile = None
    if row.corn_soy_ratio:
        try:
            pctile_stmt = text("""
                SELECT COUNT(*) FILTER (WHERE ratio <= :current_ratio) * 100 / NULLIF(COUNT(*), 0)
                FROM (
                    SELECT c.settlement / NULLIF(s.settlement, 0) AS ratio
                    FROM futures_daily c
                    JOIN futures_daily s ON c.trade_date = s.trade_date
                    WHERE c.commodity = 'corn' AND s.commodity = 'soybean'
                      AND c.trade_date >= '2000-01-01'
                      AND EXTRACT(MONTH FROM c.trade_date) = 11
                ) sub
            """)
            pctile_result = await db.execute(pctile_stmt, {"current_ratio": float(row.corn_soy_ratio)})
            ratio_pctile = pctile_result.scalar_one_or_none()
            if ratio_pctile is not None:
                ratio_pctile = int(ratio_pctile)
        except Exception:
            pass

    return AcreageForecastResponse(
        commodity=commodity,
        forecast_year=year,
        level=level,
        state_fips=target_fips if level == "state" else None,
        state_name=FIPS_TO_STATE.get(target_fips) if level == "state" else None,
        forecast_acres=float(row.forecast_acres),
        p10_acres=float(row.p10_acres) if row.p10_acres else None,
        p90_acres=float(row.p90_acres) if row.p90_acres else None,
        corn_soy_ratio=float(row.corn_soy_ratio) if row.corn_soy_ratio else None,
        corn_soy_ratio_pctile=ratio_pctile,
        key_driver=row.key_driver,
        vs_prior_year_pct=vs_prior,
        published_at=row.published_at,
        model_ver=row.model_ver,
    )


@router.get("/states", response_model=StatesAcreageResponse)
async def get_states_forecast(
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    year: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Get all state-level forecasts for a commodity/year.

    The unique constraint on acreage_forecasts is (year, state_fips,
    commodity, model_ver) — re-running inference with a bumped model_ver
    appends rather than replaces, so a state can legitimately have multiple
    rows. Dedupe here to the latest created_at per state.
    """
    from backend.models.db_tables import AcreageForecast

    if year is None:
        year = date.today().year

    stmt = (
        select(AcreageForecast)
        .where(
            AcreageForecast.forecast_year == year,
            AcreageForecast.commodity == commodity,
            AcreageForecast.state_fips != "00",  # exclude national
        )
        .order_by(AcreageForecast.state_fips, AcreageForecast.created_at.desc())
    )
    result = await db.execute(stmt)
    all_rows = result.scalars().all()

    if not all_rows:
        raise HTTPException(404, f"No state forecasts for {commodity} {year}")

    # Keep only the most recent forecast per state_fips
    seen: set[str] = set()
    rows = []
    for r in all_rows:
        if r.state_fips in seen:
            continue
        seen.add(r.state_fips)
        rows.append(r)
    rows.sort(key=lambda r: float(r.forecast_acres), reverse=True)

    # Get prior year (dedupe the same way)
    stmt_prior = (
        select(AcreageForecast)
        .where(
            AcreageForecast.forecast_year == year - 1,
            AcreageForecast.commodity == commodity,
            AcreageForecast.state_fips != "00",
        )
        .order_by(AcreageForecast.state_fips, AcreageForecast.created_at.desc())
    )
    prior_result = await db.execute(stmt_prior)
    prior_map: dict[str, float] = {}
    for r in prior_result.scalars().all():
        if r.state_fips not in prior_map:
            prior_map[r.state_fips] = float(r.forecast_acres)

    states = []
    for row in rows:
        fips = row.state_fips
        acres = float(row.forecast_acres)
        prior = prior_map.get(fips)
        vs_prior = round((acres - prior) / prior * 100, 1) if prior and prior > 0 else None

        states.append(StateAcreageItem(
            state_fips=fips,
            state=FIPS_TO_STATE.get(fips, f"FIPS {fips}"),
            forecast_acres=acres,
            vs_prior_pct=vs_prior,
        ))

    return StatesAcreageResponse(
        commodity=commodity,
        forecast_year=year,
        states=states,
    )


@router.get("/accuracy", response_model=list[AcreageAccuracyItem])
async def get_accuracy(
    commodity: Optional[str] = Query(default=None, pattern="^(corn|soybean|wheat)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get historical model accuracy vs USDA reports."""
    from backend.models.db_tables import AcreageAccuracy

    stmt = select(AcreageAccuracy).order_by(AcreageAccuracy.forecast_year.desc())
    if commodity:
        stmt = stmt.where(AcreageAccuracy.commodity == commodity)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        AcreageAccuracyItem(
            forecast_year=r.forecast_year,
            commodity=r.commodity,
            level="national" if r.state_fips == "00" else "state",
            model_forecast=float(r.model_forecast) if r.model_forecast is not None else None,
            usda_prospective=float(r.usda_prospective) if r.usda_prospective is not None else None,
            usda_june_actual=float(r.usda_june_actual) if r.usda_june_actual is not None else None,
            model_vs_usda_pct=float(r.model_vs_usda_pct) if r.model_vs_usda_pct is not None else None,
            model_vs_actual_pct=float(r.model_vs_actual_pct) if r.model_vs_actual_pct is not None else None,
        )
        for r in rows
    ]


@router.get("/price-ratio", response_model=PriceRatioResponse)
async def get_price_ratio(
    db: AsyncSession = Depends(get_db),
):
    """Get current corn/soy price ratio with historical context."""
    # Get most recent corn December and soybean November futures
    corn_stmt = text("""
        SELECT trade_date, settlement FROM futures_daily
        WHERE commodity = 'corn'
        ORDER BY trade_date DESC LIMIT 1
    """)
    soy_stmt = text("""
        SELECT trade_date, settlement FROM futures_daily
        WHERE commodity = 'soybean'
        ORDER BY trade_date DESC LIMIT 1
    """)

    corn_result = await db.execute(corn_stmt)
    soy_result = await db.execute(soy_stmt)

    corn_row = corn_result.fetchone()
    soy_row = soy_result.fetchone()

    if not corn_row or not soy_row:
        raise HTTPException(404, "No futures data available to compute price ratio")

    corn_price = float(corn_row[1])
    soy_price = float(soy_row[1])
    as_of = corn_row[0]

    ratio = corn_price / soy_price if soy_price > 0 else None

    # Historical percentile
    percentile = None
    context = None
    implication = None

    if ratio is not None:
        pctile_stmt = text("""
            SELECT COUNT(*) FILTER (WHERE sub.ratio <= :ratio) * 100 / NULLIF(COUNT(*), 0)
            FROM (
                SELECT c.settlement / NULLIF(s.settlement, 0) AS ratio
                FROM futures_daily c
                JOIN futures_daily s ON c.trade_date = s.trade_date
                WHERE c.commodity = 'corn' AND s.commodity = 'soybean'
                  AND c.trade_date >= '2000-01-01'
            ) sub
        """)
        pctile_result = await db.execute(pctile_stmt, {"ratio": ratio})
        percentile = pctile_result.scalar_one_or_none()
        if percentile is not None:
            percentile = int(percentile)

        # Interpretation
        if ratio < 2.2:
            implication = "soy_favored"
            context = (
                f"A ratio of {ratio:.2f} is below the soybean-shift threshold. "
                "Ratios below 2.2 have historically shifted 2-4M acres toward soybeans."
            )
        elif ratio > 2.5:
            implication = "corn_favored"
            context = (
                f"A ratio of {ratio:.2f} favors corn planting. "
                "Ratios above 2.5 have historically pulled acres toward corn."
            )
        else:
            implication = "neutral"
            context = (
                f"A ratio of {ratio:.2f} is in the neutral zone. "
                "Planting decisions likely driven by input costs and rotation."
            )

    return PriceRatioResponse(
        as_of_date=as_of,
        corn_dec_futures=corn_price,
        soy_nov_futures=soy_price,
        corn_soy_ratio=round(ratio, 4) if ratio else None,
        historical_percentile=percentile,
        historical_context=context,
        implication=implication,
    )
