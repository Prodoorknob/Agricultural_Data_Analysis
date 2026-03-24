"""
quickstats_ingest.py - Automated USDA QuickStats API Ingestion Pipeline

Fetches agricultural data from the USDA QuickStats API, cleans and transforms it
using the same logic as data_prep.py, partitions by state into parquet files,
and optionally uploads to S3.

Usage:
    # Full ingestion (all sectors, all years)
    python quickstats_ingest.py

    # Specific sector and year range
    python quickstats_ingest.py --sectors CROPS --year-start 2023 --year-end 2024

    # Single state for testing
    python quickstats_ingest.py --states IN --year-start 2023 --year-end 2023

    # Dry run (fetch + process, no S3 upload)
    python quickstats_ingest.py --dry-run

Environment Variables:
    USDA_QUICKSTATS_API_KEY  - API key (or fetched from AWS SSM)
    AWS_REGION               - AWS region (default: us-east-2)
"""

import gc
import os
import sys
import re
import json
import shutil
import time
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

log_filename = os.path.join(LOG_DIR, f"ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_filename),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (aligned with data_prep.py)
# ---------------------------------------------------------------------------
API_BASE = "https://quickstats.nass.usda.gov/api"
API_GET_ENDPOINT = f"{API_BASE}/api_GET"
API_COUNT_ENDPOINT = f"{API_BASE}/get_counts"

MAX_RECORDS_PER_REQUEST = 50000
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds

# Columns to keep -- extends NASS_KEEP_COLS from data_prep.py:296-301
# with temporal columns needed for weekly CONDITION/PROGRESS data
KEEP_COLS = [
    "source_desc", "sector_desc", "group_desc", "commodity_desc", "class_desc",
    "prodn_practice_desc", "util_practice_desc", "statisticcat_desc", "unit_desc",
    "short_desc", "domain_desc", "domaincat_desc", "agg_level_desc",
    "state_fips_code", "state_alpha", "state_name",
    "county_code", "county_name", "year", "Value", "CV (%)",
    # Temporal columns for weekly/monthly data granularity
    "freq_desc",               # ANNUAL, WEEKLY, MONTHLY
    "reference_period_desc",   # "YEAR", "WEEK #12", "MAR", etc.
    "begin_code",              # Period begin code (week/month number)
    "end_code",                # Period end code
]

# Sectors to fetch
SECTORS = ["CROPS", "ANIMALS & PRODUCTS", "ECONOMICS"]

# Year range
DEFAULT_YEAR_START = 2001
DEFAULT_YEAR_END = 2025

# Relevant statistic categories -- extends data_prep.py:304-309
# with livestock detail, economic metrics, and land sub-categories
RELEVANT_STAT_CATS = [
    # Crops core
    "AREA HARVESTED", "AREA PLANTED", "PRODUCTION", "YIELD",
    "PRICE RECEIVED", "SALES", "OPERATIONS",
    "EXPENSE", "WAGE RATE", "WORKERS", "ASSET VALUE",
    "INVENTORY", "HEAD", "AREA", "AREA OPERATED",
    # Crop condition (weekly data — needs freq_desc/reference_period_desc)
    "CONDITION, 5 YEAR AVG", "CONDITION, PREVIOUS WEEK",
    "CONDITION, MEASURED IN PCT EXCELLENT",
    "CONDITION, MEASURED IN PCT GOOD",
    "CONDITION, MEASURED IN PCT FAIR",
    "CONDITION, MEASURED IN PCT POOR",
    "CONDITION, MEASURED IN PCT VERY POOR",
    # Crop progress (weekly data)
    "PROGRESS", "PROGRESS, 5 YEAR AVG", "PROGRESS, PREVIOUS YEAR",
    # Livestock detail
    "SLAUGHTER", "DEATH LOSS", "DISTRIBUTION",
    # Economics detail
    "RECEIPTS", "NET INCOME", "NET CASH FARM INCOME", "GOVT PAYMENTS",
    "VALUE OF PRODUCTION",
    # Land sub-categories
    "AREA BEARING", "AREA NON-BEARING", "AREA IRRIGATED",
]

# Output directory for generated parquet files
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")

# Dataset source mapping (for the dataset_source column used by process_state_data)
SECTOR_TO_DATASET_SOURCE = {
    "CROPS": "nass_crops",
    "ANIMALS & PRODUCTS": "nass_animals",
    "ECONOMICS": "nass_economics",
}

# Commodity groups for deep sub-chunking when (source, agg_level, stat_cat) still exceeds 50K
COMMODITY_GROUPS = {
    "CROPS": [
        "FIELD CROPS", "VEGETABLES", "FRUIT & TREE NUTS",
        "HORTICULTURE", "CROP TOTALS",
    ],
    "ANIMALS & PRODUCTS": [
        "LIVESTOCK", "POULTRY", "AQUACULTURE",
        "SPECIALTY", "ANIMAL TOTALS",
    ],
    "ECONOMICS": [
        "FARMS & LAND & ASSETS", "OPERATORS", "INCOME",
        "EXPENSES",
    ],
}

# ---------------------------------------------------------------------------
# County-Level Ingestion Constants
# ---------------------------------------------------------------------------

# All 50 states + DC (territories excluded — sparse county data)
US_STATE_CODES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
]

