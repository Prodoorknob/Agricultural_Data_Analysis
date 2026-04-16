"""FastAPI router for crop yield prediction endpoints.

Base path: /api/v1/predict/yield
Three endpoints:
  GET /           — Single county forecast
  GET /map        — All counties for choropleth
  GET /history    — Historical forecast vs actual
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Numeric, select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.db_tables import YieldAccuracy, YieldForecast
from backend.models.schemas import (
    YieldAccuracyWeekItem,
    YieldForecastResponse,
    YieldHistoryItem,
    YieldMapItem,
    YieldMapResponse,
)

router = APIRouter()


def _get_yield_model(request: Request, crop: str, week: int):
    """Retrieve a loaded YieldModel from app state."""
    models = getattr(request.app.state, "yield_models", {})
    return models.get((crop, week))


@router.get("/", response_model=YieldForecastResponse)
async def get_yield_forecast(
    request: Request,
    fips: str = Query(..., min_length=5, max_length=5, description="5-digit county FIPS"),
    crop: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    year: int | None = Query(None, description="Crop year (defaults to current)"),
    db: AsyncSession = Depends(get_db),
):
    """Get the latest yield forecast for a specific county and crop."""
    crop_year = year or date.today().year

    # Query the most recent forecast for this county/crop/year
    stmt = (
        select(YieldForecast)
        .where(
            YieldForecast.fips == fips,
            YieldForecast.crop == crop,
            YieldForecast.crop_year == crop_year,
        )
        .order_by(YieldForecast.week.desc(), YieldForecast.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    forecast = result.scalar_one_or_none()

    if not forecast:
        raise HTTPException(status_code=404, detail=f"No forecast for FIPS {fips}, {crop}, year {crop_year}")

    # Compute county 5-year average from historical forecasts or DB
    avg_stmt = (
        select(func.avg(YieldForecast.p50))
        .where(
            YieldForecast.fips == fips,
            YieldForecast.crop == crop,
            YieldForecast.crop_year >= crop_year - 5,
            YieldForecast.crop_year < crop_year,
            YieldForecast.week == forecast.week,
        )
    )
    avg_result = await db.execute(avg_stmt)
    county_avg = avg_result.scalar()

    vs_avg_pct = None
    if county_avg and county_avg > 0:
        vs_avg_pct = round(float((float(forecast.p50) - county_avg) / county_avg * 100), 1)

    return YieldForecastResponse(
        fips=forecast.fips,
        crop=forecast.crop,
        crop_year=forecast.crop_year,
        week=forecast.week,
        p10=float(forecast.p10),
        p50=float(forecast.p50),
        p90=float(forecast.p90),
        confidence=forecast.confidence,
        county_avg_5yr=round(float(county_avg), 1) if county_avg else None,
        vs_avg_pct=vs_avg_pct,
        model_ver=forecast.model_ver,
        last_updated=forecast.created_at.isoformat() if forecast.created_at else None,
    )


@router.get("/map", response_model=YieldMapResponse)
async def get_yield_map(
    crop: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    week: int | None = Query(None, ge=1, le=20, description="Week of season"),
    year: int | None = Query(None, description="Crop year"),
    db: AsyncSession = Depends(get_db),
):
    """Get all county forecasts for choropleth map rendering.

    Returns a lightweight array of {fips, p50, confidence, vs_avg_pct}.
    """
    crop_year = year or date.today().year

    # If week not specified, get the latest available week
    if week is None:
        max_week_stmt = (
            select(func.max(YieldForecast.week))
            .where(
                YieldForecast.crop == crop,
                YieldForecast.crop_year == crop_year,
            )
        )
        max_week_result = await db.execute(max_week_stmt)
        week = max_week_result.scalar()
        if week is None:
            raise HTTPException(status_code=404, detail=f"No forecasts for {crop} year {crop_year}")

    # Get all county forecasts for this crop/year/week (latest model version)
    # Subquery to get latest model_ver per fips
    latest_stmt = (
        select(
            YieldForecast.fips,
            func.max(YieldForecast.created_at).label("max_created"),
        )
        .where(
            YieldForecast.crop == crop,
            YieldForecast.crop_year == crop_year,
            YieldForecast.week == week,
        )
        .group_by(YieldForecast.fips)
    )
    latest = await db.execute(latest_stmt)
    latest_map = {row.fips: row.max_created for row in latest}

    if not latest_map:
        raise HTTPException(status_code=404, detail=f"No forecasts for {crop} week {week}")

    # Fetch all forecasts
    stmt = (
        select(YieldForecast)
        .where(
            YieldForecast.crop == crop,
            YieldForecast.crop_year == crop_year,
            YieldForecast.week == week,
        )
    )
    result = await db.execute(stmt)
    forecasts = result.scalars().all()

    # Deduplicate to latest per FIPS
    fips_seen = set()
    counties = []
    for f in sorted(forecasts, key=lambda x: x.created_at or x.id, reverse=True):
        if f.fips in fips_seen:
            continue
        fips_seen.add(f.fips)

        counties.append(YieldMapItem(
            fips=f.fips,
            p50=float(f.p50),
            confidence=f.confidence,
            vs_avg_pct=None,  # Computed client-side or via separate call for performance
        ))

    return YieldMapResponse(
        crop=crop,
        crop_year=crop_year,
        week=week,
        counties=counties,
    )


@router.get("/history", response_model=list[YieldHistoryItem])
async def get_yield_history(
    fips: str = Query(..., min_length=5, max_length=5),
    crop: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    start_year: int = Query(2015, description="First year to include"),
    db: AsyncSession = Depends(get_db),
):
    """Get historical forecast vs actual yield for a county.

    Returns forecast p50 at the latest available week per crop year,
    alongside actual realized yield where available.
    """
    # Get the best (latest week) forecast per year
    stmt = (
        select(YieldForecast)
        .where(
            YieldForecast.fips == fips,
            YieldForecast.crop == crop,
            YieldForecast.crop_year >= start_year,
        )
        .order_by(YieldForecast.crop_year, YieldForecast.week.desc())
    )
    result = await db.execute(stmt)
    all_forecasts = result.scalars().all()

    # Keep only the latest-week forecast per year
    best_per_year: dict[int, YieldForecast] = {}
    for f in all_forecasts:
        if f.crop_year not in best_per_year or f.week > best_per_year[f.crop_year].week:
            best_per_year[f.crop_year] = f

    history = []
    for year in sorted(best_per_year.keys()):
        f = best_per_year[year]
        history.append(YieldHistoryItem(
            crop_year=year,
            week=f.week,
            p50_forecast=float(f.p50),
            actual_yield=None,  # Would come from NASS realized yield data
            error_pct=None,
        ))

    return history


@router.get("/accuracy", response_model=list[YieldAccuracyWeekItem])
async def get_yield_accuracy(
    crop: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    split: str = Query("test", pattern="^(val|test)$", description="Walk-forward split"),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated yield accuracy by week for the accuracy panel (§5.3.D).

    Returns average pct_error, coverage (fraction in interval), and baseline RRMSE
    per week across all counties and forecast years for the given crop.
    """
    stmt = (
        select(
            YieldAccuracy.week,
            func.avg(func.abs(YieldAccuracy.pct_error)).label("avg_pct_error"),
            func.avg(
                case((YieldAccuracy.in_interval == True, 1), else_=0)
            ).label("avg_coverage"),
            func.avg(
                func.abs(
                    (YieldAccuracy.actual_yield - YieldAccuracy.county_5yr_mean)
                    / func.nullif(YieldAccuracy.actual_yield, 0)
                    * 100
                )
            ).label("baseline_rrmse"),
            func.count().label("n_counties"),
        )
        .where(
            YieldAccuracy.crop == crop,
            YieldAccuracy.split == split,
            YieldAccuracy.actual_yield.isnot(None),
            YieldAccuracy.pct_error.isnot(None),
        )
        .group_by(YieldAccuracy.week)
        .order_by(YieldAccuracy.week)
    )
    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No yield accuracy data for {crop}")

    return [
        YieldAccuracyWeekItem(
            crop=crop,
            week=row.week,
            avg_pct_error=round(float(row.avg_pct_error), 2) if row.avg_pct_error else None,
            avg_coverage=round(float(row.avg_coverage), 3) if row.avg_coverage else None,
            baseline_rrmse=round(float(row.baseline_rrmse), 2) if row.baseline_rrmse else None,
            n_counties=row.n_counties,
        )
        for row in rows
    ]
