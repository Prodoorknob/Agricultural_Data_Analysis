import asyncio
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from backend.database import get_db
from backend.models.db_tables import FuturesDaily, PriceForecast, WasdeRelease
from backend.models.schemas import (
    PriceForecastResponse,
    ProbabilityResponse,
    WasdeSignalResponse,
    PriceForecastHistoryItem,
)

router = APIRouter()


def _get_ensemble(request: Request, commodity: str, horizon_months: int):
    """Retrieve a loaded ensemble model or raise 503 if unavailable."""
    models = getattr(request.app.state, "models", {})
    key = (commodity, horizon_months)
    ensemble = models.get(key)
    if ensemble is None:
        raise HTTPException(
            status_code=503,
            detail=f"Model not available for {commodity} horizon={horizon_months}. "
            f"Loaded models: {list(models.keys())}",
        )
    return ensemble


def _build_features_sync(commodity: str, horizon_months: int):
    """Build feature row for inference. Synchronous (psycopg2 DB queries)."""
    from backend.features.price_features import build_price_features

    return build_price_features(commodity, date.today(), horizon_months)


async def _build_features(commodity: str, horizon_months: int):
    """Async wrapper — offloads the sync DB work to a threadpool so the
    uvicorn event loop stays responsive during feature construction."""
    return await asyncio.to_thread(_build_features_sync, commodity, horizon_months)


def _horizon_month_str(horizon_months: int) -> str:
    """Compute the target YYYY-MM string from today + horizon offset."""
    import pandas as pd

    target = pd.Timestamp.today() + pd.DateOffset(months=horizon_months)
    return target.strftime("%Y-%m")