# Commodities with reliable annual county-level data in NASS surveys.
# Tier 1: core row crops with dense national county coverage.
# Tier 2: regional importance — sparser counties but available where grown.
# NOTE: PRICE RECEIVED is not published at county level by USDA.
# NOTE: SALES / VALUE OF PRODUCTION are Census-of-Ag only (see load_census_county.py).
COUNTY_COMMODITIES = [
    # Tier 1 — core row crops
    "CORN",
    "SOYBEANS",
    "WINTER WHEAT",
    "SPRING WHEAT, (EXCL DURUM)",
    "COTTON",
    # Tier 2 — regional
    "SORGHUM",
    "BARLEY",
    "OATS",
    "HAY",
    "RICE",
    "SUNFLOWER",
]

# Stat categories available at county resolution in annual NASS surveys.
COUNTY_STAT_CATS = [
    "YIELD",
    "AREA HARVESTED",
    "AREA PLANTED",
    "PRODUCTION",
]

# More conservative delay for county pulls (higher sustained API call volume)
COUNTY_REQUEST_DELAY = 2.0

# Parallelism: number of state-groups fetched concurrently.
# 4 threads × 2s delay = one request every ~0.5s effective — safe for QuickStats.
COUNTY_FETCH_WORKERS = 4

# Census of Agriculture years — CENSUS source_desc is ONLY valid for these years.
# Requesting CENSUS for any other year will always 400. Do not add interim years.
CENSUS_AG_YEARS = {2002, 2007, 2012, 2017, 2022}

# State/commodity combinations known to not exist in NASS county data.
# These are structural gaps (no agriculture of that type in that state),
# not transient API errors. Skipping them avoids pointless 400s.
# Key = commodity_desc, Value = set of state_alpha codes to skip.
COUNTY_SKIP_STATES: dict[str, set[str]] = {
    # Alaska has no commercial corn, soybean, cotton, or wheat production
    "CORN":                    {"AK", "HI", "DC"},
    "SOYBEANS":                {"AK", "HI", "DC", "NV", "AZ", "NM", "UT", "WY", "MT", "ID"},
    "WINTER WHEAT":            {"AK", "HI", "DC"},
    "SPRING WHEAT, (EXCL DURUM)": {"AK", "HI", "DC", "AL", "FL", "GA", "SC", "MS", "LA"},
    "COTTON":                  {"AK", "HI", "DC", "ME", "NH", "VT", "MA", "RI", "CT",
                                "NY", "NJ", "PA", "OH", "IN", "IL", "IA", "WI", "MI",
                                "MN", "ND", "SD", "NE", "KS", "CO", "UT", "NV", "WY",
                                "ID", "OR", "WA", "MT"},
    "RICE":                    {"AK", "HI", "DC", "ME", "NH", "VT", "MA", "RI", "CT",
                                "NY", "NJ", "PA", "OH", "IN", "IL", "IA", "WI", "MI",
                                "MN", "ND", "SD", "NE", "KS", "CO", "UT", "NV", "WY",
                                "ID", "OR", "WA", "MT", "AZ", "NM"},
    "SUNFLOWER":               {"AK", "HI", "DC", "ME", "NH", "VT", "MA", "RI", "CT",
                                "NJ", "DE", "MD", "VA", "SC", "GA", "FL", "AL", "MS",
                                "LA", "AR", "TN", "KY", "WV"},
}


# ---------------------------------------------------------------------------
# API Key Management
# ---------------------------------------------------------------------------
def get_api_key() -> str:
    """Get the QuickStats API key from env var or AWS SSM."""
    key = os.environ.get("USDA_QUICKSTATS_API_KEY")
    if key:
        return key

    # Try AWS SSM Parameter Store
    try:
        import boto3

        ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-2"))
        response = ssm.get_parameter(Name="/usda/quickstats-api-key", WithDecryption=True)
        return response["Parameter"]["Value"]
    except Exception as e:
        logger.error(f"Could not retrieve API key from SSM: {e}")

    raise ValueError(
        "No API key found. Set USDA_QUICKSTATS_API_KEY env var or store in AWS SSM at /usda/quickstats-api-key"
    )


