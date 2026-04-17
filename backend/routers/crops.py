"""FastAPI router for crop-level Crops-tab endpoints.

Base path: /api/v1/crops

Replaces the frontend's placeholder `profitPerAcre = yield * 4.5 - 700`
formula (which produced nonsense for anything other than corn) with a
real per-commodity join of NASS price + NASS yield + ERS cost/acre,
returning an honest per-year profit-per-acre series.

Uses the local parquet cache rather than RDS for NASS lookups so we avoid
round-tripping 25 years of rows back through the API layer. The per-state
parquets live at ``survey_datasets/partitioned_states/{STATE}.parquet``;
this module assumes they have been rebuilt against the new canonical
aggregation (pipeline/rebuild_enrichment.py). If that's not true, the
endpoint simply returns fewer years.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.db_tables import ErsProductionCost

logger = logging.getLogger(__name__)

router = APIRouter()

# Commodities that appear both in ERS costs and NASS price/yield.
# Wheat is a single row here because NASS publishes wheat at commodity
# level (class=ALL CLASSES), not per-season.
PROFIT_COMMODITIES = {
    "corn", "soybean", "soybeans", "wheat", "cotton", "rice",
    "peanut", "peanuts", "sorghum", "oats", "barley",
}


def _normalize_commodity(name: str) -> str:
    """Fold URL plural forms to the ERS table's singular key."""
    n = name.lower()
    return "soybean" if n == "soybeans" else ("peanut" if n == "peanuts" else n)


def commodity_param_broad(
    commodity: str = Query(..., min_length=2, max_length=20),
) -> str:
    """Commodity query param, normalized, restricted to profit-supported set.
    Raises 422 if unknown."""
    n = _normalize_commodity(commodity)
    if n not in {"corn", "soybean", "wheat", "cotton", "rice",
                 "peanut", "sorghum", "oats", "barley"}:
        raise HTTPException(422, f"commodity '{commodity}' not supported for profit-history")
    return n


NASS_COMMODITY_MAP = {
    "corn": "CORN",
    "soybean": "SOYBEANS",
    "wheat": "WHEAT",
    "cotton": "COTTON",
    "rice": "RICE",
    "peanut": "PEANUTS",
    "sorghum": "SORGHUM",
    "oats": "OATS",
    "barley": "BARLEY",
}

# Standard US state-alpha → name map used for parquet file lookup.
_STATE_FILE_MAP = {
    "AL": "AL", "AK": "AK", "AZ": "AZ", "AR": "AR", "CA": "CA", "CO": "CO",
    "CT": "CT", "DE": "DE", "FL": "FL", "GA": "GA", "HI": "HI", "ID": "ID",
    "IL": "IL", "IN": "IN", "IA": "IA", "KS": "KS", "KY": "KY", "LA": "LA",
    "ME": "ME", "MD": "MD", "MA": "MA", "MI": "MI", "MN": "MN", "MS": "MS",
    "MO": "MO", "MT": "MT", "NE": "NE", "NV": "NV", "NH": "NH", "NJ": "NJ",
    "NM": "NM", "NY": "NY", "NC": "NC", "ND": "ND", "OH": "OH", "OK": "OK",
    "OR": "OR", "PA": "PA", "RI": "RI", "SC": "SC", "SD": "SD", "TN": "TN",
    "TX": "TX", "UT": "UT", "VT": "VT", "VA": "VA", "WA": "WA", "WV": "WV",
    "WI": "WI", "WY": "WY",
}

# Look in the rebuild output first (current run), fall back to the legacy
# pipeline/output dir.
_REBUILT_DIR = Path(__file__).resolve().parent.parent.parent / "pipeline" / "output_rebuilt"
_LEGACY_DIR = Path(__file__).resolve().parent.parent.parent / "pipeline" / "output"


def _load_state_parquet(state: str) -> pd.DataFrame | None:
    for base in (_REBUILT_DIR, _LEGACY_DIR):
        p = base / f"{state}.parquet"
        if p.exists():
            return pd.read_parquet(p)
    return None


def _revenue_per_acre(yield_value: float, yield_unit: str,
                      price: float, price_unit: str) -> float | None:
    """Convert per-acre yield × per-unit price → $/acre.

    Handles the three unit families NASS uses for the major crops:
      - BU / ACRE  × $ / BU    → direct multiplication
      - LB / ACRE  × $ / CWT   → divide yield by 100 (CWT = 100 lb)
      - LB / ACRE  × $ / LB    → direct multiplication
      - LB / ACRE  × $ / TON   → divide yield by 2000
    Unknown unit pairings return None rather than risking a silent
    wrong-by-1000 computation.
    """
    yu = yield_unit.upper()
    pu = price_unit.upper()
    if yu == "BU / ACRE" and pu == "$ / BU":
        return yield_value * price
    if yu == "LB / ACRE" and pu == "$ / CWT":
        return yield_value / 100 * price
    if yu == "LB / ACRE" and pu == "$ / LB":
        return yield_value * price
    if yu == "LB / ACRE" and pu == "$ / TON":
        return yield_value / 2000 * price
    if yu == "CWT / ACRE" and pu == "$ / CWT":
        return yield_value * price
    return None


