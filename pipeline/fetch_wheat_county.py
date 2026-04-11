"""Fetch county-level WINTER WHEAT yield data from NASS QuickStats API.

The main county ingestion pipeline had wheat in its commodity list but the data
may not have been included in the S3 upload. This script specifically fetches
WINTER WHEAT county YIELD data and merges it into the existing county parquets.

Usage: python pipeline/fetch_wheat_county.py [--years 2001-2025] [--upload-s3]
"""

import os
import re
import sys
import time
import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

# Setup
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fetch_wheat_county")

QUICKSTATS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
OUTPUT_DIR = PROJECT_ROOT / "pipeline" / "output"

# Wheat commodity names in NASS
# "WHEAT" is the aggregated commodity that includes all wheat types at county level
WHEAT_COMMODITIES = ["WHEAT"]

# Stat categories to fetch
STAT_CATS = ["YIELD", "AREA PLANTED", "AREA HARVESTED", "PRODUCTION"]

# States to skip (no significant wheat production)
SKIP_STATES = {
    "WINTER WHEAT": {"ALASKA", "HAWAII"},
    "SPRING WHEAT, (EXCL DURUM)": {
        "ALASKA", "HAWAII", "ALABAMA", "FLORIDA", "GEORGIA", "SOUTH CAROLINA",
        "MISSISSIPPI", "LOUISIANA", "TEXAS", "ARIZONA", "NEW MEXICO", "NEVADA",
        "UTAH", "ARKANSAS", "TENNESSEE", "KENTUCKY", "WEST VIRGINIA", "VIRGINIA",
        "NORTH CAROLINA", "RHODE ISLAND", "CONNECTICUT", "MASSACHUSETTS",
        "NEW HAMPSHIRE", "VERMONT", "MAINE", "NEW JERSEY", "DELAWARE", "MARYLAND",
        "PENNSYLVANIA",
    },
}

# All 50 states
ALL_STATES = [
    "ALABAMA", "ALASKA", "ARIZONA", "ARKANSAS", "CALIFORNIA", "COLORADO",
    "CONNECTICUT", "DELAWARE", "FLORIDA", "GEORGIA", "IDAHO", "ILLINOIS",
    "INDIANA", "IOWA", "KANSAS", "KENTUCKY", "LOUISIANA", "MAINE", "MARYLAND",
    "MASSACHUSETTS", "MICHIGAN", "MINNESOTA", "MISSISSIPPI", "MISSOURI",
    "MONTANA", "NEBRASKA", "NEVADA", "NEW HAMPSHIRE", "NEW JERSEY", "NEW MEXICO",
    "NEW YORK", "NORTH CAROLINA", "NORTH DAKOTA", "OHIO", "OKLAHOMA", "OREGON",
    "PENNSYLVANIA", "RHODE ISLAND", "SOUTH CAROLINA", "SOUTH DAKOTA", "TENNESSEE",
    "TEXAS", "UTAH", "VERMONT", "VIRGINIA", "WASHINGTON", "WEST VIRGINIA",
    "WISCONSIN", "WYOMING",
]

# State name -> postal code
STATE_ABBR = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE",
    "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
}


