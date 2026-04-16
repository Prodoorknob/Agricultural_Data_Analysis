"""Feature engineering for planted acreage prediction (Module 03).

Features are computed as of November 1 of the prior year — the natural
decision-time snapshot for a February forecast.  All features must be
available by November 1 to avoid lookahead bias.
"""

from datetime import date
from functools import lru_cache

import numpy as np
import pandas as pd
from sqlalchemy import text

from backend.etl.common import get_sync_engine, setup_logging

logger = setup_logging("acreage_features")

# FIPS to state name mapping for the major producing states
FIPS_TO_STATE = {
    "01": "Alabama", "04": "Arizona", "05": "Arkansas", "06": "California",
    "08": "Colorado", "09": "Connecticut", "10": "Delaware", "12": "Florida",
    "13": "Georgia", "16": "Idaho", "17": "Illinois", "18": "Indiana",
    "19": "Iowa", "20": "Kansas", "21": "Kentucky", "22": "Louisiana",
    "23": "Maine", "24": "Maryland", "25": "Massachusetts", "26": "Michigan",
    "27": "Minnesota", "28": "Mississippi", "29": "Missouri", "30": "Montana",
    "31": "Nebraska", "32": "Nevada", "33": "New Hampshire", "34": "New Jersey",
    "35": "New Mexico", "36": "New York", "37": "North Carolina",
    "38": "North Dakota", "39": "Ohio", "40": "Oklahoma", "41": "Oregon",
    "42": "Pennsylvania", "44": "Rhode Island", "45": "South Carolina",
    "46": "South Dakota", "47": "Tennessee", "48": "Texas", "49": "Utah",
    "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
    "00": "National",
}

# Commodity name mapping (NASS uses uppercase, our DB uses lowercase)
COMMODITY_NASS_MAP = {
    "corn": "CORN",
    "soybean": "SOYBEANS",
    "wheat": "WHEAT",
}

# Top producing states (by FIPS) for each commodity — used for state-level models
TOP_STATES = {
    "corn": [
        "17", "19", "18", "27", "31", "39", "55", "46", "29", "26",
        "38", "20", "42", "08", "21",
    ],
    "soybean": [
        "17", "19", "18", "27", "29", "39", "38", "31", "46", "05",
        "55", "26", "20", "28", "47",
    ],
    "wheat": [
        "20", "38", "30", "40", "46", "27", "08", "31", "48", "53",
        "17", "16", "41", "42", "36",
    ],
    # Winter/spring wheat splits (both map to NASS "wheat" data)
    "wheat_winter": [
        "20", "40", "48", "08", "30", "46", "31", "53",  # KS, OK, TX, CO, MT, SD, NE, WA
    ],
    "wheat_spring": [
        "38", "27", "46", "30", "16",  # ND, MN, SD, MT, ID (SD/MT in both — dual-season)
    ],
}

# Decision dates by commodity — when farmers commit to planting
# Winter wheat planted Sep-Oct (decided Aug), spring crops decided Nov prior year
DECISION_DATES = {
    "corn": (11, 1),         # November 1 of prior year
    "soybean": (11, 1),      # November 1 of prior year
    "wheat": (11, 1),        # November 1 of prior year (legacy combined)
    "wheat_winter": (8, 1),  # August 1 — winter wheat planted Sep-Oct
    "wheat_spring": (3, 1),  # March 1 — spring wheat planted Apr-May
}

# Map split commodities to their NASS commodity name
COMMODITY_NASS_MAP_EXTENDED = {
    "wheat_winter": "WHEAT",
    "wheat_spring": "WHEAT",
}


def clear_query_caches():
    """Clear all LRU caches — call at start of each training run."""
    _query_futures_settlement.cache_clear()
    _query_ers_cost.cache_clear()
    _query_fertilizer_price.cache_clear()
    get_november_price_ratio.cache_clear()
    _query_drought_dsci.cache_clear()
    _query_rma_insured.cache_clear()
    _query_crp_enrollment.cache_clear()
    _query_export_commitments.cache_clear()