@router.get("/", response_model=PriceForecastResponse)
async def get_price_forecast(
    request: Request,
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    horizon_months: int = Query(default=3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    ensemble = _get_ensemble(request, commodity, horizon_months)

    try:
        features = await _build_features(commodity, horizon_months)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Feature build failed: {exc}")

    result = ensemble.predict(features)
    horizon_month = _horizon_month_str(horizon_months)

    # Persist forecast to DB (upsert)
    forecast_row = PriceForecast(
        run_date=date.today(),
        commodity=commodity,
        horizon_month=horizon_month,
        p10=result["p10"],
        p50=result["p50"],
        p90=result["p90"],
        key_driver=result["key_driver"],
        divergence_flag=result["divergence_flag"],
        regime_anomaly=result["regime_anomaly"],
        model_ver=result["model_ver"],
    )

    # Check if a forecast already exists for today
    existing = await db.execute(
        select(PriceForecast).where(
            PriceForecast.run_date == date.today(),
            PriceForecast.commodity == commodity,
            PriceForecast.horizon_month == horizon_month,
            PriceForecast.model_ver == result["model_ver"],
        )
    )
    row = existing.scalar()
    if row:
        row.p10, row.p50, row.p90 = result["p10"], result["p50"], result["p90"]
        row.key_driver = result["key_driver"]
        row.divergence_flag = result["divergence_flag"]
        row.regime_anomaly = result["regime_anomaly"]
    else:
        db.add(forecast_row)

    return PriceForecastResponse(
        commodity=commodity,
        run_date=date.today(),
        horizon_month=horizon_month,
        p10=result["p10"],
        p50=result["p50"],
        p90=result["p90"],
        key_driver=result["key_driver"],
        divergence_flag=result["divergence_flag"],
        regime_anomaly=result["regime_anomaly"],
        model_ver=result["model_ver"],
    )


@router.get("/probability", response_model=ProbabilityResponse)
async def get_price_probability(
    request: Request,
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    threshold_price: float = Query(..., gt=0),
    horizon_months: int = Query(default=3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    ensemble = _get_ensemble(request, commodity, horizon_months)

    try:
        features = await _build_features(commodity, horizon_months)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Feature build failed: {exc}")

    probability = ensemble.predict_probability(features, threshold_price)

    return ProbabilityResponse(
        commodity=commodity,
        threshold_price=threshold_price,
        horizon_month=_horizon_month_str(horizon_months),
        probability=round(probability, 4),
    )


@router.get("/wasde-signal", response_model=WasdeSignalResponse)
async def get_wasde_signal(
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    db: AsyncSession = Depends(get_db),
):
    # Get the two most recent WASDE releases for this commodity
    result = await db.execute(
        select(WasdeRelease)
        .where(WasdeRelease.commodity == commodity)
        .where(WasdeRelease.stocks_to_use.isnot(None))
        .order_by(WasdeRelease.release_date.desc())
        .limit(2)
    )
    releases = result.scalars().all()

    if not releases:
        raise HTTPException(status_code=404, detail=f"No WASDE data found for {commodity}")

    current = releases[0]
    prior = releases[1] if len(releases) > 1 else None

    stu = float(current.stocks_to_use)
    prior_stu = float(prior.stocks_to_use) if prior and prior.stocks_to_use else None

    # Compute surprise
    surprise = None
    surprise_direction = None
    if prior_stu is not None:
        surprise = round(stu - prior_stu, 4)
        if surprise > 0.02:
            surprise_direction = "bearish"
        elif surprise < -0.02:
            surprise_direction = "bullish"
        else:
            surprise_direction = "neutral"

    # Compute percentile against all history
    all_stu_result = await db.execute(
        select(WasdeRelease.stocks_to_use)
        .where(WasdeRelease.commodity == commodity)
        .where(WasdeRelease.stocks_to_use.isnot(None))
    )
    all_stu = [float(v) for v in all_stu_result.scalars().all()]
    pctile = int(sum(1 for v in all_stu if v <= stu) / len(all_stu) * 100) if all_stu else 50

    # Historical context
    if pctile <= 15:
        context = f"Stocks-to-use at {pctile}th percentile — historically tight supply"
    elif pctile >= 85:
        context = f"Stocks-to-use at {pctile}th percentile — historically ample supply"
    else:
        context = f"Stocks-to-use at {pctile}th percentile — within normal range"

    return WasdeSignalResponse(
        commodity=commodity,
        release_date=current.release_date,
        stocks_to_use=stu,
        stocks_to_use_pctile=pctile,
        prior_month_stu=prior_stu,
        surprise=surprise,
        surprise_direction=surprise_direction,
        historical_context=context,
    )


@router.get("/history", response_model=list[PriceForecastHistoryItem])
async def get_price_history(
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    horizon_months: int = Query(default=3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    # Get all past forecasts
    result = await db.execute(
        select(PriceForecast)
        .where(PriceForecast.commodity == commodity)
        .order_by(PriceForecast.run_date.desc())
        .limit(100)
    )
    forecasts = result.scalars().all()

    items: list[PriceForecastHistoryItem] = []
    for fc in forecasts:
        # Look up actual realized price from futures_daily at the horizon month
        actual = None
        error_pct = None

        actual_result = await db.execute(
            select(FuturesDaily.settlement)
            .where(FuturesDaily.commodity == commodity)
            .where(func.to_char(FuturesDaily.trade_date, "YYYY-MM") == fc.horizon_month)
            .order_by(FuturesDaily.trade_date.desc())
            .limit(1)
        )
        actual_row = actual_result.scalar()
        if actual_row is not None:
            # futures_daily.settlement is stored in cents/bu; forecasts are $/bu
            actual = round(float(actual_row) / 100.0, 4)
            if float(fc.p50) != 0:
                error_pct = round((actual - float(fc.p50)) / float(fc.p50) * 100, 2)

        items.append(
            PriceForecastHistoryItem(
                run_date=fc.run_date,
                horizon_month=fc.horizon_month,
                p50=float(fc.p50),
                actual=actual,
                error_pct=error_pct,
            )
        )

    return items
