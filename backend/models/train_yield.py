"""Training script for crop yield prediction models — with weather features.

Trains 60 LightGBM quantile models (3 crops × 20 weeks).
Integrates GHCN daily weather data to compute week-specific GDD and precip deficit,
combined with NASS historical yield features.

Target reformulation (default ON, see USE_ANOMALY_TARGET):
  Models predict ``yield_residual = yield_bu - county_5yr_prior_mean(fips, year)``.
  This breaks the cross-county leakage previously caused by ``year`` being the
  top-importance feature: corn-belt time trends were being applied to SE
  Atlantic counties (NC corn 2024 outlier — see
  research/yield-model-nc-2024-investigation.md). The 5yr baseline is added
  back at predict time.

Features per (fips, year, week):
  NASS history:
  - county_yield_trend  (slope of prior-year yields, structural)
  - prior_year_yield    (last-year realized — reused as a robustness anchor)
  - county_yield_std    (variability)

  Weather anomalies vs county climatology computed from training years:
  - gdd_anom            (GDD minus county/week climatology)
  - tmax_anom           (avg max temp minus county/week climatology)
  - precip_anom_in      (precip total minus county/week climatology)
  - precip_deficit_in   (PRISM normals based deficit, kept as redundant signal)
  - hot_days            (count of days >95F — kept as absolute heat-stress count)

  County drought (loaded from USDM cache if available):
  - drought_d3d4_pct    (D3+D4 percent area at most-recent USDM Thursday)

  ``year`` is intentionally REMOVED from the feature set — its previous role
  as the dominant LightGBM split was the root cause of the NC 2024 mode of
  failure documented in research/yield-model-nc-2024-investigation.md.

Usage:
    python -m backend.models.train_yield
    python -m backend.models.train_yield --commodity corn --week 15 --skip-cv
    python -m backend.models.train_yield --upload-s3
    python -m backend.models.train_yield --absolute-target  # legacy mode
    python -m backend.models.train_yield --prune-old-versions  # clean stale rows
"""

import argparse
import csv
import json
import os
import time as _time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from backend.etl.common import setup_logging
from backend.models.yield_model import YieldModel, compute_baselines, compute_rrmse

logger = setup_logging("train_yield")

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts" / "yield"
LOCAL_DATA_DIR = Path(__file__).parent.parent / "etl" / "data"
NASS_CACHE_DIR = LOCAL_DATA_DIR / "nass_cache"
GHCN_DIR = LOCAL_DATA_DIR / "ghcn_processed"
PRISM_PATH = LOCAL_DATA_DIR / "prism_normals.csv"
DROUGHT_HISTORY_PATH = LOCAL_DATA_DIR / "drought_history.parquet"
HURDAT2_PATH = LOCAL_DATA_DIR / "hurdat2.parquet"
COUNTY_CENTROIDS_PATH = LOCAL_DATA_DIR / "county_centroids.csv"
STORM_FLOODS_PATH = LOCAL_DATA_DIR / "storm_floods.parquet"


def _resolve_ghcn_path() -> Path:
    """Pick the latest ``county_weather_2000_<YYYY>.parquet``.

    The GHCN cache filename is suffixed by the latest year of coverage.
    ``backend/etl/extend_ghcn_to_current.py`` writes
    ``county_weather_2000_<end-year>.parquet`` and leaves earlier-year files
    in place. This resolver lets train + inference always pick the freshest
    cache without code edits each year.
    """
    candidates = sorted(GHCN_DIR.glob("county_weather_2000_*.parquet"))
    if candidates:
        # Highest year suffix sorts last alphabetically (e.g. 2025 < 2026).
        return candidates[-1]
    return GHCN_DIR / "county_weather_2000_2025.parquet"  # legacy fallback


GHCN_PATH = _resolve_ghcn_path()

COMMODITIES = {"corn": "CORN", "soybean": "SOYBEANS", "wheat": "WHEAT"}
WEEKS = range(1, 21)  # 20 weeks of growing season

# Planting day-of-year by crop (from yield_features.py)
PLANTING_DOY = {"corn": 110, "soybean": 125, "wheat": 60}

# Training periods
TRAIN_END = 2019
VAL_START, VAL_END = 2020, 2022
TEST_START, TEST_END = 2023, 2024

# Baseline gate: model must beat county historical mean by >=10% relative improvement
BASELINE_GATE_PCT = 10.0

# Target reformulation. When True, models predict yield - county_5yr_mean
# (see module docstring + research/yield-model-nc-2024-investigation.md).
USE_ANOMALY_TARGET = True
BASELINE_LOOKBACK_YEARS = 5

# New anomaly-based feature column ordering (used by both training and inference).
WEATHER_ANOM_COLS = ["gdd_anom", "tmax_anom", "precip_anom_in", "precip_deficit_in", "hot_days"]
DROUGHT_COLS = ["drought_d3d4_pct"]
NASS_HIST_COLS = ["county_yield_trend", "prior_year_yield", "county_yield_std"]


# ---- Data loaders ----

def load_nass_county_yields(
    commodity_nass: str,
    local_only: bool = False,
) -> pd.DataFrame:
    """Load county-level NASS yield data from parquet files."""
    cache_path = NASS_CACHE_DIR / f"{commodity_nass.lower()}_county_yields.csv"
    if cache_path.exists():
        logger.info("Loading cached county yields from %s", cache_path)
        df = pd.read_csv(cache_path, dtype={"fips": str, "state_fips": str})
        return df

    if not local_only:
        _download_county_parquets()

    all_rows = []
    parquet_dir = LOCAL_DATA_DIR / "county_parquets"

    if not parquet_dir.exists():
        logger.error("County parquet directory not found at %s", parquet_dir)
        return pd.DataFrame()

    for pq_file in sorted(parquet_dir.glob("*.parquet")):
        if pq_file.name.startswith("_"):
            continue
        try:
            df = pd.read_parquet(pq_file)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", pq_file, exc)
            continue

        # Wheat uses class_desc='WINTER'/'SPRING', others use 'ALL CLASSES'
        class_filter = (
            df["class_desc"].isin(["ALL CLASSES", "WINTER", "SPRING, (EXCL DURUM)"])
            if commodity_nass == "WHEAT"
            else (df["class_desc"] == "ALL CLASSES")
        )
        yield_df = df[
            (df["agg_level_desc"] == "COUNTY") &
            (df["statisticcat_desc"] == "YIELD") &
            (df["commodity_desc"] == commodity_nass) &
            class_filter &
            (df["unit_desc"].str.contains("BU / ACRE", case=False, na=False)) &
            (df["domain_desc"] == "TOTAL") &
            (df["freq_desc"] == "ANNUAL")
        ].copy()

        if yield_df.empty:
            continue

        yield_df["fips"] = (
            yield_df["state_fips_code"].astype(str).str.zfill(2) +
            yield_df["county_code"].astype(str).str.zfill(3)
        )

        for _, row in yield_df.iterrows():
            try:
                val = float(str(row.get("value_num", row.get("Value", ""))).replace(",", ""))
            except (ValueError, TypeError):
                continue
            if val <= 0 or np.isnan(val):
                continue
            all_rows.append({
                "fips": row["fips"],
                "year": int(row["year"]),
                "yield_bu": val,
                "state_fips": row["fips"][:2],
            })

    result = pd.DataFrame(all_rows).drop_duplicates(subset=["fips", "year"], keep="last")
    logger.info("Loaded %d county yield records for %s", len(result), commodity_nass)

    NASS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(cache_path, index=False)
    return result