# ---------------------------------------------------------------------------
# Value Cleaning (replicated from data_prep.py:344-377)
# ---------------------------------------------------------------------------
def clean_nass_value(val) -> Optional[float]:
    """Clean NASS QuickStats 'Value' column to numeric.

    Handles commas, NASS special codes: (D), (Z), (NA), (X), (S), (L), (H).
    """
    if pd.isna(val):
        return np.nan

    val_str = str(val).strip()

    # Check for NASS special codes
    if re.match(r"^\s*\([DZNAXSLH]\)\s*$", val_str, re.IGNORECASE):
        return np.nan

    if val_str in ("", "-", "--", "NA", "N/A", "null", "None"):
        return np.nan

    try:
        return float(val_str.replace(",", ""))
    except (ValueError, TypeError):
        return np.nan


def filter_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Filter out TOTALS commodities to avoid double-counting."""
    if "commodity_desc" not in df.columns:
        return df
    return df[~df["commodity_desc"].str.contains("TOTAL", case=False, na=False)].copy()


# ---------------------------------------------------------------------------
# API Calls
# ---------------------------------------------------------------------------
_active_api_key = ""  # Set during ingestion for error sanitization


def _sanitize_error(msg: str) -> str:
    """Replace API key in error messages with a redacted placeholder."""
    if _active_api_key:
        return str(msg).replace(_active_api_key, "***REDACTED***")
    return str(msg)


def api_get_counts(api_key: str, params: dict) -> int:
    """Call the get_counts endpoint and return expected record count."""
    params_with_key = {"key": api_key, **params}
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(API_COUNT_ENDPOINT, params=params_with_key, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            count = int(data.get("count", 0))
            time.sleep(REQUEST_DELAY_SECONDS)
            return count
        except Exception as e:
            wait = RETRY_BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"get_counts attempt {attempt + 1} failed: {_sanitize_error(e)}. Retrying in {wait}s...")
            time.sleep(wait)
    return 0


def api_get_data(api_key: str, params: dict) -> list[dict]:
    """Call the api_GET endpoint and return list of records."""
    params_with_key = {"key": api_key, "format": "JSON", **params}
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(API_GET_ENDPOINT, params=params_with_key, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            records = data.get("data", [])
            return records
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 413:
                logger.error(f"Request too large (>50K records): {_sanitize_error(params)}")
                return []
            if resp.status_code == 400:
                logger.warning(f"Bad request (invalid parameter combo): {_sanitize_error(params)}")
                return []
            wait = RETRY_BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"api_GET attempt {attempt + 1} failed: {_sanitize_error(e)}. Retrying in {wait}s...")
            time.sleep(wait)
        except Exception as e:
            wait = RETRY_BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"api_GET attempt {attempt + 1} failed: {_sanitize_error(e)}. Retrying in {wait}s...")
            time.sleep(wait)
    return []


# ---------------------------------------------------------------------------
# Ingestion Logic
# ---------------------------------------------------------------------------
def fetch_sector_year(api_key: str, sector: str, year: int) -> pd.DataFrame:
    """Fetch STATE and NATIONAL records for a given sector and year.

    Fetches both SURVEY and CENSUS data to maximize data density.
    The frontend filterData() handles Census/Survey deduplication.

    COUNTY agg_level is handled separately by fetch_county_data() which uses
    a whitelist-pinned flat loop — do not add COUNTY here.

    Sub-chunking strategy when count exceeds 50K:
      1. Split by source_desc (SURVEY/CENSUS)
      2. Split by statisticcat_desc (from RELEVANT_STAT_CATS)
      3. Split by group_desc (from COMMODITY_GROUPS)
      4. If group_desc still >50K, try with domain_desc=TOTAL (aggregate only)
    """
    all_records = []

    # Only fetch STATE and NATIONAL — COUNTY is discarded by partition_by_state()
    for agg_level in ["NATIONAL", "STATE"]:
        base_params = {
            "sector_desc": sector,
            "year": str(year),
            "agg_level_desc": agg_level,
        }

        count = api_get_counts(api_key, base_params)
        logger.info(f"  {sector} / {year} / {agg_level}: {count:,} records")

        if count == 0:
            continue

        if count <= MAX_RECORDS_PER_REQUEST:
            time.sleep(REQUEST_DELAY_SECONDS)
            records = api_get_data(api_key, base_params)
            all_records.extend(records)
            logger.info(f"    Fetched {len(records):,} records")
            continue

        # Sub-chunk by source_desc
        logger.info(f"    Count {count:,} exceeds limit, sub-chunking by source_desc")
        for source in ["SURVEY", "CENSUS"]:
            source_params = {**base_params, "source_desc": source}
            source_count = api_get_counts(api_key, source_params)
            if source_count == 0:
                continue

            if source_count <= MAX_RECORDS_PER_REQUEST:
                time.sleep(REQUEST_DELAY_SECONDS)
                records = api_get_data(api_key, source_params)
                all_records.extend(records)
                logger.info(f"    {source}: fetched {len(records):,}")
                continue

            # Sub-chunk by statisticcat_desc
            logger.info(f"    {source}/{agg_level}: {source_count:,} records, sub-chunking by statisticcat_desc")
            for stat_cat in RELEVANT_STAT_CATS:
                cat_params = {**source_params, "statisticcat_desc": stat_cat}
                cat_count = api_get_counts(api_key, cat_params)
                if cat_count == 0:
                    continue

                if cat_count <= MAX_RECORDS_PER_REQUEST:
                    time.sleep(REQUEST_DELAY_SECONDS)
                    records = api_get_data(api_key, cat_params)
                    all_records.extend(records)
                    logger.info(f"      {stat_cat}: fetched {len(records):,}")
                    continue

                # Sub-chunk by group_desc when stat_cat still exceeds 50K
                logger.info(
                    f"      {source}/{agg_level}/{stat_cat}: {cat_count:,} still >50K, "
                    "sub-chunking by group_desc"
                )
                groups = COMMODITY_GROUPS.get(sector, [])
                for group in groups:
                    group_params = {**cat_params, "group_desc": group}
                    time.sleep(REQUEST_DELAY_SECONDS)
                    records = api_get_data(api_key, group_params)
                    if records:
                        all_records.extend(records)
                        logger.info(f"        {group}: fetched {len(records):,}")
                    else:
                        # Fallback: try with domain_desc=TOTAL to get aggregate data
                        # when group_desc is still >50K (due to domain breakdowns)
                        total_params = {**group_params, "domain_desc": "TOTAL"}
                        time.sleep(REQUEST_DELAY_SECONDS)
                        records = api_get_data(api_key, total_params)
                        if records:
                            all_records.extend(records)
                            logger.info(f"        {group} (TOTAL only): fetched {len(records):,}")

    if all_records:
        return pd.DataFrame(all_records)
    return pd.DataFrame()


def clean_dataframe(df: pd.DataFrame, sector: str) -> pd.DataFrame:
    """Apply cleaning logic matching data_prep.py."""
    if df.empty:
        return df

    # Keep only relevant columns (those that exist)
    available_cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[available_cols].copy()

    # Clean the Value column
    df["value_num"] = df["Value"].apply(clean_nass_value)

    # Standardize state FIPS
    if "state_fips_code" in df.columns:
        df["state_fips_code"] = df["state_fips_code"].astype(str).str.zfill(2)

    # Create FIPS code
    if "county_code" in df.columns and "state_fips_code" in df.columns:
        df["county_code"] = df["county_code"].astype(str).str.zfill(3)
        df["fips"] = df["state_fips_code"] + df["county_code"]

    # Ensure year is integer
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

    # Add dataset source tag
    df["dataset_source"] = SECTOR_TO_DATASET_SOURCE.get(sector, "nass_other")

    # Filter out TOTALS
    df = filter_totals(df)

    return df


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived metrics computed at the (state, commodity, year) level.

    Computes:
    - REVENUE PER ACRE: SALES / AREA HARVESTED
    - PLANTED TO HARVESTED RATIO: AREA PLANTED / AREA HARVESTED
    - Imputed SALES: PRICE RECEIVED * PRODUCTION (when SALES is missing)

    Derived rows are tagged with source_desc='DERIVED' so the frontend
    can distinguish them from official USDA data.

    County rows (agg_level_desc == 'COUNTY') are passed through unchanged —
    derivations are meaningless aggregated across counties at this stage.
    """
    if df.empty:
        return df

    # Split county rows out — enrich state/national rows only
    if "agg_level_desc" in df.columns:
        county_mask = df["agg_level_desc"] == "COUNTY"
        county_df = df[county_mask].copy()
        df = df[~county_mask].copy()
        if df.empty:
            return county_df
    else:
        county_df = pd.DataFrame()

    group_key = ["state_alpha", "commodity_desc", "year"]
    available_keys = [k for k in group_key if k in df.columns]
    if len(available_keys) < 3:
        result = df if county_df.empty else pd.concat([df, county_df], ignore_index=True)
        return result

    # Only use ANNUAL data for deriving metrics (skip weekly CONDITION/PROGRESS)
    if "freq_desc" in df.columns:
        annual = df[df["freq_desc"].isin(["ANNUAL", ""])  | df["freq_desc"].isna()].copy()
    else:
        annual = df.copy()

    if annual.empty:
        return df

    # Build wide-format lookup: (state, commodity, year) -> {stat_cat: value}
    pivot = (
        annual.groupby(available_keys + ["statisticcat_desc"])["value_num"]
        .sum()
        .reset_index()
    )
    wide = pivot.pivot_table(
        index=available_keys, columns="statisticcat_desc", values="value_num"
    ).reset_index()

    derived_rows = []
    for _, row in wide.iterrows():
        base = {k: row[k] for k in available_keys}
        area_h = row.get("AREA HARVESTED", np.nan)
        area_p = row.get("AREA PLANTED", np.nan)
        production = row.get("PRODUCTION", np.nan)
        sales = row.get("SALES", np.nan)
        price = row.get("PRICE RECEIVED", np.nan)

        # Revenue per acre
        if pd.notna(sales) and pd.notna(area_h) and area_h > 0:
            derived_rows.append({
                **base,
                "statisticcat_desc": "REVENUE PER ACRE",
                "value_num": sales / area_h,
                "unit_desc": "$ / ACRE",
                "source_desc": "DERIVED",
                "domain_desc": "TOTAL",
            })

        # Planted-to-harvested ratio
        if pd.notna(area_p) and pd.notna(area_h) and area_h > 0:
            derived_rows.append({
                **base,
                "statisticcat_desc": "PLANTED TO HARVESTED RATIO",
                "value_num": area_p / area_h,
                "unit_desc": "RATIO",
                "source_desc": "DERIVED",
                "domain_desc": "TOTAL",
            })

        # Imputed revenue (price * production) when SALES is missing
        if (pd.isna(sales) or sales == 0) and pd.notna(price) and pd.notna(production) and price > 0:
            derived_rows.append({
                **base,
                "statisticcat_desc": "SALES",
                "value_num": price * production,
                "unit_desc": "$",
                "source_desc": "DERIVED",
                "domain_desc": "TOTAL",
            })

    if derived_rows:
        derived_df = pd.DataFrame(derived_rows)
        # Fill missing columns with appropriate defaults
        for col in df.columns:
            if col not in derived_df.columns:
                if df[col].dtype in ["float64", "Float64"]:
                    derived_df[col] = np.nan
                elif str(df[col].dtype) == "Int64":
                    derived_df[col] = pd.NA
                else:
                    derived_df[col] = ""
        df = pd.concat([df, derived_df], ignore_index=True)
        logger.info(f"  Added {len(derived_rows):,} derived metric rows")

    # Re-attach county rows
    if not county_df.empty:
        df = pd.concat([df, county_df], ignore_index=True)

    return df