def get_api_key() -> str:
    """Load API key from .env file."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("QUICKSTATS_API_KEY="):
                    return line.split("=", 1)[1].strip()
    key = os.environ.get("QUICKSTATS_API_KEY", "")
    if not key:
        raise ValueError("QUICKSTATS_API_KEY not found")
    return key


def fetch_county_wheat(api_key: str, state_alpha: str, commodity: str, year: int, max_retries: int = 3) -> pd.DataFrame:
    """Fetch county-level wheat data for a single state + year.

    Uses state_alpha (2-letter code) and fetches one year at a time,
    matching the pattern from quickstats_ingest.py.
    """
    params = {
        "key": api_key,
        "commodity_desc": commodity,
        "agg_level_desc": "COUNTY",
        "state_alpha": state_alpha,
        "year": str(year),
        "source_desc": "SURVEY",
        "format": "JSON",
    }

    for attempt in range(max_retries):
        try:
            resp = requests.get(QUICKSTATS_URL, params=params, timeout=30)
            if resp.status_code == 400:
                # 400 = no data for this state/commodity/year
                return pd.DataFrame()
            if resp.status_code == 403:
                # Rate limited — back off and retry
                wait = 30 * (attempt + 1)
                logger.warning("  %s %s %d: Rate limited (403). Waiting %ds...", state_alpha, commodity, year, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.warning("  %s %s %d: API error — %s", state_alpha, commodity, year, exc)
            if attempt < max_retries - 1:
                time.sleep(10)
                continue
            return pd.DataFrame()

        rows = data.get("data", [])
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        # Filter to yield/area/production stat categories
        if "statisticcat_desc" in df.columns:
            df = df[df["statisticcat_desc"].isin(STAT_CATS)]
        return df

    return pd.DataFrame()


def clean_value(val):
    """Clean NASS value field — remove commas, handle special codes."""
    if pd.isna(val):
        return None
    val = str(val).strip()
    # NASS special codes
    if val in ("(D)", "(Z)", "(NA)", "(X)", "(S)", "(L)", "(H)", ""):
        return None
    val = val.replace(",", "")
    try:
        return float(val)
    except ValueError:
        return None


def run_fetch(api_key: str, year_start: int, year_end: int):
    """Fetch wheat county data for all states, commodities, and years."""
    all_dfs = []

    # Top wheat states (use 2-letter postal codes)
    wheat_states = [
        "KS", "ND", "MT", "WA", "OK", "SD", "TX", "CO", "NE", "MN",
        "OR", "ID", "IL", "OH", "IN", "MO", "MI", "PA", "NY", "VA",
        "NC", "GA", "AR", "CA", "WI", "MD", "DE", "KY", "TN", "SC",
    ]

    skip_map = {}

    total_fetched = 0
    for commodity in WHEAT_COMMODITIES:
        skip = skip_map.get(commodity, set())
        logger.info("Fetching %s county data...", commodity)

        for state_alpha in wheat_states:
            if state_alpha in skip:
                continue

            state_total = 0
            for year in range(year_start, year_end + 1):
                df = fetch_county_wheat(api_key, state_alpha, commodity, year)
                if not df.empty:
                    all_dfs.append(df)
                    state_total += len(df)

                time.sleep(2.0)  # Conservative rate limit to avoid 403s

            if state_total > 0:
                logger.info("  %s %s: %d total rows", state_alpha, commodity, state_total)
            total_fetched += state_total

        logger.info("  %s subtotal: %d rows", commodity, total_fetched)

    if not all_dfs:
        logger.warning("No wheat county data fetched!")
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    logger.info("Total wheat county rows: %d", len(combined))
    return combined


def process_and_save(df: pd.DataFrame):
    """Process fetched wheat data and merge into existing county parquets."""
    if df.empty:
        return

    # Add computed columns matching pipeline output schema
    df["value_num"] = df["Value"].apply(clean_value)

    # Build FIPS code
    df["state_fips_code"] = df["state_fips_code"].astype(str).str.zfill(2)
    df["county_code"] = df["county_code"].astype(str).str.zfill(3)
    df["fips"] = df["state_fips_code"] + df["county_code"]

    # Ensure year is int
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")

    # Add dataset_source tag
    df["dataset_source"] = "nass_wheat_county"

    # Group by state and merge into existing parquets
    output_dir = PROJECT_ROOT / "backend" / "etl" / "data" / "county_parquets"
    output_dir.mkdir(parents=True, exist_ok=True)

    states_updated = 0
    for state_alpha, state_df in df.groupby("state_alpha"):
        parquet_path = output_dir / f"{state_alpha}.parquet"

        if parquet_path.exists():
            # Merge with existing data
            existing = pd.read_parquet(parquet_path)
            # Remove any existing wheat rows to avoid duplicates
            existing = existing[~existing["commodity_desc"].isin(WHEAT_COMMODITIES)]
            merged = pd.concat([existing, state_df], ignore_index=True)
            merged = merged.drop_duplicates(
                subset=["commodity_desc", "statisticcat_desc", "state_fips_code",
                         "county_code", "year", "source_desc"],
                keep="last",
            )
        else:
            merged = state_df

        merged.to_parquet(parquet_path, index=False, engine="pyarrow")
        states_updated += 1
        logger.info("Updated %s.parquet: %d total rows (wheat: %d)",
                     state_alpha, len(merged), len(state_df))

    logger.info("Updated %d state parquet files with wheat data", states_updated)

    # Also save wheat-only data for reference
    wheat_path = output_dir / "_wheat_all.parquet"
    df.to_parquet(wheat_path, index=False, engine="pyarrow")
    logger.info("Saved wheat-only data to %s (%d rows)", wheat_path, len(df))


def upload_to_s3():
    """Sync updated county parquets to S3."""
    import subprocess

    source_dir = PROJECT_ROOT / "backend" / "etl" / "data" / "county_parquets"
    s3_prefix = "s3://usda-analysis-datasets/survey_datasets/partitioned_states_counties/"

    logger.info("Uploading updated county parquets to S3...")
    try:
        subprocess.run(
            ["aws", "s3", "sync", str(source_dir), s3_prefix,
             "--exclude", "_*",  # Skip temp/meta files
             "--region", "us-east-2", "--quiet"],
            check=True, timeout=120,
        )
        logger.info("S3 upload complete")
    except Exception as exc:
        logger.warning("S3 upload failed: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch wheat county yield data from NASS")
    parser.add_argument("--year-start", type=int, default=2001)
    parser.add_argument("--year-end", type=int, default=2025)
    parser.add_argument("--upload-s3", action="store_true", help="Upload updated parquets to S3")
    args = parser.parse_args()

    t0 = time.time()
    api_key = get_api_key()

    logger.info("Fetching wheat county data for %d-%d", args.year_start, args.year_end)
    df = run_fetch(api_key, args.year_start, args.year_end)
    process_and_save(df)

    if args.upload_s3:
        upload_to_s3()

    elapsed = time.time() - t0
    logger.info("Done in %.1f minutes", elapsed / 60)
