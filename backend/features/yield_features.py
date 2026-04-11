"""Feature engineering for county-level crop yield prediction.

Builds the 7-feature vector per (fips, crop, crop_year, week):
    1. gdd_ytd — Growing Degree Days accumulated from planting date
    2. cci_cumul — Cumulative Crop Condition Index (NASS weekly ratings)
    3. precip_deficit — Cumulative actual precip minus 30-yr normal (mm)
    4. vpd_stress_days — Count of days with VPD > 2.0 kPa
    5. drought_d3d4_pct — Percent county area in D3+D4 drought
    6. soil_awc — Available Water Capacity (cm/cm, SSURGO static)
    7. soil_drain — Drainage class 1-8 (SSURGO static)

Strict temporal integrity: no feature uses data beyond as_of_date.

Usage:
    # Build features for one county
    row = build_weekly_features("19153", "corn", 2025, 15, date(2025, 8, 1))

    # Build full training matrix
    df = build_training_matrix("corn", range(2005, 2024), week=15)

    # Pipeline CLI: persist features to DB
    python -m backend.features.yield_features --persist --crop corn --year 2026 --week 15
"""

import argparse
import csv
import glob
import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from backend.etl.common import get_sync_session, setup_logging

logger = setup_logging("yield_features")

FEATURE_COLS = [
    "gdd_ytd",
    "cci_cumul",
    "precip_deficit",
    "vpd_stress_days",
    "drought_d3d4_pct",
    "soil_awc",
    "soil_drain",
]

# Approximate planting dates (day of year) by crop × region.
# Used to compute week-of-season indexing.
# Corn: ~April 20 (DOY 110) in central Corn Belt
# Soybean: ~May 5 (DOY 125)
# Winter wheat: planted Sept prior year, key period starts ~March 1 (DOY 60)
PLANTING_DOY = {
    "corn": 110,       # April 20
    "soybean": 125,    # May 5
    "wheat": 60,       # March 1 (start of spring growth for winter wheat)
}

DATA_DIR = Path(__file__).parent.parent / "etl" / "data"


def week_to_date_range(crop: str, crop_year: int, week: int) -> tuple[date, date]:
    """Convert (crop, crop_year, week) to a date range.

    Returns (planting_date, as_of_date) where as_of_date is the end of the
    given week of the growing season.
    """
    planting_doy = PLANTING_DOY.get(crop, 110)
    planting_date = date(crop_year, 1, 1) + timedelta(days=planting_doy - 1)
    as_of_date = planting_date + timedelta(weeks=week)
    return planting_date, as_of_date


# ---- GDD: Growing Degree Days ----

def compute_gdd_ytd(
    fips: str,
    crop: str,
    crop_year: int,
    week: int,
    weather_data: pd.DataFrame | None = None,
) -> float | None:
    """Compute accumulated GDD from planting date through end of given week.

    GDD = Σ max(0, (TMAX + TMIN)/2 - 50°F) where temps in Fahrenheit.
    """
    planting_date, as_of_date = week_to_date_range(crop, crop_year, week)

    if weather_data is not None and not weather_data.empty:
        df = weather_data[
            (weather_data["fips"] == fips) &
            (weather_data["date"] >= str(planting_date)) &
            (weather_data["date"] <= str(as_of_date))
        ]
        if df.empty:
            return None

        # Try NOAA data first (Fahrenheit), then NASA POWER (Celsius -> Fahrenheit)
        if "tmax_f" in df.columns and df["tmax_f"].notna().any():
            gdd_daily = ((df["tmax_f"] + df["tmin_f"]) / 2 - 50).clip(lower=0)
        elif "tmax_c" in df.columns:
            tmax_f = df["tmax_c"] * 9 / 5 + 32
            tmin_f = df["tmin_c"] * 9 / 5 + 32
            gdd_daily = ((tmax_f + tmin_f) / 2 - 50).clip(lower=0)
        else:
            return None

        return round(float(gdd_daily.sum()), 1)

    return None


# ---- CCI: Crop Condition Index ----

def compute_cci_cumul(
    fips: str,
    crop: str,
    crop_year: int,
    week: int,
    conditions_data: pd.DataFrame | None = None,
) -> float | None:
    """Compute cumulative CCI from week 1 to given week.

    CCI per week = 2*(%Excellent) + 1*(%Good) + 0*(%Fair) - 1*(%Poor) - 2*(%Very Poor)
    Cumulative CCI = sum of weekly CCI values.
    State-level data is used as proxy for county (same state).
    """
    state_fips = fips[:2]

    if conditions_data is not None and not conditions_data.empty:
        # Map commodity names
        comm_map = {"corn": "CORN", "soybean": "SOYBEANS", "wheat": "WHEAT"}
        nass_commodity = comm_map.get(crop, crop.upper())

        df = conditions_data[
            (conditions_data["state_fips"] == state_fips) &
            (conditions_data["commodity"] == nass_commodity) &
            (conditions_data["week_num"].notna()) &
            (conditions_data["week_num"] <= week)
        ]
        if df.empty:
            return None

        return round(float(df["cci"].sum()), 1)

    return None