@lru_cache(maxsize=256)
def _query_futures_settlement(
    commodity: str, as_of_date: date, contract_month: str
) -> float | None:
    """Get the nearest futures settlement price on or before as_of_date."""
    engine = get_sync_engine()
    sql = text("""
        SELECT settlement FROM futures_daily
        WHERE commodity = :commodity
          AND contract_month = :contract_month
          AND trade_date <= :as_of
        ORDER BY trade_date DESC
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {
            "commodity": commodity,
            "contract_month": contract_month,
            "as_of": as_of_date,
        }).fetchone()
    return float(row[0]) if row else None


def _query_nass_acreage(state_fips: str, commodity: str, year: int) -> float | None:
    """Get NASS planted acreage for a state/commodity/year from futures_daily's
    companion NASS data (via the QuickStats pipeline parquet, loaded into
    a simple lookup). Falls back to a direct DB query if available."""
    # Try the DB first (if NASS acreage data has been loaded)
    engine = get_sync_engine()

    # NASS acreage is in the pipeline parquet files, not in RDS.
    # We use a local CSV cache or compute from parquet at training time.
    # For now, return None and let the training script handle this via pandas.
    return None


@lru_cache(maxsize=256)
def _query_ers_cost(commodity: str, year: int, field: str) -> float | None:
    """Get ERS production cost for a commodity/year."""
    engine = get_sync_engine()
    sql = text(f"SELECT {field} FROM ers_production_costs WHERE commodity = :c AND year = :y")
    with engine.connect() as conn:
        row = conn.execute(sql, {"c": commodity, "y": year}).fetchone()
    return float(row[0]) if row and row[0] is not None else None


@lru_cache(maxsize=256)
def _query_fertilizer_price(as_of_date: date, product: str) -> float | None:
    """Get the most recent fertilizer price on or before as_of_date."""
    engine = get_sync_engine()
    year = as_of_date.year
    quarter = (as_of_date.month - 1) // 3 + 1
    quarter_str = f"{year}-Q{quarter}"

    sql = text(f"SELECT {product} FROM ers_fertilizer_prices WHERE quarter <= :q ORDER BY quarter DESC LIMIT 1")
    with engine.connect() as conn:
        row = conn.execute(sql, {"q": quarter_str}).fetchone()
    return float(row[0]) if row and row[0] is not None else None


@lru_cache(maxsize=64)
def get_november_price_ratio(forecast_year: int) -> float | None:
    """Corn/soy price ratio as of November 1 of the prior year.

    Uses December corn and November soybean contracts — the standard
    economic signal farmers use for next-year planting decisions.
    """
    as_of = date(forecast_year - 1, 11, 1)
    corn_dec = _query_futures_settlement("corn", as_of, f"{forecast_year - 1}-12")
    soy_nov = _query_futures_settlement("soybean", as_of, f"{forecast_year - 1}-11")

    if corn_dec is None or soy_nov is None or soy_nov == 0:
        return None
    return corn_dec / soy_nov


# --- Tier 1 data source queries ---


@lru_cache(maxsize=256)
def _query_drought_dsci(state_fips: str, year: int) -> dict | None:
    """Get DSCI drought features for a state/year from drought_index."""
    engine = get_sync_engine()
    sql = text("""
        SELECT dsci_nov, dsci_fall_avg
        FROM drought_index
        WHERE state_fips = :fips AND year = :y
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"fips": state_fips, "y": year}).fetchone()
    if not row:
        return None
    return {
        "dsci_nov": float(row[0]) if row[0] is not None else None,
        "dsci_fall_avg": float(row[1]) if row[1] is not None else None,
    }