def _download_county_parquets():
    """Download county parquets from S3."""
    import subprocess
    dest = LOCAL_DATA_DIR / "county_parquets"
    dest.mkdir(parents=True, exist_ok=True)
    s3_prefix = "s3://usda-analysis-datasets/survey_datasets/partitioned_states_counties/"
    logger.info("Syncing county parquets from S3...")
    try:
        subprocess.run(["aws", "s3", "sync", s3_prefix, str(dest), "--quiet"],
                       check=True, timeout=300)
        logger.info("S3 sync complete to %s", dest)
    except Exception as exc:
        logger.warning("S3 sync failed: %s", exc)


def load_weather_data() -> pd.DataFrame:
    """Load GHCN daily weather data (16M rows, ~1s)."""
    if not GHCN_PATH.exists():
        logger.warning("GHCN weather data not found at %s", GHCN_PATH)
        return pd.DataFrame()
    t0 = _time.time()
    df = pd.read_parquet(GHCN_PATH)
    logger.info("Loaded GHCN weather: %d rows in %.1fs", len(df), _time.time() - t0)
    return df


def load_prism_normals() -> dict[tuple[str, int], float]:
    """Load PRISM monthly precipitation normals. Returns {(fips, month): precip_in}."""
    if not PRISM_PATH.exists():
        logger.warning("PRISM normals not found at %s", PRISM_PATH)
        return {}
    result = {}
    with open(PRISM_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[(row["fips"], int(row["month"]))] = float(row["precip_normal_in"])
    logger.info("Loaded PRISM normals: %d entries", len(result))
    return result


def load_hurdat2() -> pd.DataFrame:
    """Load NOAA HURDAT2 Atlantic tropical cyclone tracks from local parquet.

    Built by ``backend.etl.backfill_hurdat2``. Returns columns
    ``[storm_id, storm_name, date, status, is_landfall, lat, lon,
    max_wind_kt, min_pressure_mb]``. Empty DataFrame if cache missing —
    callers must handle gracefully so models can still train without
    hurricane features.
    """
    if not HURDAT2_PATH.exists():
        logger.warning(
            "HURDAT2 cache not found at %s — hurricane features will all be "
            "NaN. Run `python -m backend.etl.backfill_hurdat2`.",
            HURDAT2_PATH,
        )
        return pd.DataFrame(columns=[
            "storm_id", "storm_name", "date", "status",
            "is_landfall", "lat", "lon", "max_wind_kt",
        ])
    df = pd.read_parquet(HURDAT2_PATH)
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    logger.info(
        "Loaded HURDAT2: %d track points, %d storms, %d..%d",
        len(df),
        df["storm_id"].nunique() if "storm_id" in df.columns else 0,
        df["date"].dt.year.min() if len(df) else 0,
        df["date"].dt.year.max() if len(df) else 0,
    )
    return df


def load_county_centroids() -> pd.DataFrame:
    """Load county centroid table for great-circle distance computations."""
    if not COUNTY_CENTROIDS_PATH.exists():
        logger.warning(
            "County centroids not found at %s — hurricane features will be skipped.",
            COUNTY_CENTROIDS_PATH,
        )
        return pd.DataFrame(columns=["fips", "lat", "lon"])
    df = pd.read_csv(COUNTY_CENTROIDS_PATH, dtype={"fips": str})
    df["fips"] = df["fips"].str.zfill(5)
    logger.info("Loaded county centroids: %d counties", len(df))
    return df[["fips", "lat", "lon"]]


def load_storm_floods() -> pd.DataFrame:
    """Load NOAA Storm Events flood/flash-flood records from local parquet.

    Built by ``backend.etl.backfill_storm_events``. Returns columns
    ``[fips, event_date, event_type, damage_property_usd]``. Empty if
    cache missing — flood features become NaN downstream.
    """
    if not STORM_FLOODS_PATH.exists():
        logger.warning(
            "Storm Events cache not found at %s — flood features will all be "
            "NaN. Run `python -m backend.etl.backfill_storm_events`.",
            STORM_FLOODS_PATH,
        )
        return pd.DataFrame(columns=["fips", "event_date", "event_type", "damage_property_usd"])
    df = pd.read_parquet(STORM_FLOODS_PATH)
    if "event_date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["event_date"]):
        df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")
    logger.info(
        "Loaded NOAA Storm Events floods: %d rows, %d counties, %d..%d",
        len(df),
        df["fips"].nunique() if "fips" in df.columns else 0,
        df["event_date"].dt.year.min() if len(df) else 0,
        df["event_date"].dt.year.max() if len(df) else 0,
    )
    return df


def load_drought_history() -> pd.DataFrame:
    """Load county-level USDM drought history from local parquet cache.

    Expected columns: ``fips`` (str, 5-char), ``date`` (datetime64), ``d3d4_pct``
    (float). Built by ``backend.etl.backfill_drought_history`` (separate
    backfill script — fetches one Thursday per growing-season week from the
    USDM API and writes a single parquet).

    Returns an empty DataFrame if the cache file is missing; callers must
    handle that gracefully so models can still train without drought data.
    """
    if not DROUGHT_HISTORY_PATH.exists():
        logger.warning(
            "Drought history not found at %s — drought_d3d4_pct will be null. "
            "Run `python -m backend.etl.backfill_drought_history` to populate.",
            DROUGHT_HISTORY_PATH,
        )
        return pd.DataFrame(columns=["fips", "date", "d3d4_pct"])
    t0 = _time.time()
    df = pd.read_parquet(DROUGHT_HISTORY_PATH)
    if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["fips", "date"])
    df["fips"] = df["fips"].astype(str).str.zfill(5)
    if "d3d4_pct" not in df.columns and {"d3_pct", "d4_pct"}.issubset(df.columns):
        df["d3d4_pct"] = df["d3_pct"].fillna(0) + df["d4_pct"].fillna(0)
    logger.info(
        "Loaded USDM drought history: %d rows (%d counties, %s..%s) in %.1fs",
        len(df),
        df["fips"].nunique(),
        df["date"].min().strftime("%Y-%m-%d") if len(df) else "N/A",
        df["date"].max().strftime("%Y-%m-%d") if len(df) else "N/A",
        _time.time() - t0,
    )
    return df