class ProfitHistoryPoint(BaseModel):
    year: int
    price: float | None
    price_unit: str | None
    yield_value: float | None
    yield_unit: str | None
    revenue_per_acre: float | None
    variable_cost_per_acre: float | None
    total_cost_per_acre: float | None
    profit_per_acre: float | None   # revenue − total_cost


class ProfitHistoryResponse(BaseModel):
    commodity: str
    state: str
    points: list[ProfitHistoryPoint]
    cost_source: str
    note: str | None = None


@router.get("/profit-history", response_model=ProfitHistoryResponse)
async def profit_history(
    commodity: str = Depends(commodity_param_broad),
    state: str = Query("IA", min_length=2, max_length=2, pattern="^[A-Za-z]{2}$"),
    db: AsyncSession = Depends(get_db),
):
    """Per-year profit per acre = (NASS price × NASS state yield) − ERS US cost/acre.

    Costs come from ERS Commodity Costs and Returns, which publishes a
    single US-average series per commodity. State-specific costs aren't
    available; we apply the national cost against the state's own yield
    and price. That is how USDA ERS itself computes state profitability
    in its AgCensus tables — noted in the response so the frontend can
    surface it honestly.
    """
    state_upper = state.upper()
    if state_upper not in _STATE_FILE_MAP:
        raise HTTPException(422, f"unknown state code {state}")

    df = _load_state_parquet(state_upper)
    if df is None:
        raise HTTPException(404, f"no parquet for state {state_upper}")

    nass_name = NASS_COMMODITY_MAP[commodity]

    # Only canonical, annual, ALL-CLASSES rows — matches the B1 aggregation
    # rules. Sub-class rows (e.g. RICE LONG GRAIN) aren't applicable here.
    can = df[
        (df["commodity_desc"] == nass_name)
        & (df["reference_period_desc"].fillna("").isin(["YEAR", "MARKETING YEAR", ""]))
        & (df["class_desc"].fillna("").isin(["ALL CLASSES", ""]))
        & (df["domain_desc"].fillna("TOTAL") == "TOTAL")
    ]
    if can.empty:
        raise HTTPException(404, f"no NASS data for {commodity} in {state_upper}")

    # Price received — one row per year, pick the row with the largest
    # value_num (MARKETING YEAR annual — monthly prices are filtered by the
    # reference_period filter above).
    price_rows = (
        can[can["statisticcat_desc"] == "PRICE RECEIVED"]
        .sort_values("value_num", ascending=False)
        .drop_duplicates(subset=["year"], keep="first")
        .set_index("year")
    )
    yield_rows = (
        can[can["statisticcat_desc"] == "YIELD"]
        .sort_values("value_num", ascending=False)
        .drop_duplicates(subset=["year"], keep="first")
        .set_index("year")
    )

    # ERS costs from DB
    cost_stmt = (
        select(ErsProductionCost)
        .where(ErsProductionCost.commodity == commodity)
        .order_by(ErsProductionCost.year)
    )
    result = await db.execute(cost_stmt)
    cost_rows = {r.year: r for r in result.scalars().all()}

    years = sorted(set(price_rows.index) | set(yield_rows.index))
    points: list[ProfitHistoryPoint] = []
    for year in years:
        pr = price_rows.loc[year] if year in price_rows.index else None
        yr = yield_rows.loc[year] if year in yield_rows.index else None

        price = float(pr["value_num"]) if pr is not None and pd.notna(pr["value_num"]) else None
        price_unit = str(pr["unit_desc"]) if pr is not None else None
        yval = float(yr["value_num"]) if yr is not None and pd.notna(yr["value_num"]) else None
        yunit = str(yr["unit_desc"]) if yr is not None else None

        revenue = None
        if price is not None and yval is not None and price_unit and yunit:
            revenue = _revenue_per_acre(yval, yunit, price, price_unit)

        cost = cost_rows.get(int(year))
        var_cost = float(cost.variable_cost_per_acre) if cost and cost.variable_cost_per_acre is not None else None
        tot_cost = float(cost.total_cost_per_acre) if cost and cost.total_cost_per_acre is not None else None

        profit = None
        if revenue is not None and tot_cost is not None:
            profit = round(revenue - tot_cost, 2)

        points.append(ProfitHistoryPoint(
            year=int(year),
            price=round(price, 4) if price is not None else None,
            price_unit=price_unit,
            yield_value=round(yval, 2) if yval is not None else None,
            yield_unit=yunit,
            revenue_per_acre=round(revenue, 2) if revenue is not None else None,
            variable_cost_per_acre=var_cost,
            total_cost_per_acre=tot_cost,
            profit_per_acre=profit,
        ))

    note = None
    if not cost_rows:
        note = (
            f"No ERS Commodity Costs and Returns data for {commodity}. "
            "Profit column is null; revenue shown is price × yield only."
        )

    return ProfitHistoryResponse(
        commodity=commodity,
        state=state_upper,
        points=points,
        cost_source="USDA ERS Commodity Costs and Returns (U.S. average)",
        note=note,
    )