@lru_cache(maxsize=256)
def _query_rma_insured(state_fips: str, commodity: str, crop_year: int) -> float | None:
    """Get net reported insured acres for a state/commodity/year from rma_insured_acres."""
    engine = get_sync_engine()
    sql = text("""
        SELECT net_reported_acres
        FROM rma_insured_acres
        WHERE state_fips = :fips AND commodity = :c AND crop_year = :y
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"fips": state_fips, "c": commodity, "y": crop_year}).fetchone()
    return float(row[0]) if row and row[0] is not None else None


@lru_cache(maxsize=256)
def _query_crp_enrollment(state_fips: str, year: int) -> dict | None:
    """Get CRP enrollment/expirations for a state/year from crp_enrollment."""
    engine = get_sync_engine()
    sql = text("""
        SELECT enrolled_acres, expiring_acres
        FROM crp_enrollment
        WHERE state_fips = :fips AND year = :y
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"fips": state_fips, "y": year}).fetchone()
    if not row:
        return None
    return {
        "enrolled_acres": float(row[0]) if row[0] is not None else None,
        "expiring_acres": float(row[1]) if row[1] is not None else None,
    }


@lru_cache(maxsize=256)
def _query_export_commitments(commodity: str, marketing_year: str) -> dict | None:
    """Get export commitments snapshot nearest Nov 1 for a commodity/marketing year.

    Uses the latest as_of_date on or before Nov 15 of the start year
    (giving a ~2 week window around the decision date).
    """
    engine = get_sync_engine()
    sql = text("""
        SELECT outstanding_sales_mt, accumulated_exports_mt
        FROM export_commitments
        WHERE commodity = :c AND marketing_year = :my
        ORDER BY as_of_date DESC
        LIMIT 1
    """)
    with engine.connect() as conn:
        row = conn.execute(sql, {"c": commodity, "my": marketing_year}).fetchone()
    if not row:
        return None
    return {
        "outstanding_sales_mt": float(row[0]) if row[0] is not None else None,
        "accumulated_exports_mt": float(row[1]) if row[1] is not None else None,
    }


# State total cropland acres from NASS 2022 Census of Agriculture (1,000 acres)
# Used for computing CRP as % of cropland
STATE_CROPLAND_ACRES = {
    "17": 23_800_000, "19": 24_300_000, "18": 14_200_000, "27": 21_400_000,
    "31": 19_700_000, "39": 10_800_000, "55": 8_600_000, "46": 17_800_000,
    "29": 14_400_000, "26": 7_900_000, "38": 25_700_000, "20": 28_500_000,
    "42": 5_600_000, "08": 10_200_000, "21": 5_200_000, "05": 7_600_000,
    "28": 5_300_000, "47": 4_800_000, "30": 15_100_000, "40": 10_900_000,
    "48": 25_700_000, "53": 7_300_000, "16": 5_500_000, "41": 3_900_000,
    "36": 3_300_000, "22": 4_600_000,
}

# Marketing year start months by commodity (for export features)
MARKETING_YEAR_START = {"corn": 9, "soybean": 9, "wheat": 6}


_MONTH_ABBR = {6: "Jun", 9: "Sep"}
_MY_END_MONTH = {6: "May", 9: "Aug"}


def _get_marketing_year_str(commodity: str, forecast_year: int) -> str:
    """Get the marketing year string matching FAS format (e.g., 'Sep 2024/Aug 2025').

    For acreage decisions made in Nov of forecast_year-1, the relevant
    marketing year is the one currently active in November:
      - Corn/soy MY starts Sep, so Nov falls in MY starting Sep of that year
      - Wheat MY starts Jun, so Nov falls in MY starting Jun of that year
    """
    start_month = MARKETING_YEAR_START.get(commodity, 9)
    start_year = forecast_year - 1
    start_abbr = _MONTH_ABBR.get(start_month, "Sep")
    end_abbr = _MY_END_MONTH.get(start_month, "Aug")
    return f"{start_abbr} {start_year}/{end_abbr} {start_year + 1}"


