"""FastAPI router for market data endpoints.

Base path: /api/v1/market
Five read-only endpoints serving futures, forward curve, DXY, production costs,
and fertilizer prices. No ML — pure database reads.

Spec reference: frontend-spec-v1.md §2.10, §5.2
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.db_tables import (
    DxyDaily,
    ErsFertilizerPrice,
    ErsProductionCost,
    ExportCommitment,
    FuturesDaily,
)
from backend.routers.deps import commodity_param
from backend.models.schemas import (
    DxyPoint,
    DxyTimeSeriesResponse,
    ExportPaceResponse,
    FertilizerPriceResponse,
    ForwardCurvePoint,
    ForwardCurveResponse,
    FuturesPoint,
    FuturesTimeSeriesResponse,
    ProductionCostResponse,
)

router = APIRouter()


def _nearby_contract_filter(commodity: str, trade_date: date) -> str:
    """Determine the nearby (front-month) contract month for a given date.

    Simple heuristic: the nearest contract_month >= current month that has data.
    We rely on the query to find the actual nearest by sorting.
    """
    return trade_date.strftime("%Y-%m")


@router.get("/futures", response_model=FuturesTimeSeriesResponse)
async def get_futures_time_series(
    commodity: str = Depends(commodity_param),
    start: str | None = Query(None, description="ISO date, e.g. 2025-01-01"),
    end: str | None = Query(None, description="ISO date, e.g. 2026-04-15"),
    db: AsyncSession = Depends(get_db),
):
    """Daily settle prices for the nearby (front-month) contract.

    For each trade date, selects the contract_month closest to (but >=) that date.
    Returns up to 2,000 points.
    """
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=365)

    # Get all futures rows in the date range, ordered by date + contract_month
    stmt = (
        select(FuturesDaily)
        .where(
            FuturesDaily.commodity == commodity,
            FuturesDaily.trade_date >= start_date,
            FuturesDaily.trade_date <= end_date,
        )
        .order_by(FuturesDaily.trade_date, FuturesDaily.contract_month)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No futures data for {commodity} in range")

    # For each trade date, pick the nearest contract_month >= trade_date's month
    points: list[FuturesPoint] = []
    seen_dates: set[date] = set()
    for row in rows:
        td = row.trade_date
        if td in seen_dates:
            continue
        # contract_month is "YYYY-MM"; pick first one >= trade_date month
        trade_month = td.strftime("%Y-%m")
        if row.contract_month >= trade_month:
            seen_dates.add(td)
            points.append(FuturesPoint(
                date=td.isoformat(),
                settle=round(float(row.settlement) / 100, 4) if float(row.settlement) > 50 else round(float(row.settlement), 4),
                volume=row.volume,
            ))

    # If the >= filter missed some dates, do a second pass picking the nearest contract
    if len(points) < len({r.trade_date for r in rows}) * 0.5:
        # Fallback: for each date, just take the contract closest to that date
        points = []
        seen_dates = set()
        by_date: dict[date, list] = {}
        for row in rows:
            by_date.setdefault(row.trade_date, []).append(row)
        for td in sorted(by_date.keys()):
            contracts = by_date[td]
            trade_month = td.strftime("%Y-%m")
            # Prefer >= trade_month, fallback to the last available
            eligible = [c for c in contracts if c.contract_month >= trade_month]
            pick = eligible[0] if eligible else contracts[-1]
            points.append(FuturesPoint(
                date=td.isoformat(),
                settle=round(float(pick.settlement) / 100, 4) if float(pick.settlement) > 50 else round(float(pick.settlement), 4),
                volume=pick.volume,
            ))

    return FuturesTimeSeriesResponse(
        commodity=commodity,
        contract_type="nearby",
        points=points[-2000:],  # cap at 2000 points
    )


@router.get("/curve", response_model=ForwardCurveResponse)
async def get_forward_curve(
    commodity: str = Depends(commodity_param),
    as_of: str | None = Query(None, description="ISO date (defaults to latest available)"),
    db: AsyncSession = Depends(get_db),
):
    """Forward curve: next 6 delivery months from the given date.

    Returns one settle price per contract month.
    """
    if as_of:
        ref_date = date.fromisoformat(as_of)
    else:
        # Find the latest trade date
        latest_stmt = select(func.max(FuturesDaily.trade_date)).where(
            FuturesDaily.commodity == commodity
        )
        latest_result = await db.execute(latest_stmt)
        ref_date = latest_result.scalar()
        if not ref_date:
            raise HTTPException(status_code=404, detail=f"No futures data for {commodity}")

    ref_month = ref_date.strftime("%Y-%m")

    # Get all contracts on or near the reference date
    # Try exact date first, fall back to most recent 3 trading days
    stmt = (
        select(FuturesDaily)
        .where(
            FuturesDaily.commodity == commodity,
            FuturesDaily.trade_date >= ref_date - timedelta(days=5),
            FuturesDaily.trade_date <= ref_date,
            FuturesDaily.contract_month >= ref_month,
        )
        .order_by(FuturesDaily.trade_date.desc(), FuturesDaily.contract_month)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No forward curve data for {commodity} as of {ref_date}")

    # Take the most recent trade date, then pick first 6 distinct contract months
    best_date = rows[0].trade_date
    curve_points: list[ForwardCurvePoint] = []
    seen_months: set[str] = set()
    for row in rows:
        if row.trade_date != best_date:
            continue
        if row.contract_month in seen_months:
            continue
        seen_months.add(row.contract_month)
        settle_val = float(row.settlement)
        curve_points.append(ForwardCurvePoint(
            contract_month=row.contract_month,
            settle=round(settle_val / 100, 4) if settle_val > 50 else round(settle_val, 4),
        ))
        if len(curve_points) >= 6:
            break

    return ForwardCurveResponse(
        commodity=commodity,
        as_of_date=best_date.isoformat(),
        points=curve_points,
    )


@router.get("/dxy", response_model=DxyTimeSeriesResponse)
async def get_dxy_time_series(
    start: str | None = Query(None, description="ISO date"),
    end: str | None = Query(None, description="ISO date"),
    db: AsyncSession = Depends(get_db),
):
    """DXY (U.S. Dollar Index) daily time series."""
    end_date = date.fromisoformat(end) if end else date.today()
    start_date = date.fromisoformat(start) if start else end_date - timedelta(days=365)

    stmt = (
        select(DxyDaily)
        .where(
            DxyDaily.trade_date >= start_date,
            DxyDaily.trade_date <= end_date,
        )
        .order_by(DxyDaily.trade_date)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="No DXY data in range")

    points = [
        DxyPoint(date=row.trade_date.isoformat(), value=round(float(row.dxy), 2))
        for row in rows
    ]

    return DxyTimeSeriesResponse(points=points)


@router.get("/costs", response_model=ProductionCostResponse)
async def get_production_costs(
    commodity: str = Depends(commodity_param),
    db: AsyncSession = Depends(get_db),
):
    """Latest ERS production cost per bushel + current futures for margin calc."""
    # Get latest cost year
    cost_stmt = (
        select(ErsProductionCost)
        .where(ErsProductionCost.commodity == commodity)
        .order_by(ErsProductionCost.year.desc())
        .limit(1)
    )
    cost_result = await db.execute(cost_stmt)
    cost = cost_result.scalar_one_or_none()

    if not cost:
        raise HTTPException(status_code=404, detail=f"No production cost data for {commodity}")

    # Get latest nearby futures price for margin calculation
    today = date.today()
    current_month = today.strftime("%Y-%m")
    futures_stmt = (
        select(FuturesDaily)
        .where(
            FuturesDaily.commodity == commodity,
            FuturesDaily.contract_month >= current_month,
        )
        .order_by(FuturesDaily.trade_date.desc(), FuturesDaily.contract_month)
        .limit(1)
    )
    futures_result = await db.execute(futures_stmt)
    futures = futures_result.scalar_one_or_none()

    current_price = None
    margin = None
    if futures:
        settle_val = float(futures.settlement)
        current_price = round(settle_val / 100, 4) if settle_val > 50 else round(settle_val, 4)
        if cost.total_cost_per_bu:
            margin = round(current_price - float(cost.total_cost_per_bu), 4)

    return ProductionCostResponse(
        commodity=commodity,
        year=cost.year,
        variable_cost_per_bu=round(float(cost.variable_cost_per_bu), 4) if cost.variable_cost_per_bu else None,
        total_cost_per_bu=round(float(cost.total_cost_per_bu), 4) if cost.total_cost_per_bu else None,
        current_futures_price=current_price,
        margin_per_bu=margin,
    )


@router.get("/fertilizer", response_model=list[FertilizerPriceResponse])
async def get_fertilizer_prices(
    limit: int = Query(4, ge=1, le=20, description="Number of quarters to return"),
    db: AsyncSession = Depends(get_db),
):
    """Latest quarterly fertilizer prices (anhydrous ammonia, DAP, potash)."""
    stmt = (
        select(ErsFertilizerPrice)
        .order_by(ErsFertilizerPrice.quarter.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="No fertilizer price data")

    return [
        FertilizerPriceResponse(
            quarter=row.quarter,
            anhydrous_ammonia_ton=round(float(row.anhydrous_ammonia_ton), 2) if row.anhydrous_ammonia_ton else None,
            dap_ton=round(float(row.dap_ton), 2) if row.dap_ton else None,
            potash_ton=round(float(row.potash_ton), 2) if row.potash_ton else None,
        )
        for row in rows
    ]


# Marketing year start month (US convention):
#   Wheat: June  |  Corn & Soybean: September
_MARKETING_YEAR_START_MONTH = {"wheat": 6, "corn": 9, "soybean": 9}


def _week_of_marketing_year(as_of: date, commodity: str) -> int:
    """Weeks elapsed since the start of the current marketing year (1-indexed)."""
    start_month = _MARKETING_YEAR_START_MONTH.get(commodity, 9)
    start_year = as_of.year if as_of.month >= start_month else as_of.year - 1
    start = date(start_year, start_month, 1)
    return max(1, (as_of - start).days // 7 + 1)


@router.get("/exports", response_model=ExportPaceResponse)
async def get_export_pace(
    commodity: str = Depends(commodity_param),
    db: AsyncSession = Depends(get_db),
):
    """Latest weekly export commitment snapshot vs the 5-year same-week average.

    "Committed" = outstanding sales + accumulated exports, the standard FAS
    pipeline metric. The 5-year average is taken over the same week-of-
    marketing-year across the prior five marketing years, which normalizes
    for seasonality (exports ramp through the marketing year) and lets the
    frontend show a "pace vs normal" signal regardless of absolute volume.
    """
    # Latest snapshot
    latest_stmt = (
        select(ExportCommitment)
        .where(ExportCommitment.commodity == commodity)
        .order_by(ExportCommitment.as_of_date.desc())
        .limit(1)
    )
    result = await db.execute(latest_stmt)
    latest = result.scalar_one_or_none()
    if latest is None:
        raise HTTPException(404, f"No export commitment data for {commodity}")

    outstanding = float(latest.outstanding_sales_mt) if latest.outstanding_sales_mt is not None else None
    accumulated = float(latest.accumulated_exports_mt) if latest.accumulated_exports_mt is not None else None
    committed = None
    if outstanding is not None and accumulated is not None:
        committed = outstanding + accumulated

    woy = _week_of_marketing_year(latest.as_of_date, commodity)

    # 5-year same-week average. "Same week" = +/- 3 days from the matching
    # week-of-marketing-year date across the prior five marketing years.
    avg_stmt = text("""
        WITH prior_years AS (
            SELECT
                (COALESCE(outstanding_sales_mt, 0) + COALESCE(accumulated_exports_mt, 0)) AS committed_mt,
                as_of_date,
                EXTRACT(YEAR FROM as_of_date) AS yr
            FROM export_commitments
            WHERE commodity = :commodity
              AND as_of_date < :cutoff
              AND as_of_date >= :earliest
        )
        SELECT AVG(committed_mt) FROM (
            SELECT DISTINCT ON (yr) committed_mt, yr
            FROM prior_years
            WHERE ABS(EXTRACT(DOY FROM as_of_date) - :target_doy) <= 3
               OR ABS(EXTRACT(DOY FROM as_of_date) - :target_doy_wrap) <= 3
            ORDER BY yr, ABS(EXTRACT(DOY FROM as_of_date) - :target_doy)
        ) sub
    """)
    # day-of-year of the current snapshot for same-week matching. Wrap-around
    # handles the Jan 1 boundary when target_doy is near 1 or 365.
    target_doy = int(latest.as_of_date.strftime("%j"))
    avg_result = await db.execute(avg_stmt, {
        "commodity": commodity,
        "cutoff": latest.as_of_date.replace(year=latest.as_of_date.year - 1),
        "earliest": latest.as_of_date.replace(year=latest.as_of_date.year - 6),
        "target_doy": target_doy,
        "target_doy_wrap": target_doy if target_doy > 180 else target_doy + 365,
    })
    five_yr_avg = avg_result.scalar_one_or_none()
    five_yr_avg = float(five_yr_avg) if five_yr_avg is not None else None

    pct_of_avg = None
    if committed is not None and five_yr_avg and five_yr_avg > 0:
        pct_of_avg = round(committed / five_yr_avg * 100, 1)

    return ExportPaceResponse(
        commodity=commodity,
        as_of_date=latest.as_of_date,
        marketing_year=latest.marketing_year,
        outstanding_sales_mt=round(outstanding, 1) if outstanding is not None else None,
        accumulated_exports_mt=round(accumulated, 1) if accumulated is not None else None,
        total_committed_mt=round(committed, 1) if committed is not None else None,
        five_yr_avg_committed_mt=round(five_yr_avg, 1) if five_yr_avg is not None else None,
        pct_of_5yr_avg=pct_of_avg,
        week_of_marketing_year=woy,
    )
