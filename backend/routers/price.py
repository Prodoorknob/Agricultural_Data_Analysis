from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.schemas import (
    PriceForecastResponse,
    ProbabilityResponse,
    WasdeSignalResponse,
    PriceForecastHistoryItem,
)

router = APIRouter()


@router.get("/", response_model=PriceForecastResponse)
async def get_price_forecast(
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    horizon_months: int = Query(default=3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    # TODO: implement in Step 7
    raise NotImplementedError("Price forecast endpoint not yet implemented")


@router.get("/probability", response_model=ProbabilityResponse)
async def get_price_probability(
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    threshold_price: float = Query(..., gt=0),
    horizon_months: int = Query(default=3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    # TODO: implement in Step 7
    raise NotImplementedError("Probability endpoint not yet implemented")


@router.get("/wasde-signal", response_model=WasdeSignalResponse)
async def get_wasde_signal(
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    db: AsyncSession = Depends(get_db),
):
    # TODO: implement in Step 7
    raise NotImplementedError("WASDE signal endpoint not yet implemented")


@router.get("/history", response_model=list[PriceForecastHistoryItem])
async def get_price_history(
    commodity: str = Query(..., pattern="^(corn|soybean|wheat)$"),
    horizon_months: int = Query(default=3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    # TODO: implement in Step 7
    raise NotImplementedError("Price history endpoint not yet implemented")