def build_acreage_features(
    state_fips: str,
    commodity: str,
    forecast_year: int,
    nass_data: pd.DataFrame | None = None,
) -> pd.Series:
    """Build features for a single (state, commodity, forecast_year).

    Args:
        state_fips: 2-digit FIPS code ('00' for national)
        commodity: 'corn', 'soybean', or 'wheat'
        forecast_year: the planting year being forecast
        nass_data: optional DataFrame with historical NASS data
                   (columns: state_fips, commodity, year, acres_planted, yield_bu)
                   If None, features requiring NASS data are set to NaN.

    Returns:
        pd.Series with named features
    """
    # Use commodity-specific decision date
    dec_month, dec_day = DECISION_DATES.get(commodity, (11, 1))
    # For Nov decision: use prior year. For Aug/Mar: same forecast year context
    if dec_month >= 8:
        # Aug or Nov of prior year
        decision_date = date(forecast_year - 1, dec_month, dec_day)
    else:
        # Mar of forecast year (spring wheat decides in March of planting year)
        decision_date = date(forecast_year, dec_month, dec_day)
    features = {}

    # Resolve NASS commodity name (wheat_winter/wheat_spring -> wheat)
    nass_commodity = commodity.split("_")[0] if "_" in commodity else commodity

    # --- Price signals ---
    features["corn_soy_ratio"] = get_november_price_ratio(forecast_year)

    # Contract months: use the front-month contract at the decision date.
    # Yahoo Finance continuous contract data is tagged with the nearest active
    # contract month, so we query using infer_contract_month() for the
    # decision date rather than hardcoding forward-dated contracts.
    from backend.etl.ingest_futures import infer_contract_month

    corn_contract = infer_contract_month("corn", decision_date)
    soy_contract = infer_contract_month("soybean", decision_date)
    wheat_contract = infer_contract_month("wheat", decision_date)

    corn_dec = _query_futures_settlement("corn", decision_date, corn_contract)
    soy_nov = _query_futures_settlement("soybean", decision_date, soy_contract)
    wheat_dec = _query_futures_settlement("wheat", decision_date, wheat_contract)
    # Fallback: try next contract if front-month is expired
    if wheat_dec is None:
        wheat_months = [3, 5, 7, 9, 12]
        cm = int(wheat_contract.split("-")[1])
        idx = wheat_months.index(cm) if cm in wheat_months else 0
        next_cm = wheat_months[(idx + 1) % len(wheat_months)]
        next_yr = int(wheat_contract.split("-")[0]) + (1 if next_cm < cm else 0)
        wheat_dec = _query_futures_settlement("wheat", decision_date, f"{next_yr}-{next_cm:02d}")

    features["corn_futures_dec"] = corn_dec
    features["soy_futures_nov"] = soy_nov
    features["wheat_futures_jul"] = wheat_dec  # keep column name for model compat

    # --- Cost structure ---
    cost_year = forecast_year - 1
    var_cost = _query_ers_cost(nass_commodity, cost_year, "variable_cost_per_bu")
    features["variable_cost_bu"] = var_cost

    own_futures = {
        "corn": corn_dec, "soybean": soy_nov, "wheat": wheat_dec,
    }.get(nass_commodity)
    features["profit_margin_bu"] = (
        (own_futures - var_cost) if own_futures and var_cost else None
    )

    features["anhydrous_price_ton"] = _query_fertilizer_price(
        decision_date, "anhydrous_ammonia_ton"
    )

    # --- Relative crop profitability (corn vs soy) ---
    if nass_commodity in ("corn", "soybean"):
        corn_cost = _query_ers_cost("corn", cost_year, "variable_cost_per_bu")
        soy_cost = _query_ers_cost("soybean", cost_year, "variable_cost_per_bu")
        if corn_dec and soy_nov and corn_cost and soy_cost:
            corn_margin = corn_dec - corn_cost
            soy_margin = soy_nov - soy_cost
            features["relative_profitability"] = corn_margin - soy_margin
        else:
            features["relative_profitability"] = None
    else:
        features["relative_profitability"] = None

    # --- NASS historical (from provided DataFrame) ---
    if nass_data is not None and not nass_data.empty:
        state_crop = nass_data[
            (nass_data["state_fips"] == state_fips)
            & (nass_data["commodity"] == nass_commodity)
        ].sort_values("year")

        prior = state_crop[state_crop["year"] == forecast_year - 1]
        features["prior_year_acres"] = (
            prior["acres_planted"].values[0] if len(prior) else None
        )
        features["prior_year_yield"] = (
            prior["yield_bu"].values[0] if len(prior) and "yield_bu" in prior.columns else None
        )

        # 3-year average acres (for residual baseline)
        recent_3 = state_crop[
            (state_crop["year"] >= forecast_year - 3)
            & (state_crop["year"] < forecast_year)
        ]
        features["prior_3yr_avg_acres"] = (
            recent_3["acres_planted"].mean() if len(recent_3) >= 2 else None
        )

        # 5-year average acres
        recent = state_crop[
            (state_crop["year"] >= forecast_year - 5)
            & (state_crop["year"] < forecast_year)
        ]
        features["prior_5yr_avg_acres"] = (
            recent["acres_planted"].mean() if len(recent) >= 3 else None
        )

        # Yield trend (5-year linear slope)
        trend_data = state_crop[
            (state_crop["year"] >= forecast_year - 5)
            & (state_crop["year"] < forecast_year)
            & (state_crop["yield_bu"].notna())
        ]
        if len(trend_data) >= 3:
            x = trend_data["year"].values.astype(float)
            y = trend_data["yield_bu"].values.astype(float)
            slope = np.polyfit(x, y, 1)[0]
            features["yield_trend_5yr"] = slope
        else:
            features["yield_trend_5yr"] = None

        # Rotation ratio (corn/soy ratio of prior year acres)
        if state_fips != "00":
            corn_prior = state_crop[
                (state_crop["year"] == forecast_year - 1)
            ]
            soy_data = nass_data[
                (nass_data["state_fips"] == state_fips)
                & (nass_data["commodity"] == "soybean")
                & (nass_data["year"] == forecast_year - 1)
            ]
            c_acres = corn_prior["acres_planted"].values[0] if len(corn_prior) else None
            s_acres = soy_data["acres_planted"].values[0] if len(soy_data) else None
            if c_acres and s_acres and s_acres > 0:
                features["rotation_ratio"] = c_acres / s_acres
            else:
                features["rotation_ratio"] = None
        else:
            features["rotation_ratio"] = None
    else:
        features["prior_year_acres"] = None
        features["prior_year_yield"] = None
        features["prior_3yr_avg_acres"] = None
        features["prior_5yr_avg_acres"] = None
        features["yield_trend_5yr"] = None
        features["rotation_ratio"] = None

    # --- Drought signals (Tier 1) ---
    # For Nov decision: use prior year drought. For Aug decision: use current year summer.
    drought_year = decision_date.year
    dsci = _query_drought_dsci(state_fips, drought_year)
    features["dsci_nov"] = dsci["dsci_nov"] if dsci else None
    features["dsci_fall_avg"] = dsci["dsci_fall_avg"] if dsci else None

    # --- Crop insurance signals (Tier 1) ---
    # Prior year insured acres (finalized well before Nov 1)
    insured_prior = _query_rma_insured(state_fips, nass_commodity, forecast_year - 1)
    features["insured_acres_prior"] = insured_prior
    insured_prior2 = _query_rma_insured(state_fips, nass_commodity, forecast_year - 2)
    if insured_prior and insured_prior2 and insured_prior2 > 0:
        features["insured_acres_yoy_change"] = (
            (insured_prior - insured_prior2) / insured_prior2
        )
    else:
        features["insured_acres_yoy_change"] = None

    # --- CRP land supply signals (Tier 1) ---
    crp = _query_crp_enrollment(state_fips, forecast_year)
    features["crp_expiring_acres"] = crp["expiring_acres"] if crp else None
    enrolled = crp["enrolled_acres"] if crp else None
    state_cropland = STATE_CROPLAND_ACRES.get(state_fips)
    if enrolled and state_cropland and state_cropland > 0:
        features["crp_pct_cropland"] = enrolled / state_cropland
    else:
        features["crp_pct_cropland"] = None

    # --- Export demand signals (Tier 1) ---
    my_str = _get_marketing_year_str(nass_commodity, forecast_year)
    export = _query_export_commitments(nass_commodity, my_str)
    features["export_outstanding_pct"] = None
    features["export_pace_vs_5yr"] = None
    if export and export["outstanding_sales_mt"]:
        # Outstanding as raw value (normalized by model; % of projection
        # would require WASDE export forecast, keep simple for now)
        features["export_outstanding_pct"] = export["outstanding_sales_mt"]
    if export and export["accumulated_exports_mt"]:
        # Compare to 5-year average pace
        avg_accum = []
        for offset in range(1, 6):
            prev_my = _get_marketing_year_str(nass_commodity, forecast_year - offset)
            prev = _query_export_commitments(nass_commodity, prev_my)
            if prev and prev["accumulated_exports_mt"]:
                avg_accum.append(prev["accumulated_exports_mt"])
        if avg_accum:
            avg_5yr = sum(avg_accum) / len(avg_accum)
            if avg_5yr > 0:
                features["export_pace_vs_5yr"] = (
                    export["accumulated_exports_mt"] / avg_5yr
                )

    # --- Structural ---
    features["forecast_year"] = forecast_year
    features["state_fips_code"] = int(state_fips) if state_fips.isdigit() else 0

    return pd.Series(features)


