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


# ---------------------------------------------------------------------------
# Module 03: Planted Acreage Prediction
# ---------------------------------------------------------------------------


class AcreageForecastResponse(BaseModel):
    commodity: str
    forecast_year: int
    level: str  # 'national' | 'state'
    state_fips: str | None = None
    state_name: str | None = None
    forecast_acres_millions: float
    p10_acres_millions: float | None = None
    p90_acres_millions: float | None = None
    corn_soy_ratio: float | None = None
    corn_soy_ratio_pctile: int | None = None
    key_driver: str | None = None
    vs_prior_year_pct: float | None = None
    published_at: date | None = None
    model_ver: str | None = None


class StateAcreageItem(BaseModel):
    state_fips: str
    state: str
    forecast_acres_millions: float
    vs_prior_pct: float | None = None


class StatesAcreageResponse(BaseModel):
    commodity: str
    forecast_year: int
    states: list[StateAcreageItem]


class AcreageAccuracyItem(BaseModel):
    forecast_year: int
    commodity: str
    level: str
    model_forecast: float
    usda_prospective: float | None = None
    usda_june_actual: float | None = None
    model_vs_usda_pct: float | None = None
    model_vs_actual_pct: float | None = None


class PriceRatioResponse(BaseModel):
    as_of_date: date
    corn_dec_futures: float | None = None
    soy_nov_futures: float | None = None
    corn_soy_ratio: float | None = None
    historical_percentile: int | None = None
    historical_context: str | None = None
    implication: str | None = None  # 'corn_favored' | 'soy_favored' | 'neutral'


# ---------------------------------------------------------------------------
# Module 04: Crop Yield Forecasting
# ---------------------------------------------------------------------------


class YieldForecastResponse(BaseModel):
    fips: str
    crop: str
    crop_year: int
    week: int
    p10: float
    p50: float
    p90: float
    unit: str = "bu/acre"
    confidence: str  # 'low' | 'medium' | 'high'
    county_avg_5yr: float | None = None
    vs_avg_pct: float | None = None
    model_ver: str
    last_updated: str | None = None


class YieldMapItem(BaseModel):
    fips: str
    p50: float
    confidence: str
    vs_avg_pct: float | None = None


class YieldMapResponse(BaseModel):
    crop: str
    crop_year: int
    week: int
    counties: list[YieldMapItem]


class YieldHistoryItem(BaseModel):
    crop_year: int
    week: int
    p50_forecast: float
    actual_yield: float | None = None
    error_pct: float | None = None
