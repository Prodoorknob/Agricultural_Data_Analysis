"""
load_census_county.py - One-time Census of Agriculture county data loader

Fetches county-level SALES, VALUE OF PRODUCTION, and INVENTORY data from
USDA NASS QuickStats for Census of Agriculture years (2017, 2022).

This data is NOT available in annual NASS surveys — Census-of-Ag is the only
source for county-level dollar sales and livestock inventory counts.

Run once after the initial annual backfill, and again after each new Census
year dataset is published (typically ~2 years after the census year).

Usage:
    # Fetch both Census years (default)
    python load_census_county.py

    # Specific Census year only
    python load_census_county.py --years 2022

    # Dry run — show what would be fetched, no writes
    python load_census_county.py --dry-run

Output:
    pipeline/output/{STATE}.parquet  (county Census rows merged in)
    pipeline/output/athena_optimized/state_alpha={STATE}/data.parquet (updated)

Environment Variables:
    USDA_QUICKSTATS_API_KEY  - API key (or fetched from AWS SSM)
    AWS_REGION               - AWS region (default: us-east-2)
"""

import gc
import os
import sys
import re
import time
import logging
import argparse
from typing import Optional

import numpy as np
import pandas as pd

# Reuse shared helpers from quickstats_ingest
from quickstats_ingest import (
    get_api_key,
    api_get_data,
    clean_nass_value,
    _sanitize_error,
    _active_api_key,
    OUTPUT_DIR,
    US_STATE_CODES,
    COUNTY_COMMODITIES,
    COUNTY_REQUEST_DELAY,
)

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "census_county.log")),
    ],
)
logger = logging.getLogger(__name__)

# Census of Agriculture years available in QuickStats
CENSUS_YEARS = [2017, 2022]

# Stat categories available at county level from Census of Agriculture.
# These are NOT available in annual surveys.
CENSUS_COUNTY_STAT_CATS = [
    "SALES",
    "VALUE OF PRODUCTION",
]

# Livestock commodities available at county level from Census of Agriculture.
# Annual NASS surveys do not publish livestock at county resolution.
CENSUS_LIVESTOCK_COMMODITIES = [
    "CATTLE, INCL CALVES",
    "HOGS",
    "CHICKENS, BROILERS",
    "MILK",
]

CENSUS_LIVESTOCK_STAT_CATS = [
    "INVENTORY",
    "SALES",
]


def fetch_census_county_state(
    api_key: str,
    state: str,
    year: int,
    dry_run: bool = False,
) -> pd.DataFrame:
    """Fetch Census-of-Ag county data for one state and year.

    Covers:
      - SALES + VALUE OF PRODUCTION for COUNTY_COMMODITIES (crop commodities)
      - INVENTORY + SALES for livestock commodities

    Each API call is targeted (commodity + stat_cat pinned), so requests
    are well under 50K records. No sub-chunking needed.
    """
    if dry_run:
        logger.info(f"  [DRY RUN] Would fetch Census county: {state}/{year}")
        return pd.DataFrame()

    all_records = []

    # --- Crop commodities: SALES + VALUE OF PRODUCTION ---
    for commodity in COUNTY_COMMODITIES:
        for stat_cat in CENSUS_COUNTY_STAT_CATS:
            params = {
                "agg_level_desc": "COUNTY",
                "source_desc": "CENSUS",
                "year": str(year),
                "state_alpha": state,
                "commodity_desc": commodity,
                "statisticcat_desc": stat_cat,
            }
            time.sleep(COUNTY_REQUEST_DELAY)
            records = api_get_data(api_key, params)
            if records:
                all_records.extend(records)

    # --- Livestock commodities: INVENTORY + SALES ---
    for commodity in CENSUS_LIVESTOCK_COMMODITIES:
        for stat_cat in CENSUS_LIVESTOCK_STAT_CATS:
            params = {
                "agg_level_desc": "COUNTY",
                "source_desc": "CENSUS",
                "year": str(year),
                "state_alpha": state,
                "commodity_desc": commodity,
                "statisticcat_desc": stat_cat,
            }
            time.sleep(COUNTY_REQUEST_DELAY)
            records = api_get_data(api_key, params)
            if records:
                all_records.extend(records)

    if not all_records:
        return pd.DataFrame()

    df = pd.DataFrame(all_records)

    # Standardize FIPS columns
    if "state_fips_code" in df.columns:
        df["state_fips_code"] = df["state_fips_code"].astype(str).str.zfill(2)
    if "county_code" in df.columns and "state_fips_code" in df.columns:
        df["county_code"] = df["county_code"].astype(str).str.zfill(3)
        df["fips"] = df["state_fips_code"] + df["county_code"]
    if "Value" in df.columns:
        df["value_num"] = df["Value"].apply(clean_nass_value)
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

    df["dataset_source"] = "nass_census_county"

    logger.info(f"  Census {state}/{year}: {len(df):,} records")
    return df