def partition_by_state(df: pd.DataFrame, output_dir: str) -> dict[str, int]:
    """Partition dataframe by state_alpha and write parquet files.

    Returns dict of {state_code: row_count}.
    """
    os.makedirs(output_dir, exist_ok=True)
    state_counts = {}

    if "state_alpha" not in df.columns:
        logger.warning("No state_alpha column found, cannot partition")
        return state_counts

    # Filter to state-level and national-level records
    if "agg_level_desc" in df.columns:
        state_df = df[df["agg_level_desc"].isin(["STATE", "NATIONAL"])].copy()
    else:
        state_df = df.copy()

    for state_code, group in state_df.groupby("state_alpha"):
        if pd.isna(state_code) or state_code == "":
            continue

        # Sort for better compression
        if "year" in group.columns and "commodity_desc" in group.columns:
            group = group.sort_values(["year", "commodity_desc"])

        group = group.drop_duplicates()

        filename = f"{state_code}.parquet"
        if state_code == "US":
            filename = "NATIONAL.parquet"

        filepath = os.path.join(output_dir, filename)
        group.to_parquet(filepath, engine="pyarrow", compression="snappy", index=False)
        state_counts[state_code] = len(group)
        logger.info(f"  Wrote {filename}: {len(group):,} rows")

    return state_counts