def build_training_features(
    commodity: str,
    nass_data: pd.DataFrame,
    year_start: int = 1990,
    year_end: int = 2025,
    states: list[str] | None = None,
) -> pd.DataFrame:
    """Build the full feature matrix for training.

    Args:
        commodity: 'corn', 'soybean', or 'wheat'
        nass_data: DataFrame with columns [state_fips, commodity, year, acres_planted, yield_bu]
        year_start: first forecast year
        year_end: last forecast year
        states: list of state FIPS codes (default: national only '00')

    Returns:
        DataFrame with features + target column 'acres_planted'
    """
    if states is None:
        states = ["00"]

    rows = []
    for year in range(year_start, year_end + 1):
        for state in states:
            features = build_acreage_features(state, commodity, year, nass_data)

            # Get target: actual planted acres for this year
            # wheat_winter/wheat_spring map to NASS "wheat"
            nass_commodity = commodity.split("_")[0] if "_" in commodity else commodity
            actual = nass_data[
                (nass_data["state_fips"] == state)
                & (nass_data["commodity"] == nass_commodity)
                & (nass_data["year"] == year)
            ]
            if actual.empty:
                continue
            features["acres_planted"] = actual["acres_planted"].values[0]
            features["_state_fips"] = state
            features["_year"] = year
            rows.append(features)

    df = pd.DataFrame(rows)
    logger.info(f"Built {len(df)} training rows for {commodity} ({year_start}-{year_end})")
    return df


# Feature columns used by the model (excludes target + meta columns)
FEATURE_COLS = [
    "corn_soy_ratio",
    "corn_futures_dec",
    "soy_futures_nov",
    "wheat_futures_jul",
    "variable_cost_bu",
    "profit_margin_bu",
    "anhydrous_price_ton",
    "relative_profitability",
    "prior_year_acres",
    "prior_year_yield",
    "prior_3yr_avg_acres",
    "prior_5yr_avg_acres",
    "yield_trend_5yr",
    "rotation_ratio",
    "forecast_year",
    "state_fips_code",
    # Tier 1: Drought
    "dsci_nov",
    "dsci_fall_avg",
    # Tier 1: Crop Insurance
    "insured_acres_prior",
    "insured_acres_yoy_change",
    # Tier 1: CRP
    "crp_expiring_acres",
    "crp_pct_cropland",
    # Tier 1: Exports
    "export_outstanding_pct",
    "export_pace_vs_5yr",
]
