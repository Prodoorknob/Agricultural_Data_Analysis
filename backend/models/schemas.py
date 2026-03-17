from datetime import date
from pydantic import BaseModel


class PriceForecastResponse(BaseModel):
    commodity: str
    run_date: date
    horizon_month: str  # 'YYYY-MM'
    p10: float
    p50: float
    p90: float
    unit: str = "USD/bushel"
    key_driver: str | None = None
    divergence_flag: bool = False
    regime_anomaly: bool = False
    model_ver: str


class ProbabilityResponse(BaseModel):
    commodity: str
    threshold_price: float
    horizon_month: str
    probability: float
    confidence_note: str = "Based on calibrated ensemble; +/-8pp historical calibration error"


class WasdeSignalResponse(BaseModel):
    commodity: str
    release_date: date
    stocks_to_use: float
    stocks_to_use_pctile: int
    prior_month_stu: float | None = None
    surprise: float | None = None
    surprise_direction: str | None = None  # 'bullish' | 'bearish' | 'neutral'
    historical_context: str | None = None


class PriceForecastHistoryItem(BaseModel):
    run_date: date
    horizon_month: str
    p50: float
    actual: float | None = None
    error_pct: float | None = None