# ---------------------------------------------------------------------------
# County-Level Ingestion
# ---------------------------------------------------------------------------

def _fetch_county_state_year(
    api_key: str,
    state: str,
    year: int,
    temp_dir: str,
) -> int:
    """Fetch all county-level records for one state and year.

    Iterates over COUNTY_COMMODITIES × COUNTY_STAT_CATS using a flat loop.
    Each (state, commodity, stat_cat) request is guaranteed to return well
    under 50K records (typically 50–500), so no sub-chunking is needed.

    Skips:
      - CENSUS source for non-Census years (only 2002,2007,2012,2017,2022 are valid)
      - State/commodity pairs in COUNTY_SKIP_STATES (structural data gaps)

    Writes chunk files to temp_dir/{state}/COUNTY_{commodity}_{stat_cat}_{year}.parquet.
    Returns total records fetched for this state+year.
    """
    state_chunk_dir = os.path.join(temp_dir, state)
    os.makedirs(state_chunk_dir, exist_ok=True)

    is_census_year = year in CENSUS_AG_YEARS
    total = 0

    for commodity in COUNTY_COMMODITIES:
        # Skip known non-producing state/commodity pairs
        skip_states = COUNTY_SKIP_STATES.get(commodity, set())
        if state in skip_states:
            continue

        for stat_cat in COUNTY_STAT_CATS:
            base_params = {
                "agg_level_desc": "COUNTY",
                "year": str(year),
                "state_alpha": state,
                "commodity_desc": commodity,
                "statisticcat_desc": stat_cat,
            }

            # --- Annual SURVEY pull ---
            time.sleep(COUNTY_REQUEST_DELAY)
            records = api_get_data(api_key, {**base_params, "source_desc": "SURVEY"})

            # --- CENSUS pull only on actual Census-of-Ag years ---
            if is_census_year:
                time.sleep(COUNTY_REQUEST_DELAY)
                census_records = api_get_data(api_key, {**base_params, "source_desc": "CENSUS"})
                records = records + census_records

            if not records:
                continue

            df_chunk = pd.DataFrame(records)
            # Lightweight clean: standardise FIPS columns
            if "state_fips_code" in df_chunk.columns:
                df_chunk["state_fips_code"] = df_chunk["state_fips_code"].astype(str).str.zfill(2)
            if "county_code" in df_chunk.columns and "state_fips_code" in df_chunk.columns:
                df_chunk["county_code"] = df_chunk["county_code"].astype(str).str.zfill(3)
                df_chunk["fips"] = df_chunk["state_fips_code"] + df_chunk["county_code"]
            df_chunk["value_num"] = df_chunk["Value"].apply(clean_nass_value) if "Value" in df_chunk.columns else np.nan
            df_chunk["dataset_source"] = "nass_crops"

            # Sanitize commodity name for use as filename component
            safe_commodity = re.sub(r"[^A-Za-z0-9]+", "_", commodity).strip("_")
            safe_stat = re.sub(r"[^A-Za-z0-9]+", "_", stat_cat).strip("_")
            chunk_path = os.path.join(
                state_chunk_dir,
                f"COUNTY_{safe_commodity}_{safe_stat}_{year}.parquet",
            )
            df_chunk.to_parquet(chunk_path, engine="pyarrow", compression="snappy", index=False)
            total += len(df_chunk)

    if total > 0:
        logger.info(f"  County {state}/{year}: {total:,} records")
    return total