# ---- Precip Deficit ----

def compute_precip_deficit(
    fips: str,
    crop: str,
    crop_year: int,
    week: int,
    weather_data: pd.DataFrame | None = None,
    normals: dict[tuple[str, int], float] | None = None,
) -> float | None:
    """Compute cumulative precipitation deficit vs 30-year normal (mm).

    deficit = actual_precip - normal_precip for the growing season so far.
    Negative = drier than normal.
    """
    planting_date, as_of_date = week_to_date_range(crop, crop_year, week)

    if weather_data is None or weather_data.empty:
        return None

    df = weather_data[
        (weather_data["fips"] == fips) &
        (weather_data["date"] >= str(planting_date)) &
        (weather_data["date"] <= str(as_of_date))
    ]

    if df.empty:
        return None

    # Actual precipitation (convert inches to mm if NOAA data)
    if "prcp_in" in df.columns and df["prcp_in"].notna().any():
        actual_mm = df["prcp_in"].fillna(0).sum() * 25.4
    else:
        return None

    # Normal precipitation for the months covered
    if normals:
        normal_mm = 0.0
        current = planting_date
        while current <= as_of_date:
            key = (fips, current.month)
            monthly_normal = normals.get(key, 75.0)  # default ~3 inches/month
            # Prorate for partial months
            days_in_month = 30
            normal_mm += monthly_normal / days_in_month
            current += timedelta(days=1)
    else:
        # Fallback: assume 3 inches/month (76mm) as rough US average
        days_covered = (as_of_date - planting_date).days
        normal_mm = days_covered * 76.0 / 30.0

    return round(actual_mm - normal_mm, 1)


# ---- VPD Stress Days ----

def compute_vpd_stress_days(
    fips: str,
    crop: str,
    crop_year: int,
    week: int,
    nasa_data: pd.DataFrame | None = None,
) -> int | None:
    """Count days with VPD > 2.0 kPa during the growing season up to given week."""
    planting_date, as_of_date = week_to_date_range(crop, crop_year, week)

    if nasa_data is None or nasa_data.empty:
        return None

    df = nasa_data[
        (nasa_data["fips"] == fips) &
        (nasa_data["date"] >= str(planting_date)) &
        (nasa_data["date"] <= str(as_of_date)) &
        (nasa_data["vpd_kpa"].notna())
    ]

    if df.empty:
        return None

    return int((df["vpd_kpa"] > 2.0).sum())


# ---- Drought ----

def get_drought_d3d4(
    fips: str,
    crop_year: int,
    week: int,
    drought_data: pd.DataFrame | None = None,
) -> float | None:
    """Get the latest D3+D4 drought percentage for a county at the given week."""
    if drought_data is None or drought_data.empty:
        return None

    _, as_of_date = week_to_date_range("corn", crop_year, week)  # crop doesn't matter for drought

    df = drought_data[
        (drought_data["fips"] == fips) &
        (drought_data["date"] <= str(as_of_date))
    ].sort_values("date", ascending=False)

    if df.empty:
        return None

    return round(float(df.iloc[0]["d3d4_pct"]), 2)


# ---- Soil (static) ----

@lru_cache(maxsize=4096)
def get_soil_features(fips: str) -> tuple[float | None, int | None]:
    """Get AWC and drainage class from soil_features table."""
    try:
        session = get_sync_session()
        from backend.models.db_tables import SoilFeature
        from sqlalchemy import select

        result = session.execute(
            select(SoilFeature.awc_cm, SoilFeature.drain_class)
            .where(SoilFeature.fips == fips)
        ).first()
        session.close()

        if result:
            awc = float(result[0]) if result[0] is not None else None
            drain = int(result[1]) if result[1] is not None else None
            return awc, drain
    except Exception:
        pass
    return None, None


# ---- Main feature builders ----

def build_weekly_features(
    fips: str,
    crop: str,
    crop_year: int,
    week: int,
    weather_data: pd.DataFrame | None = None,
    nasa_data: pd.DataFrame | None = None,
    conditions_data: pd.DataFrame | None = None,
    drought_data: pd.DataFrame | None = None,
    normals: dict | None = None,
) -> pd.Series:
    """Build a single feature row for one (fips, crop, crop_year, week).

    All data sources are passed in to avoid repeated I/O during batch operations.
    """
    gdd = compute_gdd_ytd(fips, crop, crop_year, week, weather_data)
    cci = compute_cci_cumul(fips, crop, crop_year, week, conditions_data)
    precip = compute_precip_deficit(fips, crop, crop_year, week, weather_data, normals)
    vpd = compute_vpd_stress_days(fips, crop, crop_year, week, nasa_data)
    drought = get_drought_d3d4(fips, crop_year, week, drought_data)
    awc, drain = get_soil_features(fips)

    return pd.Series({
        "gdd_ytd": gdd,
        "cci_cumul": cci,
        "precip_deficit": precip,
        "vpd_stress_days": vpd,
        "drought_d3d4_pct": drought,
        "soil_awc": awc,
        "soil_drain": drain,
    })


