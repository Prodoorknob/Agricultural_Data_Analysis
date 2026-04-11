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
}


def clear_query_caches():
    """Clear all LRU caches — call at start of each training run."""
    _query_futures_settlement.cache_clear()
    _query_ers_cost.cache_clear()
    _query_fertilizer_price.cache_clear()
    get_november_price_ratio.cache_clear()


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
    decision_date = date(forecast_year - 1, 11, 1)
    features = {}

    # --- Price signals ---
    features["corn_soy_ratio"] = get_november_price_ratio(forecast_year)

    corn_dec = _query_futures_settlement("corn", decision_date, f"{forecast_year - 1}-12")
    soy_nov = _query_futures_settlement("soybean", decision_date, f"{forecast_year - 1}-11")
    # Use December wheat (available in November) instead of July (too far out)
    wheat_dec = _query_futures_settlement("wheat", decision_date, f"{forecast_year - 1}-12")
    if wheat_dec is None:
        # Fallback: try nearest available wheat contract
        wheat_dec = _query_futures_settlement("wheat", decision_date, f"{forecast_year}-03")

    features["corn_futures_dec"] = corn_dec
    features["soy_futures_nov"] = soy_nov
    features["wheat_futures_jul"] = wheat_dec  # keep column name for model compat

    # --- Cost structure ---
    cost_year = forecast_year - 1
    var_cost = _query_ers_cost(commodity, cost_year, "variable_cost_per_bu")
    features["variable_cost_bu"] = var_cost

    own_futures = {
        "corn": corn_dec, "soybean": soy_nov, "wheat": wheat_dec,
    }.get(commodity)
    features["profit_margin_bu"] = (
        (own_futures - var_cost) if own_futures and var_cost else None
    )

    features["anhydrous_price_ton"] = _query_fertilizer_price(
        decision_date, "anhydrous_ammonia_ton"
    )

    # --- Relative crop profitability (corn vs soy) ---
    if commodity in ("corn", "soybean"):
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
            & (nass_data["commodity"] == commodity)
        ].sort_values("year")

        prior = state_crop[state_crop["year"] == forecast_year - 1]
        features["prior_year_acres"] = (
            prior["acres_planted"].values[0] if len(prior) else None
        )
        features["prior_year_yield"] = (
            prior["yield_bu"].values[0] if len(prior) and "yield_bu" in prior.columns else None
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
        features["prior_5yr_avg_acres"] = None
        features["yield_trend_5yr"] = None
        features["rotation_ratio"] = None

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
            actual = nass_data[
                (nass_data["state_fips"] == state)
                & (nass_data["commodity"] == commodity)
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
    "prior_5yr_avg_acres",
    "yield_trend_5yr",
    "rotation_ratio",
    "forecast_year",
    "state_fips_code",
]