def fetch_county_data(
    api_key: str,
    year_start: int,
    year_end: int,
    temp_dir: str,
    states_filter: Optional[list[str]] = None,
) -> int:
    """Fetch county-level data for all states and years using a flat parallel loop.

    Uses ThreadPoolExecutor to parallelize across states (COUNTY_FETCH_WORKERS threads).
    Each thread fetches one state × all years sequentially to avoid burst overload.

    Args:
        api_key: USDA QuickStats API key
        year_start: Start year (inclusive)
        year_end: End year (inclusive)
        temp_dir: Directory to write chunk files into
        states_filter: Optional subset of state codes (default: all US_STATE_CODES)

    Returns:
        Total county records fetched
    """
    states = states_filter if states_filter else US_STATE_CODES
    years = list(range(year_start, year_end + 1))
    total_county = 0

    logger.info("=" * 60)
    logger.info(f"County fetch: {len(states)} states × {len(years)} years × "
                f"{len(COUNTY_COMMODITIES)} commodities × {len(COUNTY_STAT_CATS)} stat_cats")
    logger.info(f"Workers: {COUNTY_FETCH_WORKERS} | Delay: {COUNTY_REQUEST_DELAY}s/call")
    logger.info("=" * 60)

    def _state_task(state: str) -> int:
        """Fetch all years for a single state (run in thread)."""
        state_total = 0
        for year in years:
            try:
                n = _fetch_county_state_year(api_key, state, year, temp_dir)
                state_total += n
            except Exception as exc:
                logger.error(f"  County {state}/{year} failed: {_sanitize_error(exc)}")
        return state_total

    with ThreadPoolExecutor(max_workers=COUNTY_FETCH_WORKERS) as executor:
        future_to_state = {executor.submit(_state_task, s): s for s in states}
        for future in as_completed(future_to_state):
            state = future_to_state[future]
            try:
                n = future.result()
                total_county += n
            except Exception as exc:
                logger.error(f"  County state task {state} raised: {_sanitize_error(exc)}")

    logger.info(f"County fetch complete: {total_county:,} total records")
    return total_county