def build_training_matrix(
    crop: str,
    year_range: range,
    week: int,
    county_fips_list: list[str] | None = None,
    weather_data: pd.DataFrame | None = None,
    nasa_data: pd.DataFrame | None = None,
    conditions_data: pd.DataFrame | None = None,
    drought_data: pd.DataFrame | None = None,
    normals: dict | None = None,
    nass_yields: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build full training DataFrame for a given crop and week across all counties and years.

    Returns DataFrame with feature columns + metadata columns (_fips, _crop_year, _yield).
    """
    rows = []

    if county_fips_list is None:
        county_fips_list = _get_ag_county_fips(crop)

    for year in year_range:
        for fips in county_fips_list:
            features = build_weekly_features(
                fips, crop, year, week,
                weather_data, nasa_data, conditions_data, drought_data, normals,
            )

            # Get target yield
            actual_yield = None
            if nass_yields is not None:
                match = nass_yields[
                    (nass_yields["fips"] == fips) &
                    (nass_yields["year"] == year)
                ]
                if not match.empty:
                    actual_yield = float(match.iloc[0]["yield_bu"])

            if actual_yield is None:
                continue  # Skip rows without target

            row = features.to_dict()
            row["_fips"] = fips
            row["_crop_year"] = year
            row["_yield"] = actual_yield
            rows.append(row)

    df = pd.DataFrame(rows)
    logger.info(
        "Built training matrix: %d rows x %d features for %s week %d (%d-%d)",
        len(df), len(FEATURE_COLS), crop, week,
        year_range.start, year_range.stop - 1,
    )
    return df


def _get_ag_county_fips(crop: str) -> list[str]:
    """Get list of county FIPS codes that grow this crop, from county centroids."""
    centroids_path = DATA_DIR / "county_centroids.csv"
    if not centroids_path.exists():
        logger.warning("County centroids not found. Returning empty list.")
        return []

    fips_list = []
    with open(centroids_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Filter to continental US ag states (exclude AK=02, HI=15, territories)
            state_fips = row["state_fips"]
            if state_fips not in ("02", "15", "11", "60", "66", "69", "72", "78"):
                fips_list.append(row["fips"])
    return fips_list


def persist_features(
    crop: str,
    crop_year: int,
    week: int,
    features_df: pd.DataFrame,
):
    """Upsert computed features to the feature_weekly DB table."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from backend.models.db_tables import FeatureWeekly

    session = get_sync_session()
    count = 0

    try:
        for _, row in features_df.iterrows():
            vals = {
                "fips": row.get("_fips", ""),
                "crop": crop,
                "crop_year": crop_year,
                "week": week,
                "gdd_ytd": _safe_numeric(row.get("gdd_ytd")),
                "cci_cumul": _safe_numeric(row.get("cci_cumul")),
                "precip_deficit": _safe_numeric(row.get("precip_deficit")),
                "vpd_stress_days": _safe_int(row.get("vpd_stress_days")),
                "drought_d3d4_pct": _safe_numeric(row.get("drought_d3d4_pct")),
                "soil_awc": _safe_numeric(row.get("soil_awc")),
                "soil_drain": _safe_int(row.get("soil_drain")),
            }
            stmt = pg_insert(FeatureWeekly).values(**vals)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_feature_weekly",
                set_={k: v for k, v in vals.items() if k not in ("fips", "crop", "crop_year", "week")},
            )
            session.execute(stmt)
            count += 1

        session.commit()
        logger.info("Persisted %d feature rows for %s %d week %d", count, crop, crop_year, week)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _safe_numeric(val) -> float | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return float(val)


def _safe_int(val) -> int | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return int(val)


def clear_caches():
    """Clear LRU caches for fresh queries."""
    get_soil_features.cache_clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build and persist yield features")
    parser.add_argument("--crop", default="all", help="corn|soybean|wheat|all")
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--week", type=int, help="Week of season (1-30)")
    parser.add_argument("--persist", action="store_true", help="Write features to DB")
    args = parser.parse_args()

    logger.info("Yield feature builder — crop=%s year=%d week=%s persist=%s",
                args.crop, args.year, args.week, args.persist)
    logger.info("Feature columns: %s", FEATURE_COLS)
    logger.info("To build features, run the ETL scripts first to populate raw data.")