def merge_into_state_parquet(state: str, new_df: pd.DataFrame) -> int:
    """Merge Census county rows into the existing state parquet file.

    Existing rows are preserved; new Census rows are appended and
    de-duplicated. Returns total rows after merge.
    """
    filename = f"{state}.parquet"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath):
        try:
            existing = pd.read_parquet(filepath)
            combined = pd.concat([existing, new_df], ignore_index=True)
            del existing
        except Exception as e:
            logger.warning(f"  Could not read {filename}, writing Census data standalone: {e}")
            combined = new_df.copy()
    else:
        logger.info(f"  No existing {filename} — writing Census data as new file")
        combined = new_df.copy()

    combined = combined.drop_duplicates()
    if "year" in combined.columns and "commodity_desc" in combined.columns:
        combined = combined.sort_values(["year", "commodity_desc"])

    # Write browser-fetch parquet
    combined.to_parquet(filepath, engine="pyarrow", compression="snappy", index=False)

    # Write Athena Hive-partitioned parquet
    athena_dir = os.path.join(OUTPUT_DIR, "athena_optimized")
    partition_dir = os.path.join(athena_dir, f"state_alpha={state}")
    os.makedirs(partition_dir, exist_ok=True)
    combined.to_parquet(
        os.path.join(partition_dir, "data.parquet"),
        engine="pyarrow",
        compression="snappy",
        index=False,
    )

    n = len(combined)
    del combined
    gc.collect()
    return n


def run_census_load(
    api_key: str,
    census_years: Optional[list[int]] = None,
    states_filter: Optional[list[str]] = None,
    dry_run: bool = False,
) -> bool:
    """Run the Census-of-Agriculture county data load.

    Args:
        api_key: USDA QuickStats API key
        census_years: Census years to load (default: CENSUS_YEARS = [2017, 2022])
        states_filter: Optional list of state codes (default: all US_STATE_CODES)
        dry_run: If True, fetch but do not write

    Returns:
        True if successful, False otherwise
    """
    years = census_years or CENSUS_YEARS
    states = states_filter or US_STATE_CODES
    total_fetched = 0

    logger.info("=" * 60)
    logger.info("Census of Agriculture County Data Loader")
    logger.info("=" * 60)
    logger.info(f"Census years: {years}")
    logger.info(f"States: {len(states)} {'(filtered)' if states_filter else '(all)'}")
    logger.info(f"Dry run: {dry_run}")
    logger.info("")

    for year in years:
        logger.info(f"--- Census year: {year} ---")
        for state in states:
            try:
                df = fetch_census_county_state(api_key, state, year, dry_run=dry_run)
                if df.empty:
                    continue
                if not dry_run:
                    merge_into_state_parquet(state, df)
                total_fetched += len(df)
                del df
            except Exception as e:
                logger.error(f"  Failed {state}/{year}: {_sanitize_error(e)}")
        logger.info("")

    logger.info(f"Census load complete. Total records: {total_fetched:,}")
    return total_fetched > 0


def main():
    parser = argparse.ArgumentParser(
        description="Load Census of Agriculture county data into state parquets"
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=CENSUS_YEARS,
        help=f"Census years to load (default: {CENSUS_YEARS})",
    )
    parser.add_argument(
        "--states",
        nargs="+",
        default=None,
        help="Filter to specific state codes (e.g., IN OH IL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not write to parquet files",
    )
    args = parser.parse_args()

    try:
        api_key = get_api_key()
        logger.info("API key loaded successfully")
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    success = run_census_load(
        api_key=api_key,
        census_years=args.years,
        states_filter=args.states,
        dry_run=args.dry_run,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