# ---- Weather feature computation ----

def _compute_normal_precip_per_fips(
    prism_normals: dict[tuple[str, int], float],
    fips_list: list[str],
    season_start_doy: int,
    season_end_doy: int,
) -> dict[str, float]:
    """Sum daily PRISM normals across the season window per FIPS.

    Each day in month M contributes ``monthly_normal[M]/30``. The window is
    fixed across years for a given crop+week, so we precompute it once and
    reuse instead of looping per (fips, year). Returns ``{fips: total_normal_in}``.
    """
    days_per_month = [0] * 13  # 1..12
    start = date(2001, 1, 1) + timedelta(days=season_start_doy - 1)
    end = date(2001, 1, 1) + timedelta(days=min(season_end_doy, 365) - 1)
    cur = start
    while cur <= end:
        days_per_month[cur.month] += 1
        cur += timedelta(days=1)

    out: dict[str, float] = {}
    for fips in fips_list:
        total = 0.0
        for m in range(1, 13):
            d = days_per_month[m]
            if d:
                total += prism_normals.get((fips, m), 0.25) * d / 30.0
        out[fips] = total
    return out


def compute_weather_features(
    weather_df: pd.DataFrame,
    prism_normals: dict,
    crop: str,
    fips_list: list[str],
    year_range: range,
    week: int,
) -> pd.DataFrame:
    """Compute weather features for all (fips, year) at a given week.

    Returns DataFrame with columns: fips, year, gdd_ytd, precip_season_in,
    precip_deficit_in, tmax_avg, hot_days. Anomaly versions
    (gdd_anom / tmax_anom / precip_anom_in) are produced separately by
    ``apply_weather_anomalies`` once the climatology is known.

    Vectorized: a single pandas groupby over (fips, year) replaces the
    nested per-year per-fips Python loop. With ~16M GHCN rows pre-filtered
    to the season window, this runs in a couple of seconds vs ~20 minutes
    for the original implementation.
    """
    if weather_df.empty:
        return pd.DataFrame()

    planting_doy = PLANTING_DOY.get(crop, 110)
    season_start_doy = planting_doy
    season_end_doy = planting_doy + week * 7

    # Filter weather to only the requested counties.
    wx = weather_df[weather_df["fips"].isin(fips_list)].copy()
    if wx.empty:
        return pd.DataFrame()

    # Parse date once. Cache results because train_yield calls this 20 times
    # per crop with the same weather_df slice — but recomputing is cheap.
    if not pd.api.types.is_datetime64_any_dtype(wx["date"]):
        wx["date_parsed"] = pd.to_datetime(wx["date"], format="%Y-%m-%d", errors="coerce")
    else:
        wx["date_parsed"] = wx["date"]
    wx["year_val"] = wx["date_parsed"].dt.year
    wx["doy"] = wx["date_parsed"].dt.dayofyear

    season_mask = (
        wx["year_val"].isin(list(year_range))
        & (wx["doy"] >= season_start_doy)
        & (wx["doy"] <= season_end_doy)
    )
    season = wx.loc[season_mask, ["fips", "year_val", "tmax_f", "tmin_f", "prcp_in"]]
    if season.empty:
        return pd.DataFrame()

    # Daily-level derivations
    season = season.copy()
    season["gdd_daily"] = ((season["tmax_f"] + season["tmin_f"]) / 2 - 50).clip(lower=0)
    season["hot_flag"] = (season["tmax_f"] > 95).astype("int8")
    # Mark valid temperature rows for the >=5-day requirement
    season["temp_valid"] = (season["tmax_f"].notna() & season["tmin_f"].notna()).astype("int8")

    grouped = (
        season.groupby(["fips", "year_val"], observed=True)
        .agg(
            gdd_ytd=("gdd_daily", "sum"),
            precip_season_in=("prcp_in", "sum"),
            tmax_avg=("tmax_f", "mean"),
            hot_days=("hot_flag", "sum"),
            n_temp_days=("temp_valid", "sum"),
        )
        .reset_index()
        .rename(columns={"year_val": "year"})
    )

    # Drop county-years with too little observed temperature data (matches
    # the previous "len(temp_valid) < 5" gate).
    grouped = grouped[grouped["n_temp_days"] >= 5].drop(columns=["n_temp_days"])

    # Precip deficit vs PRISM normals — precomputed once per FIPS for the
    # fixed season window (same across all years).
    normal_lookup = _compute_normal_precip_per_fips(
        prism_normals, fips_list, season_start_doy, season_end_doy,
    )
    grouped["precip_deficit_in"] = (
        grouped["precip_season_in"] - grouped["fips"].map(normal_lookup).fillna(0.0)
    )

    # Round for stable artifact output / human inspection
    grouped["gdd_ytd"] = grouped["gdd_ytd"].round(1)
    grouped["precip_season_in"] = grouped["precip_season_in"].round(2)
    grouped["precip_deficit_in"] = grouped["precip_deficit_in"].round(2)
    grouped["tmax_avg"] = grouped["tmax_avg"].round(1)
    grouped["hot_days"] = grouped["hot_days"].astype(int)

    return grouped[
        ["fips", "year", "gdd_ytd", "precip_season_in",
         "precip_deficit_in", "tmax_avg", "hot_days"]
    ]


def compute_climatology(
    wx_features: pd.DataFrame,
    train_end: int = TRAIN_END,
) -> dict[str, dict[str, float]]:
    """Compute per-county climatology from training years.

    For each county, average the absolute weather features over years
    ``year <= train_end``. This isolates the model from same-year leakage
    while still letting a NC county's "is 2024 unusually hot for *here*"
    signal show up as an anomaly.

    Returns ``{fips: {"gdd_climo", "tmax_climo", "precip_climo"}}``. Counties
    with no training-year coverage are omitted (caller treats the missing
    anomaly as NaN, which LightGBM handles natively).
    """
    if wx_features.empty:
        return {}
    train = wx_features[wx_features["year"] <= train_end]
    if train.empty:
        logger.warning(
            "No training-year weather rows (year <= %d) for climatology; "
            "anomaly features will all be NaN", train_end,
        )
        return {}
    grouped = train.groupby("fips").agg(
        gdd_climo=("gdd_ytd", "mean"),
        tmax_climo=("tmax_avg", "mean"),
        precip_climo=("precip_season_in", "mean"),
    )
    return {
        fips: {
            "gdd_climo": float(row["gdd_climo"]),
            "tmax_climo": float(row["tmax_climo"]),
            "precip_climo": float(row["precip_climo"]),
        }
        for fips, row in grouped.iterrows()
    }


