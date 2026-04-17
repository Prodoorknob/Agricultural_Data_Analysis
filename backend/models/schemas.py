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
    # Raw acres (e.g. 92_800_000 for 92.8M acres). The `_millions` suffix on
    # prior versions was misleading — the DB stored raw acres and the suffix
    # never matched the numeric scale.
    forecast_acres: float
    p10_acres: float | None = None
    p90_acres: float | None = None
    corn_soy_ratio: float | None = None
    corn_soy_ratio_pctile: int | None = None
    key_driver: str | None = None
    vs_prior_year_pct: float | None = None
    published_at: date | None = None
    model_ver: str | None = None


class StateAcreageItem(BaseModel):
    state_fips: str
    state: str
    forecast_acres: float  # raw acres, see AcreageForecastResponse
    vs_prior_pct: float | None = None


class StatesAcreageResponse(BaseModel):
    commodity: str
    forecast_year: int
    states: list[StateAcreageItem]


class AcreageAccuracyItem(BaseModel):
    forecast_year: int
    commodity: str
    level: str
    model_forecast: float | None = None
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


# ---------------------------------------------------------------------------
# Market data endpoints (§5.2)
# ---------------------------------------------------------------------------


class FuturesPoint(BaseModel):
    date: str  # ISO date
    settle: float  # $/bu
    volume: int | None = None


class FuturesTimeSeriesResponse(BaseModel):
    commodity: str
    contract_type: str  # 'nearby' or specific month
    points: list[FuturesPoint]


class ForwardCurvePoint(BaseModel):
    contract_month: str  # e.g. "2026-07"
    settle: float


class ForwardCurveResponse(BaseModel):
    commodity: str
    as_of_date: str
    points: list[ForwardCurvePoint]


class DxyPoint(BaseModel):
    date: str
    value: float


class DxyTimeSeriesResponse(BaseModel):
    points: list[DxyPoint]


class ProductionCostResponse(BaseModel):
    commodity: str
    year: int
    variable_cost_per_bu: float | None = None
    total_cost_per_bu: float | None = None
    current_futures_price: float | None = None  # latest nearby settle, $/bu
    margin_per_bu: float | None = None  # futures - total_cost


class FertilizerPriceResponse(BaseModel):
    quarter: str
    anhydrous_ammonia_ton: float | None = None
    dap_ton: float | None = None
    potash_ton: float | None = None


class ExportPaceResponse(BaseModel):
    """Weekly export commitments vs the 5-year same-week average.

    Fills the Market tab's third-card slot when the commodity is wheat
    (the corn/soy ratio card is meaningless there).
    """
    commodity: str
    as_of_date: date
    marketing_year: str
    outstanding_sales_mt: float | None
    accumulated_exports_mt: float | None
    total_committed_mt: float | None
    five_yr_avg_committed_mt: float | None
    pct_of_5yr_avg: float | None
    week_of_marketing_year: int | None


class YieldAccuracyWeekItem(BaseModel):
    crop: str
    week: int
    avg_pct_error: float | None = None
    avg_coverage: float | None = None  # fraction of forecasts within p10–p90
    baseline_rrmse: float | None = None  # county 5yr mean baseline
    n_counties: int = 0


class YieldModelMetadataResponse(BaseModel):
    """Per-crop model metadata for the frontend performance banner.

    The yield model surfaces in the dashboard even when its deployment gate
    fails (class-project use case). This response gives the UI enough data to
    annotate it honestly ("experimental" / "production") rather than letting
    readers treat gate-failed forecasts as production-quality.
    """
    crop: str
    model_ver: str | None = None
    n_weeks: int = 0
    n_weeks_pass_gate: int = 0
    gate_status: str  # "pass" | "partial" | "fail"
    avg_val_rrmse: float | None = None
    avg_test_rrmse: float | None = None
    avg_baseline_rrmse: float | None = None
    has_weather_features: bool = False
    gate_threshold_pct: float | None = None
