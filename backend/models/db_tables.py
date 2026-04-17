"""SQLAlchemy ORM models for the prediction module database tables."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class FuturesDaily(Base):
    __tablename__ = "futures_daily"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    commodity: Mapped[str] = mapped_column(String(10), nullable=False)
    contract_month: Mapped[str] = mapped_column(String(7), nullable=False)
    settlement: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    open_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="nasdaq_dl")
    ingest_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", "commodity", "contract_month", name="uq_futures_daily"),
    )


class WasdeRelease(Base):
    __tablename__ = "wasde_releases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    release_date: Mapped[date] = mapped_column(Date, nullable=False)
    commodity: Mapped[str] = mapped_column(String(10), nullable=False)
    marketing_year: Mapped[str] = mapped_column(String(9), nullable=False)
    us_production: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    us_exports: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    ending_stocks: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    stocks_to_use: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    world_production: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="usda_wasde")

    __table_args__ = (
        UniqueConstraint("release_date", "commodity", "marketing_year", name="uq_wasde_releases"),
    )


class PriceForecast(Base):
    __tablename__ = "price_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    commodity: Mapped[str] = mapped_column(String(10), nullable=False)
    horizon_month: Mapped[str] = mapped_column(String(7), nullable=False)
    p10: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    p50: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    p90: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    prob_above_threshold: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    threshold_price: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    key_driver: Mapped[str | None] = mapped_column(String(100), nullable=True)
    divergence_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    model_ver: Mapped[str] = mapped_column(String(20), nullable=False)
    regime_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("run_date", "commodity", "horizon_month", "model_ver", name="uq_price_forecasts"),
    )


class ErsProductionCost(Base):
    __tablename__ = "ers_production_costs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    commodity: Mapped[str] = mapped_column(String(20), nullable=False)
    variable_cost_per_bu: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    total_cost_per_bu: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    variable_cost_per_acre: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_cost_per_acre: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    yield_units: Mapped[str | None] = mapped_column(String(40), nullable=True)
    yield_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint("year", "commodity", name="uq_ers_costs"),
    )


class DxyDaily(Base):
    __tablename__ = "dxy_daily"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    dxy: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="fred")
    ingest_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Module 03: Planted Acreage Prediction
# ---------------------------------------------------------------------------


class AcreageForecast(Base):
    __tablename__ = "acreage_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    forecast_year: Mapped[int] = mapped_column(Integer, nullable=False)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    commodity: Mapped[str] = mapped_column(String(20), nullable=False)
    forecast_acres: Mapped[float] = mapped_column(Numeric(10, 1), nullable=False)
    p10_acres: Mapped[float | None] = mapped_column(Numeric(10, 1), nullable=True)
    p90_acres: Mapped[float | None] = mapped_column(Numeric(10, 1), nullable=True)
    corn_soy_ratio: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    key_driver: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_ver: Mapped[str] = mapped_column(String(20), nullable=False)
    published_at: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "forecast_year", "state_fips", "commodity", "model_ver",
            name="uq_acreage_forecasts",
        ),
    )


class AcreageAccuracy(Base):
    __tablename__ = "acreage_accuracy"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    forecast_year: Mapped[int] = mapped_column(Integer, nullable=False)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    commodity: Mapped[str] = mapped_column(String(20), nullable=False)
    model_forecast: Mapped[float | None] = mapped_column(Numeric(10, 1), nullable=True)
    usda_prospective: Mapped[float | None] = mapped_column(Numeric(10, 1), nullable=True)
    usda_june_actual: Mapped[float | None] = mapped_column(Numeric(10, 1), nullable=True)
    model_vs_usda_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    model_vs_actual_pct: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "forecast_year", "state_fips", "commodity",
            name="uq_acreage_accuracy",
        ),
    )


class ErsFertilizerPrice(Base):
    __tablename__ = "ers_fertilizer_prices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quarter: Mapped[str] = mapped_column(String(7), nullable=False)
    anhydrous_ammonia_ton: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    dap_ton: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    potash_ton: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint("quarter", name="uq_fertilizer_prices"),
    )


# --- Module 03 Tier 1: Additional acreage data sources ---


class DroughtIndex(Base):
    __tablename__ = "drought_index"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    dsci_nov: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    dsci_fall_avg: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    dsci_winter_avg: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    drought_weeks_d2plus: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("state_fips", "year", name="uq_drought_index"),
    )


class RmaInsuredAcres(Base):
    __tablename__ = "rma_insured_acres"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    commodity: Mapped[str] = mapped_column(String(10), nullable=False)
    crop_year: Mapped[int] = mapped_column(Integer, nullable=False)
    net_reported_acres: Mapped[float | None] = mapped_column(Numeric(12, 1), nullable=True)
    policies_earning: Mapped[int | None] = mapped_column(Integer, nullable=True)
    liability_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "state_fips", "commodity", "crop_year", name="uq_rma_insured"
        ),
    )


class CrpEnrollment(Base):
    __tablename__ = "crp_enrollment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    enrolled_acres: Mapped[float | None] = mapped_column(Numeric(12, 1), nullable=True)
    expiring_acres: Mapped[float | None] = mapped_column(Numeric(12, 1), nullable=True)
    new_enrollment_acres: Mapped[float | None] = mapped_column(Numeric(12, 1), nullable=True)

    __table_args__ = (
        UniqueConstraint("state_fips", "year", name="uq_crp_enrollment"),
    )


class ExportCommitment(Base):
    __tablename__ = "export_commitments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    commodity: Mapped[str] = mapped_column(String(10), nullable=False)
    marketing_year: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    outstanding_sales_mt: Mapped[float | None] = mapped_column(Numeric(12, 1), nullable=True)
    accumulated_exports_mt: Mapped[float | None] = mapped_column(Numeric(12, 1), nullable=True)
    net_sales_mt: Mapped[float | None] = mapped_column(Numeric(12, 1), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "commodity", "marketing_year", "as_of_date",
            name="uq_export_commits",
        ),
    )


# ---------------------------------------------------------------------------
# Module 04: Crop Yield Forecasting
# ---------------------------------------------------------------------------


class SoilFeature(Base):
    __tablename__ = "soil_features"

    fips: Mapped[str] = mapped_column(String(5), primary_key=True)
    awc_cm: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    drain_class: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FeatureWeekly(Base):
    __tablename__ = "feature_weekly"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fips: Mapped[str] = mapped_column(String(5), nullable=False)
    crop: Mapped[str] = mapped_column(String(10), nullable=False)
    crop_year: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    gdd_ytd: Mapped[float | None] = mapped_column(Numeric(8, 1), nullable=True)
    cci_cumul: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    precip_deficit: Mapped[float | None] = mapped_column(Numeric(8, 1), nullable=True)
    vpd_stress_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drought_d3d4_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    soil_awc: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    soil_drain: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingest_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("fips", "crop", "crop_year", "week", name="uq_feature_weekly"),
    )


class YieldForecast(Base):
    __tablename__ = "yield_forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fips: Mapped[str] = mapped_column(String(5), nullable=False)
    crop: Mapped[str] = mapped_column(String(10), nullable=False)
    crop_year: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    p10: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    p50: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    p90: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    model_ver: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "fips", "crop", "crop_year", "week", "model_ver",
            name="uq_yield_forecasts",
        ),
    )


class YieldAccuracy(Base):
    """Walk-forward test predictions from train_yield.py.

    One row per (forecast_year, fips, crop, week, model_ver).
    Powers the Forecasts tab accuracy panel (§5.3.D).
    """

    __tablename__ = "yield_accuracy"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    forecast_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fips: Mapped[str] = mapped_column(String(5), nullable=False)
    crop: Mapped[str] = mapped_column(String(10), nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    model_p50: Mapped[float] = mapped_column(Numeric(6, 1), nullable=False)
    model_p10: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    model_p90: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    actual_yield: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    county_5yr_mean: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True)
    abs_error: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    pct_error: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    in_interval: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    split: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model_ver: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "forecast_year", "fips", "crop", "week", "model_ver",
            name="uq_yield_accuracy",
        ),
    )


class LandUseCategory(Base):
    __tablename__ = "land_use_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    state_alpha: Mapped[str] = mapped_column(String(2), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    acres: Mapped[float | None] = mapped_column(Numeric(14, 1), nullable=True)

    __table_args__ = (
        UniqueConstraint("state_fips", "year", "category", name="uq_land_use_categories"),
    )


class BlsEstablishment(Base):
    __tablename__ = "bls_establishments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    state_fips: Mapped[str] = mapped_column(String(2), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    naics: Mapped[str] = mapped_column(String(6), nullable=False)
    establishments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_annual_pay: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("state_fips", "year", "naics", name="uq_bls_establishments"),
    )