# ---------------------------------------------------------------------------
# Manifest Management
# ---------------------------------------------------------------------------
def load_manifest() -> dict:
    """Load the ingestion manifest file."""
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    return {"last_run": None, "last_success": None, "record_counts": {}, "version": 1}


def save_manifest(manifest: dict):
    """Save the ingestion manifest file."""
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=4, default=str)


# ---------------------------------------------------------------------------
# Main Ingestion
# ---------------------------------------------------------------------------
def run_ingestion(
    api_key: str,
    sectors: list[str],
    year_start: int,
    year_end: int,
    states_filter: Optional[list[str]] = None,
    dry_run: bool = False,
    include_county: bool = False,
    county_only: bool = False,
) -> bool:
    """Run the full ingestion pipeline.

    Args:
        api_key: USDA QuickStats API key
        sectors: List of sectors to fetch
        year_start: Start year (inclusive)
        year_end: End year (inclusive)
        states_filter: Optional list of state codes to filter output
        dry_run: If True, skip S3 upload
        include_county: If True, also run county-level fetch after state-level
        county_only: If True, skip state-level fetch and run county fetch only

    Returns:
        True if successful, False otherwise
    """
    global _active_api_key
    _active_api_key = api_key
    manifest = load_manifest()
    manifest["last_run"] = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("USDA QuickStats API Ingestion Pipeline")
    logger.info("=" * 60)
    logger.info(f"Sectors: {sectors}")
    logger.info(f"Years: {year_start}-{year_end}")
    logger.info(f"States filter: {states_filter or 'ALL'}")
    logger.info(f"County fetch: {'county-only' if county_only else ('yes' if include_county else 'no')}")
    logger.info(f"Dry run: {dry_run}")
    logger.info(f"Output: {OUTPUT_DIR}")
    logger.info("")

    # Use a temp directory for intermediate per-state chunk files.
    # This avoids accumulating all data in memory (which causes OOM kills
    # on small EC2 instances for full 25-year runs).
    temp_dir = os.path.join(OUTPUT_DIR, "_chunks")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    total_fetched = 0

    # ---- Phase 1: State/National fetch (skipped when county_only=True) ----
    if not county_only:
        for sector in sectors:
            logger.info(f"--- Fetching sector: {sector} ---")
            for year in range(year_start, year_end + 1):
                df = fetch_sector_year(api_key, sector, year)
                if df.empty:
                    continue

                df = clean_dataframe(df, sector)
                df = enrich_dataframe(df)

                # Apply state filter early to save disk and memory
                if states_filter and "state_alpha" in df.columns:
                    df = df[df["state_alpha"].isin(states_filter)]

                total_fetched += len(df)
                manifest["record_counts"][f"{sector}_{year}"] = len(df)

                # Write per-state chunk files so memory is freed after each (sector, year)
                if "state_alpha" in df.columns:
                    for state_code, group in df.groupby("state_alpha"):
                        if pd.isna(state_code) or state_code == "":
                            continue
                        state_chunk_dir = os.path.join(temp_dir, str(state_code))
                        os.makedirs(state_chunk_dir, exist_ok=True)
                        chunk_path = os.path.join(
                            state_chunk_dir, f"{sector}_{year}.parquet"
                        )
                        group.to_parquet(
                            chunk_path,
                            engine="pyarrow",
                            compression="snappy",
                            index=False,
                        )

                del df
                gc.collect()

            logger.info("")

    # ---- Phase 1b: County fetch (runs when include_county=True or county_only=True) ----
    if include_county or county_only:
        county_count = fetch_county_data(
            api_key=api_key,
            year_start=year_start,
            year_end=year_end,
            temp_dir=temp_dir,
            states_filter=states_filter,
        )
        total_fetched += county_count
        manifest["record_counts"]["county_fetch_total"] = (
            manifest["record_counts"].get("county_fetch_total", 0) + county_count
        )

    if total_fetched == 0:
        logger.warning("No data fetched from any sector/year combination")
        shutil.rmtree(temp_dir)
        save_manifest(manifest)
        return False

    logger.info(f"Total records fetched and cleaned: {total_fetched:,}")

    # ---- Phase 2: Merge per-state chunks into final parquet files ----

    # Only one state's data is in memory at a time.
    # If a parquet file already exists for a state (from a previous run with
    # a different year range), merge the new data into it so that multi-step
    # runs (e.g., 2001-2010 then 2011-2020) accumulate correctly.
    logger.info("\nMerging chunks and writing final parquet files...")
    athena_dir = os.path.join(OUTPUT_DIR, "athena_optimized")
    os.makedirs(athena_dir, exist_ok=True)
    state_total = 0

    for state_code in sorted(os.listdir(temp_dir)):
        state_chunk_dir = os.path.join(temp_dir, state_code)
        if not os.path.isdir(state_chunk_dir):
            continue

        # Read all NEW chunks for this state
        chunks = []
        for chunk_file in sorted(os.listdir(state_chunk_dir)):
            if chunk_file.endswith(".parquet"):
                chunks.append(
                    pd.read_parquet(os.path.join(state_chunk_dir, chunk_file))
                )

        if not chunks:
            continue

        new_data = pd.concat(chunks, ignore_index=True)
        del chunks

        # Merge with existing parquet if present (incremental accumulation)
        filename = "NATIONAL.parquet" if state_code == "US" else f"{state_code}.parquet"
        existing_path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(existing_path):
            try:
                existing = pd.read_parquet(existing_path)
                new_data = pd.concat([existing, new_data], ignore_index=True)
                del existing
                logger.info(f"  Merged with existing {filename}")
            except Exception as e:
                logger.warning(f"  Could not read existing {filename}, overwriting: {e}")

        combined = new_data.drop_duplicates()
        del new_data

        if "year" in combined.columns and "commodity_desc" in combined.columns:
            combined = combined.sort_values(["year", "commodity_desc"])

        # Write browser-fetch parquet
        combined.to_parquet(
            os.path.join(OUTPUT_DIR, filename),
            engine="pyarrow",
            compression="snappy",
            index=False,
        )

        # Write Athena Hive-partitioned parquet
        partition_dir = os.path.join(athena_dir, f"state_alpha={state_code}")
        os.makedirs(partition_dir, exist_ok=True)
        combined.to_parquet(
            os.path.join(partition_dir, "data.parquet"),
            engine="pyarrow",
            compression="snappy",
            index=False,
        )

        logger.info(f"  Wrote {filename}: {len(combined):,} rows")
        state_total += 1

        del combined
        gc.collect()

    # Cleanup temp directory
    shutil.rmtree(temp_dir)
    logger.info(f"Wrote {state_total} state parquet files")
    logger.info(f"Wrote Athena-optimized partitions to {athena_dir}")

    manifest["last_success"] = datetime.now(timezone.utc).isoformat()
    save_manifest(manifest)

    logger.info("\n" + "=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info("=" * 60)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="USDA QuickStats API Ingestion Pipeline")
    parser.add_argument(
        "--sectors",
        nargs="+",
        default=SECTORS,
        help=f"Sectors to fetch (default: {SECTORS})",
    )
    parser.add_argument("--year-start", type=int, default=DEFAULT_YEAR_START, help="Start year")
    parser.add_argument("--year-end", type=int, default=DEFAULT_YEAR_END, help="End year")
    parser.add_argument(
        "--states",
        nargs="+",
        default=None,
        help="Filter to specific state codes (e.g., IN OH IL)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and process but skip S3 upload")
    parser.add_argument(
        "--include-county",
        action="store_true",
        help="Also fetch county-level data (COUNTY_COMMODITIES whitelist) after state-level fetch",
    )
    parser.add_argument(
        "--county-only",
        action="store_true",
        help="Skip state-level fetch; run county-level fetch only (useful for backfill runs)",
    )
    args = parser.parse_args()

    try:
        api_key = get_api_key()
        logger.info("API key loaded successfully")
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    success = run_ingestion(
        api_key=api_key,
        sectors=args.sectors,
        year_start=args.year_start,
        year_end=args.year_end,
        states_filter=args.states,
        dry_run=args.dry_run,
        include_county=args.include_county,
        county_only=args.county_only,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
