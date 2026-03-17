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
    commodity: Mapped[str] = mapped_column(String(10), nullable=False)
    variable_cost_per_bu: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    total_cost_per_bu: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)

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