def apply_weather_anomalies(
    wx_features: pd.DataFrame,
    climatology: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """Add ``gdd_anom``, ``tmax_anom``, ``precip_anom_in`` columns.

    Anomaly = current value - county climatology. Counties absent from
    ``climatology`` get NaN (LightGBM handles missing values natively).
    """
    if wx_features.empty:
        return wx_features

    result = wx_features.copy()
    gdd_climo_map = {f: c["gdd_climo"] for f, c in climatology.items()}
    tmax_climo_map = {f: c["tmax_climo"] for f, c in climatology.items()}
    precip_climo_map = {f: c["precip_climo"] for f, c in climatology.items()}

    result["gdd_anom"] = (
        result["gdd_ytd"] - result["fips"].map(gdd_climo_map)
    ).round(1)
    result["tmax_anom"] = (
        result["tmax_avg"] - result["fips"].map(tmax_climo_map)
    ).round(1)
    result["precip_anom_in"] = (
        result["precip_season_in"] - result["fips"].map(precip_climo_map)
    ).round(2)
    return result


def _haversine_km(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Vectorized great-circle distance in km between two arrays of points."""
    R = 6371.0
    lat1r = np.radians(lat1)
    lat2r = np.radians(lat2)
    dlat = lat2r - lat1r
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def attach_hurricane_features(
    feature_df: pd.DataFrame,
    hurdat_df: pd.DataFrame,
    county_centroids: pd.DataFrame,
    crop: str,
    week: int,
    proximity_km: float = 200.0,
) -> pd.DataFrame:
    """Attach tropical-cyclone proximity features per (fips, year).

    Single feature on purpose:
      - ``tropical_track_pts_within_200km`` — count of TS/HU/SS track
        points within ``proximity_km`` of the county centroid during the
        ``[planting_doy, planting_doy + week*7]`` window.

    A first pass added distance + wind, but the heavy NaN distribution
    (most counties never see a tropical system in any growing season)
    let LightGBM split on noise and uniformly hurt validation+test.
    Keeping a single 0-indexed integer feature means the tree only
    splits when there's a real signal: most rows are 0 and a small
    minority have positive counts.

    Counties without a centroid receive NaN; the rest get the integer
    count (0 when no storm activity is in window). The lingering-storm
    case (Debby in NC 2024) shows up as 1+ track points within 200 km.
    """
    out = feature_df.copy()
    out["tropical_track_pts_within_200km"] = np.nan

    if hurdat_df.empty or county_centroids.empty:
        return out

    qualifying = hurdat_df[hurdat_df["status"].isin(["TS", "HU", "SS"])]
    if qualifying.empty:
        return out

    planting_doy = PLANTING_DOY.get(crop, 110)
    season_end_doy = planting_doy + week * 7

    centroid_lookup = dict(zip(
        county_centroids["fips"], zip(county_centroids["lat"], county_centroids["lon"])
    ))

    qualifying = qualifying.assign(
        year=qualifying["date"].dt.year, doy=qualifying["date"].dt.dayofyear,
    )
    tracks_by_year: dict[int, pd.DataFrame] = {}
    for yr, grp in qualifying.groupby("year"):
        season = grp[(grp["doy"] >= planting_doy) & (grp["doy"] <= season_end_doy)]
        if not season.empty:
            tracks_by_year[int(yr)] = season

    n_within = np.full(len(out), np.nan)
    for i, (fips, year) in enumerate(zip(out["fips"], out["year"])):
        centroid = centroid_lookup.get(str(fips))
        if centroid is None:
            continue
        # County is in the centroid universe — start with a true zero and
        # only increment when nearby tracks exist.
        season_tracks = tracks_by_year.get(int(year))
        if season_tracks is None or season_tracks.empty:
            n_within[i] = 0
            continue
        clat, clon = centroid
        track_lat = season_tracks["lat"].to_numpy()
        track_lon = season_tracks["lon"].to_numpy()
        dists = _haversine_km(
            np.full(len(track_lat), clat),
            np.full(len(track_lat), clon),
            track_lat, track_lon,
        )
        n_within[i] = int((dists <= proximity_km).sum())

    out["tropical_track_pts_within_200km"] = n_within
    return out


def attach_flood_features(
    feature_df: pd.DataFrame,
    flood_df: pd.DataFrame,
    crop: str,
    week: int,
) -> pd.DataFrame:
    """Attach flood-event count per (fips, year) for the season window.

    Single feature:
      - ``flood_event_count`` — number of NOAA Storm Events flood records
        (Flood / Flash Flood / Heavy Rain / Tropical Storm / Hurricane /
        Storm Surge / Coastal Flood) for the county within the season
        window.

    Damage USD was tested but its heavy-tailed distribution + log
    transform let LightGBM split on damage-magnitude noise rather than
    presence/absence. Keeping a single integer count keeps the signal
    clean: 0 means "no flood reported in window," ≥1 means a real
    event. True zeros (not missing) for counties without events.
    """
    out = feature_df.copy()
    out["flood_event_count"] = 0.0

    if flood_df.empty:
        return out

    planting_doy = PLANTING_DOY.get(crop, 110)
    season_end_doy = planting_doy + week * 7

    flood = flood_df.copy()
    flood["year"] = flood["event_date"].dt.year
    flood["doy"] = flood["event_date"].dt.dayofyear
    flood = flood[(flood["doy"] >= planting_doy) & (flood["doy"] <= season_end_doy)]
    if flood.empty:
        return out

    agg = (
        flood.groupby(["fips", "year"], observed=True)
        .agg(flood_event_count=("event_type", "size"))
        .reset_index()
    )

    out = out.drop(columns=["flood_event_count"]).merge(
        agg, on=["fips", "year"], how="left",
    )
    out["flood_event_count"] = out["flood_event_count"].fillna(0).astype(float)
    return out


def attach_drought_features(
    feature_df: pd.DataFrame,
    drought_df: pd.DataFrame,
    crop: str,
    week: int,
) -> pd.DataFrame:
    """Attach ``drought_d3d4_pct`` to a (fips, year) feature DataFrame.

    Looks up the most recent USDM Thursday on or before the season-end date
    for that (crop, year, week) and copies its D3+D4 percent area into the
    feature row. Rows without a covering USDM observation get NaN.

    Vectorized via ``pd.merge_asof`` (per-fips backward lookup). Drops the
    quadratic per-row mask scan that made attach_drought_features dominate
    train_yield wall time when run against the 2.5M-row USDM history.
    """
    if feature_df.empty:
        return feature_df.assign(drought_d3d4_pct=np.nan)

    out = feature_df.copy()
    if drought_df.empty:
        out["drought_d3d4_pct"] = np.nan
        return out

    planting_doy = PLANTING_DOY.get(crop, 110)
    season_end_doy = planting_doy + week * 7

    # Build target_date column (depends on year only since week is fixed
    # for a given call).
    def _safe_target_date(year: int) -> pd.Timestamp:
        try:
            return pd.Timestamp(
                date(int(year), 1, 1) + timedelta(days=min(season_end_doy, 365) - 1)
            )
        except (ValueError, OverflowError):
            return pd.NaT

    # Vectorized via map of unique years -> target dates.
    unique_years = out["year"].astype(int).unique()
    year_to_date = {int(y): _safe_target_date(int(y)) for y in unique_years}
    out["target_date"] = out["year"].astype(int).map(year_to_date)

    # merge_asof requires both sides sorted on the on-key.
    drought = drought_df[["fips", "date", "d3d4_pct"]].copy()
    drought["date"] = pd.to_datetime(drought["date"])
    drought = drought.sort_values(["date"])

    out_sorted = out.sort_values(["target_date", "fips"])
    merged = pd.merge_asof(
        out_sorted,
        drought.rename(columns={"date": "target_date"}),
        on="target_date",
        by="fips",
        direction="backward",
    )
    merged = merged.drop(columns=["target_date"])
    merged.rename(columns={"d3d4_pct": "drought_d3d4_pct"}, inplace=True)
    return merged.reset_index(drop=True)


# ---- Training ----

def train_single_model(
    crop: str,
    week: int,
    nass_yields: pd.DataFrame,
    weather_df: pd.DataFrame,
    prism_normals: dict,
    drought_df: pd.DataFrame | None = None,
    hurdat_df: pd.DataFrame | None = None,
    flood_df: pd.DataFrame | None = None,
    county_centroids: pd.DataFrame | None = None,
    skip_cv: bool = False,
    capture_predictions: bool = False,
    use_anomaly_target: bool = USE_ANOMALY_TARGET,
) -> dict:
    """Train a single YieldModel for (crop, week) with weather features.

    Target reformulation: when ``use_anomaly_target`` is True (default), the
    model is trained on ``yield_bu - county_5yr_prior_mean``; the baseline is
    added back at predict time. Driven by the NC corn 2024 investigation
    (research/yield-model-nc-2024-investigation.md) — eliminates the
    cross-county "year" leakage that pulled SE Atlantic counties toward the
    corn-belt mean.

    If capture_predictions is True, returned dict includes a 'predictions'
    key holding a list of per-row val+test predictions. Each item:
        {forecast_year, fips, model_p50, model_p10, model_p90,
         actual_yield, county_5yr_mean, split}
    Used by the --persist-accuracy flag to populate yield_accuracy (§7.4 WI-3).
    """
    logger.info("=== Training %s week %d (target=%s) ===",
                crop, week, "anomaly" if use_anomaly_target else "absolute")

    # Get list of counties with yield data
    fips_list = nass_yields["fips"].unique().tolist()
    year_range = range(
        max(int(nass_yields["year"].min()), 2000),
        int(nass_yields["year"].max()) + 1,
    )

    # Compute absolute weather features for this crop/week, then derive
    # county-week climatology from training years and convert to anomalies.
    wx_features = compute_weather_features(
        weather_df, prism_normals, crop, fips_list, year_range, week,
    )
    has_weather = not wx_features.empty

    climatology: dict[str, dict[str, float]] = {}
    if has_weather:
        climatology = compute_climatology(wx_features, train_end=TRAIN_END)
        wx_features = apply_weather_anomalies(wx_features, climatology)
        # Attach drought (no-op if drought_df is empty)
        if drought_df is not None and not drought_df.empty:
            wx_features = attach_drought_features(wx_features, drought_df, crop, week)
        else:
            wx_features["drought_d3d4_pct"] = np.nan
        # Attach hurricane proximity (no-op if either input is empty)
        if (
            hurdat_df is not None and not hurdat_df.empty
            and county_centroids is not None and not county_centroids.empty
        ):
            wx_features = attach_hurricane_features(
                wx_features, hurdat_df, county_centroids, crop, week,
            )
        else:
            wx_features["tropical_track_pts_within_200km"] = np.nan
        # Attach NOAA Storm Events flood aggregates (no-op if missing)
        if flood_df is not None and not flood_df.empty:
            wx_features = attach_flood_features(wx_features, flood_df, crop, week)
        else:
            wx_features["flood_event_count"] = 0.0
        wx_lookup = wx_features.set_index(["fips", "year"])
        logger.info(
            "  Weather features: %d (fips,year) pairs; climatology counties=%d; "
            "drought=%s hurdat=%s floods=%s",
            len(wx_features),
            len(climatology),
            bool(drought_df is not None and not drought_df.empty),
            bool(hurdat_df is not None and not hurdat_df.empty),
            bool(flood_df is not None and not flood_df.empty),
        )
    else:
        wx_lookup = None
        logger.info("  No weather features available — using NASS-only features")

    # Build feature rows via grouped, sorted iteration over the yield panel.
    # The previous boolean-mask-per-row scheme was O(N^2) over ~22k rows per
    # crop (5×10^8 ops on the corn panel — minutes per call). Walking each
    # county once amortizes the historical-stat computation.
    features_rows = []
    nass_sorted = nass_yields.sort_values(["fips", "year"], kind="stable")
    for fips_val, grp in nass_sorted.groupby("fips", sort=False):
        years_arr = grp["year"].to_numpy()
        yields_arr = grp["yield_bu"].to_numpy(dtype=float)
        n_rows = len(years_arr)
        if n_rows < 4:
            continue
        for i in range(n_rows):
            if i < 3:  # need ≥3 prior years
                continue
            prior = yields_arr[:i]
            last_n = prior[-BASELINE_LOOKBACK_YEARS:]
            features_rows.append({
                "county_yield_trend": _compute_trend(pd.Series(prior)),
                "prior_year_yield": float(prior[-1]),
                "county_yield_std": float(prior.std(ddof=1)) if len(prior) > 1 else 0.0,
                "_fips": fips_val,
                "_year": int(years_arr[i]),
                "_yield": float(yields_arr[i]),
                "_baseline": float(last_n.mean()),
            })

    if not features_rows:
        logger.warning("No training data for %s week %d", crop, week)
        return {}

    df = pd.DataFrame(features_rows)

    # Vectorized join of weather + drought + hurricane + flood features onto the panel.
    if has_weather and wx_lookup is not None:
        wx_join = wx_features[[
            c for c in (
                "fips", "year",
                "gdd_anom", "tmax_anom", "precip_anom_in",
                "precip_deficit_in", "hot_days", "drought_d3d4_pct",
                "tropical_track_pts_within_200km",
                "flood_event_count",
            ) if c in wx_features.columns
        ]].copy()
        wx_join["year"] = wx_join["year"].astype(int)
        df = df.merge(
            wx_join,
            left_on=["_fips", "_year"],
            right_on=["fips", "year"],
            how="left",
        ).drop(columns=["fips", "year"])

    # Use available features (drop all-null columns). Underscore-prefixed
    # columns are housekeeping and never enter X.
    available_features = [
        c for c in df.columns
        if not c.startswith("_") and df[c].notna().any()
    ]

    if len(available_features) < 2:
        logger.warning("Too few features for %s week %d", crop, week)
        return {}

    # Split train/val/test
    train_mask = df["_year"] <= TRAIN_END
    val_mask = (df["_year"] >= VAL_START) & (df["_year"] <= VAL_END)
    test_mask = (df["_year"] >= TEST_START) & (df["_year"] <= TEST_END)

    X_train = df.loc[train_mask, available_features]
    X_val = df.loc[val_mask, available_features]
    X_test = df.loc[test_mask, available_features]

    y_train_abs = df.loc[train_mask, "_yield"].astype(float)
    y_val_abs = df.loc[val_mask, "_yield"].astype(float)
    y_test_abs = df.loc[test_mask, "_yield"].astype(float)

    base_train = df.loc[train_mask, "_baseline"].astype(float)
    base_val = df.loc[val_mask, "_baseline"].astype(float)
    base_test = df.loc[test_mask, "_baseline"].astype(float)

    if use_anomaly_target:
        y_train = y_train_abs - base_train
        y_val = y_val_abs - base_val
        y_test = y_test_abs - base_test
    else:
        y_train = y_train_abs
        y_val = y_val_abs
        y_test = y_test_abs

    logger.info("  Split: train=%d, val=%d, test=%d, features=%d (%s)",
                len(X_train), len(X_val), len(X_test), len(available_features),
                ", ".join(available_features))

    if len(X_train) < 50 or len(X_val) < 10:
        logger.warning("Insufficient data for %s week %d", crop, week)
        return {}

    # Train model in target space (residual when use_anomaly_target=True).
    target_mode = "anomaly_5yr_mean" if use_anomaly_target else "absolute"
    model = YieldModel(
        crop=crop,
        week=week,
        model_ver=date.today().isoformat(),
        feature_cols=available_features,
        target_mode=target_mode,
        climatology=climatology,
    )
    model.fit(X_train, y_train)

    # Evaluate in absolute-yield space so RRMSE numbers are comparable to
    # the prior model and the published gate. predict_batch handles the
    # residual-to-absolute conversion internally when target_mode is set.
    if use_anomaly_target:
        _, train_p50_abs, _ = model.predict_batch(X_train, baselines=base_train.values)
        _, val_p50_abs, _ = model.predict_batch(X_val, baselines=base_val.values)
    else:
        _, train_p50_abs, _ = model.predict_batch(X_train)
        _, val_p50_abs, _ = model.predict_batch(X_val)

    train_rrmse = compute_rrmse(y_train_abs.values, train_p50_abs)
    val_rrmse = compute_rrmse(y_val_abs.values, val_p50_abs)

    # Calibrate conformal intervals in target space (residual when anomaly).
    model.calibrate_conformal(X_val, y_val)

    # Capture per-row walk-forward predictions for yield_accuracy persistence (§7.4 WI-3)
    prediction_rows: list[dict] = []
    if capture_predictions:
        val_df = df.loc[val_mask]
        if use_anomaly_target:
            val_p10, val_p50, val_p90 = model.predict_batch(X_val, baselines=base_val.values)
        else:
            val_p10, val_p50, val_p90 = model.predict_batch(X_val)
        for i, (_, meta) in enumerate(val_df.iterrows()):
            actual = float(meta["_yield"])
            p50 = float(val_p50[i])
            p10 = float(val_p10[i])
            p90 = float(val_p90[i])
            pct_err = round((p50 - actual) / actual * 100, 2) if actual > 0 else None
            prediction_rows.append({
                "forecast_year": int(meta["_year"]),
                "fips": str(meta["_fips"]),
                "crop": crop,
                "week": week,
                "model_p50": p50,
                "model_p10": p10,
                "model_p90": p90,
                "actual_yield": actual,
                "county_5yr_mean": round(float(meta.get("_baseline", 0)), 1) if pd.notna(meta.get("_baseline")) else None,
                "abs_error": round(abs(p50 - actual), 2),
                "pct_error": pct_err,
                "in_interval": bool(p10 <= actual <= p90),
                "split": "val",
            })

    # Test set
    test_rrmse = None
    if len(X_test) > 0:
        if use_anomaly_target:
            _, test_p50_abs, _ = model.predict_batch(X_test, baselines=base_test.values)
        else:
            _, test_p50_abs, _ = model.predict_batch(X_test)
        test_rrmse = compute_rrmse(y_test_abs.values, test_p50_abs)

        if capture_predictions:
            test_df = df.loc[test_mask]
            if use_anomaly_target:
                test_p10, test_p50, test_p90 = model.predict_batch(X_test, baselines=base_test.values)
            else:
                test_p10, test_p50, test_p90 = model.predict_batch(X_test)
            for i, (_, meta) in enumerate(test_df.iterrows()):
                actual = float(meta["_yield"])
                p50 = float(test_p50[i])
                p10 = float(test_p10[i])
                p90 = float(test_p90[i])
                pct_err = round((p50 - actual) / actual * 100, 2) if actual > 0 else None
                prediction_rows.append({
                    "forecast_year": int(meta["_year"]),
                    "fips": str(meta["_fips"]),
                    "crop": crop,
                    "week": week,
                    "model_p50": p50,
                    "model_p10": p10,
                    "model_p90": p90,
                    "actual_yield": actual,
                    "county_5yr_mean": round(float(meta.get("_baseline", 0)), 1) if pd.notna(meta.get("_baseline")) else None,
                    "abs_error": round(abs(p50 - actual), 2),
                    "pct_error": pct_err,
                    "in_interval": bool(p10 <= actual <= p90),
                    "split": "test",
                })

    # Baselines
    baselines = compute_baselines(
        nass_yields,
        list(range(VAL_START, VAL_END + 1)),
    )

    # Gate check
    county_mean_baseline = baselines.get("county_mean_rrmse", 100)
    beats_baseline = val_rrmse < county_mean_baseline * (1 - BASELINE_GATE_PCT / 100)

    logger.info(
        "  %s week %d: train=%.2f%% val=%.2f%% test=%s baseline=%.2f%% beats=%s",
        crop, week, train_rrmse, val_rrmse,
        f"{test_rrmse:.2f}%" if test_rrmse else "N/A",
        county_mean_baseline, beats_baseline,
    )

    # Save artifacts
    artifact_dir = ARTIFACTS_DIR / crop / f"week_{week}"
    model.save(artifact_dir / "model.pkl")

    metrics = {
        "crop": crop,
        "week": week,
        "model_ver": model.model_ver,
        "train_rrmse": train_rrmse,
        "val_rrmse": val_rrmse,
        "test_rrmse": test_rrmse,
        "baselines": baselines,
        "beats_baseline": beats_baseline,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "n_features": len(model.feature_cols),
        "feature_cols": model.feature_cols,
        "has_weather_features": has_weather,
        "target_mode": target_mode,
        "n_climatology_counties": len(climatology),
        "drought_attached": "drought_d3d4_pct" in model.feature_cols,
        "hurricane_attached": "tropical_track_pts_within_200km" in model.feature_cols,
        "flood_attached": "flood_event_count" in model.feature_cols,
        "top_features": [
            {"name": name, "importance": round(float(imp), 4)}
            for name, imp in model.get_top_features(7)
        ],
        "conformal_q80": model.conformal_q80,
        "confidence_tier": YieldModel.confidence_tier(week),
    }

    with open(artifact_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    if capture_predictions:
        metrics["predictions"] = prediction_rows

    return metrics


def persist_yield_accuracy(predictions: list[dict], model_ver: str) -> int:
    """Upsert walk-forward yield predictions into yield_accuracy table (§7.4 WI-3).

    Args:
        predictions: list of per-row prediction dicts from train_single_model
                     (captured when capture_predictions=True).
        model_ver: model version string for the unique constraint.

    Returns number of rows upserted.
    """
    from sqlalchemy.dialects.postgresql import insert
    from backend.etl.common import get_sync_session
    from backend.models.db_tables import YieldAccuracy

    if not predictions:
        return 0

    rows = []
    for p in predictions:
        rows.append({
            **p,
            "model_ver": model_ver,
        })

    session = get_sync_session()
    try:
        # Upsert in chunks to keep single statements reasonable
        CHUNK = 5000
        total = 0
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i + CHUNK]
            stmt = insert(YieldAccuracy.__table__).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_yield_accuracy",
                set_={
                    "model_p50": stmt.excluded.model_p50,
                    "model_p10": stmt.excluded.model_p10,
                    "model_p90": stmt.excluded.model_p90,
                    "actual_yield": stmt.excluded.actual_yield,
                    "county_5yr_mean": stmt.excluded.county_5yr_mean,
                    "abs_error": stmt.excluded.abs_error,
                    "pct_error": stmt.excluded.pct_error,
                    "in_interval": stmt.excluded.in_interval,
                    "split": stmt.excluded.split,
                },
            )
            result = session.execute(stmt)
            total += result.rowcount
        session.commit()
        return total
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _compute_trend(series: pd.Series) -> float:
    """Compute simple linear trend (slope) of a series."""
    if len(series) < 3:
        return 0.0
    x = np.arange(len(series))
    try:
        slope = np.polyfit(x, series.values, 1)[0]
        return round(float(slope), 2)
    except (np.linalg.LinAlgError, ValueError):
        return 0.0


def prune_old_yield_accuracy_versions(crop: str | None = None) -> int:
    """Delete yield_accuracy rows whose model_ver is not the current max.

    The (forecast_year, fips, crop, week, model_ver) unique constraint means
    each retraining run appends a fresh row instead of replacing prior ones.
    Without periodic pruning, the analyst agent's outlier ranking gets
    triplicated (NC corn 2024 / Lee Co showed 3 identical rows across
    2026-04-14, 2026-04-15, 2026-04-21 model versions). Documented as a side
    finding in research/yield-model-nc-2024-investigation.md.

    Args:
        crop: optional crop filter ("corn" / "soybean" / "wheat"); None = all.

    Returns number of rows deleted.
    """
    from sqlalchemy import text
    from backend.etl.common import get_sync_session

    session = get_sync_session()
    try:
        if crop:
            sql = text(
                """
                DELETE FROM yield_accuracy
                 WHERE crop = :crop
                   AND model_ver < (
                     SELECT MAX(model_ver) FROM yield_accuracy WHERE crop = :crop
                   )
                """
            )
            params = {"crop": crop}
        else:
            sql = text(
                """
                DELETE FROM yield_accuracy ya
                 WHERE ya.model_ver < (
                   SELECT MAX(model_ver) FROM yield_accuracy WHERE crop = ya.crop
                 )
                """
            )
            params = {}
        result = session.execute(sql, params)
        session.commit()
        return result.rowcount or 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upload_to_s3():
    """Upload all yield model artifacts to S3."""
    import subprocess
    s3_prefix = "s3://usda-analysis-datasets/models/yield/"
    logger.info("Uploading artifacts to S3...")
    try:
        subprocess.run(
            ["aws", "s3", "sync", str(ARTIFACTS_DIR), s3_prefix, "--quiet"],
            check=True, timeout=120,
        )
        logger.info("Artifacts uploaded to %s", s3_prefix)
    except Exception as exc:
        logger.warning("S3 upload failed: %s", exc)


def _write_crop_summaries(all_metrics: list[dict]) -> None:
    """Aggregate per-week metrics into one summary.json per crop.

    The yield forecast is surfaced in the dashboard even when the deployment
    gate fails (this is a class project; performance is annotated in-UI
    rather than gated at the model layer). The summary gives the frontend
    enough structured data to render an honest "Experimental" or "Production"
    badge instead of silently publishing suspect numbers.
    """
    by_crop: dict[str, list[dict]] = {}
    for m in all_metrics:
        by_crop.setdefault(m["crop"], []).append(m)

    for crop, ms in by_crop.items():
        weeks_with_gate = [bool(m.get("beats_baseline")) for m in ms]
        val_rrmses = [m["val_rrmse"] for m in ms if m.get("val_rrmse") is not None]
        test_rrmses = [m["test_rrmse"] for m in ms if m.get("test_rrmse") is not None]
        baselines = [
            m["baselines"].get("county_mean_rrmse")
            for m in ms if m.get("baselines") and m["baselines"].get("county_mean_rrmse") is not None
        ]

        n_pass = sum(1 for g in weeks_with_gate if g)
        gate_status = "pass" if n_pass == len(ms) else ("partial" if n_pass > 0 else "fail")

        summary = {
            "crop": crop,
            "model_ver": ms[0].get("model_ver") if ms else None,
            "n_weeks": len(ms),
            "n_weeks_pass_gate": n_pass,
            "gate_status": gate_status,
            "avg_val_rrmse": round(float(np.mean(val_rrmses)), 2) if val_rrmses else None,
            "avg_test_rrmse": round(float(np.mean(test_rrmses)), 2) if test_rrmses else None,
            "avg_baseline_rrmse": round(float(np.mean(baselines)), 2) if baselines else None,
            "has_weather_features": any(m.get("has_weather_features") for m in ms),
            "target_mode": ms[0].get("target_mode") if ms else None,
            "drought_attached": any(m.get("drought_attached") for m in ms),
            "hurricane_attached": any(m.get("hurricane_attached") for m in ms),
            "flood_attached": any(m.get("flood_attached") for m in ms),
            "gate_threshold_pct": BASELINE_GATE_PCT,
        }

        summary_path = ARTIFACTS_DIR / crop / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(
            "  Wrote %s: gate=%s (%d/%d weeks pass)",
            summary_path, gate_status, n_pass, len(ms),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train crop yield prediction models")
    parser.add_argument("--commodity", default="all", help="corn|soybean|wheat|all")
    parser.add_argument("--week", type=int, help="Specific week (1-20), default: all")
    parser.add_argument("--local-only", action="store_true", help="Skip S3 download")
    parser.add_argument("--skip-cv", action="store_true", help="Skip cross-validation")
    parser.add_argument("--upload-s3", action="store_true", help="Upload artifacts to S3")
    parser.add_argument(
        "--persist-accuracy",
        action="store_true",
        help="Upsert walk-forward val+test predictions to yield_accuracy table",
    )
    parser.add_argument(
        "--absolute-target",
        action="store_true",
        help="Train against absolute yield rather than (yield - 5yr mean) anomaly. "
        "Provided for A/B comparison; production runs should leave this off.",
    )
    parser.add_argument(
        "--prune-old-versions",
        action="store_true",
        help="After training (or standalone), DELETE yield_accuracy rows whose "
        "model_ver < MAX(model_ver) per crop. Side finding from "
        "research/yield-model-nc-2024-investigation.md — keeps the analyst "
        "agent's outlier ranking clean.",
    )
    args = parser.parse_args()

    t0 = _time.time()

    # Load shared data once
    weather_df = load_weather_data()
    prism_normals = load_prism_normals()
    drought_df = load_drought_history()
    hurdat_df = load_hurdat2()
    flood_df = load_storm_floods()
    county_centroids = load_county_centroids()

    commodities = COMMODITIES if args.commodity == "all" else {args.commodity: COMMODITIES[args.commodity]}
    weeks = [args.week] if args.week else list(WEEKS)

    use_anomaly_target = not args.absolute_target

    all_metrics = []

    for crop_key, crop_nass in commodities.items():
        logger.info("=== Commodity: %s ===", crop_key)
        nass_yields = load_nass_county_yields(crop_nass, local_only=args.local_only)

        if nass_yields.empty:
            logger.warning("No yield data for %s. Skipping.", crop_key)
            continue

        logger.info("Loaded %d county yield records for %s (%d-%d)",
                    len(nass_yields), crop_key,
                    nass_yields["year"].min(), nass_yields["year"].max())

        for week in weeks:
            metrics = train_single_model(
                crop_key, week, nass_yields, weather_df, prism_normals,
                drought_df=drought_df,
                hurdat_df=hurdat_df,
                flood_df=flood_df,
                county_centroids=county_centroids,
                skip_cv=args.skip_cv,
                capture_predictions=args.persist_accuracy,
                use_anomaly_target=use_anomaly_target,
            )
            if metrics:
                all_metrics.append(metrics)

                # Persist walk-forward predictions per (crop, week) to yield_accuracy
                if args.persist_accuracy and metrics.get("predictions"):
                    try:
                        n = persist_yield_accuracy(
                            metrics["predictions"],
                            model_ver=metrics["model_ver"],
                        )
                        logger.info("  Persisted %d rows to yield_accuracy", n)
                    except Exception as exc:
                        logger.error("  Failed to persist yield accuracy: %s", exc)
                    # Strip predictions from in-memory metrics to keep memory bounded
                    metrics.pop("predictions", None)

    # Summary
    logger.info("=== Training Summary ===")
    for m in all_metrics:
        status = "PASS" if m.get("beats_baseline") else "FAIL"
        wx_tag = "+wx" if m.get("has_weather_features") else "nass-only"
        logger.info(
            "  %s week %2d: val=%.2f%% test=%s baseline=%.2f%% [%s] (%s, %d feats)",
            m["crop"], m["week"], m["val_rrmse"],
            f"{m['test_rrmse']:.2f}%" if m.get("test_rrmse") else "N/A",
            m["baselines"].get("county_mean_rrmse", 0),
            status, wx_tag, m["n_features"],
        )

    # Per-crop aggregate summary (consumed by GET /api/v1/predict/yield/metadata
    # so the frontend can annotate models that fail the deployment gate).
    _write_crop_summaries(all_metrics)

    if args.prune_old_versions:
        try:
            n_pruned = prune_old_yield_accuracy_versions(
                None if args.commodity == "all" else args.commodity,
            )
            logger.info(
                "Pruned %d stale yield_accuracy rows (model_ver < MAX per crop)",
                n_pruned,
            )
        except Exception as exc:
            logger.error("Could not prune yield_accuracy: %s", exc)

    if args.upload_s3:
        upload_to_s3()

    elapsed = _time.time() - t0
    logger.info("Total training time: %.1f minutes", elapsed / 60)
