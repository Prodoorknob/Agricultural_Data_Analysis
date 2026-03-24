"""
incremental_check.py - Check for new data availability in USDA QuickStats

Compares current API record counts against the stored manifest to determine
if new data has been published since the last ingestion run.

Usage:
    python incremental_check.py

Exit codes:
    0 - No new data detected
    1 - New data detected (run quickstats_ingest.py)
    2 - Error during check
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

import requests

# Reuse constants from quickstats_ingest
from quickstats_ingest import (
    API_COUNT_ENDPOINT,
    SECTORS,
    DEFAULT_YEAR_START,
    DEFAULT_YEAR_END,
    MANIFEST_PATH,
    get_api_key,
    load_manifest,
    save_manifest,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
)
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def check_counts(api_key: str, manifest: dict) -> tuple[bool, dict]:
    """Check current API counts against manifest.

    Returns:
        (has_new_data, current_counts)
    """
    current_counts = {}
    has_new_data = False

    # Only check recent years to minimize API calls
    # Check last 3 years + current year
    current_year = datetime.now().year
    check_years = range(max(current_year - 2, DEFAULT_YEAR_START), current_year + 1)

    # ---- State-level count checks ----
    for sector in SECTORS:
        for year in check_years:
            key = f"{sector}_{year}"
            params = {
                "key": api_key,
                "source_desc": "SURVEY",
                "sector_desc": sector,
                "year": str(year),
            }

            for attempt in range(MAX_RETRIES):
                try:
                    resp = requests.get(API_COUNT_ENDPOINT, params=params, timeout=60)
                    resp.raise_for_status()
                    data = resp.json()
                    count = int(data.get("count", 0))
                    current_counts[key] = count

                    prev_count = manifest.get("record_counts", {}).get(key, 0)
                    if count > prev_count:
                        logger.info(
                            f"  NEW DATA: {key}: {prev_count:,} -> {count:,} (+{count - prev_count:,})"
                        )
                        has_new_data = True
                    else:
                        logger.info(f"  {key}: {count:,} (unchanged)")

                    time.sleep(0.3)
                    break
                except Exception as e:
                    wait = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.warning(f"  Check failed for {key}: {e}. Retry in {wait}s...")
                    time.sleep(wait)

    # ---- County-level count checks (Tier 1 crops only, most recent year) ----
    # Detect new Census-of-Ag releases or corrections to annual county data.
    logger.info("")
    logger.info("Checking county-level counts (Tier 1 crops, most recent year)...")
    tier1 = ["CORN", "SOYBEANS", "WINTER WHEAT"]
    for commodity in tier1:
        key = f"COUNTY_{commodity}_{current_year - 1}"
        params = {
            "key": api_key,
            "agg_level_desc": "COUNTY",
            "commodity_desc": commodity,
            "statisticcat_desc": "YIELD",
            "year": str(current_year - 1),
        }
        try:
            resp = requests.get(API_COUNT_ENDPOINT, params=params, timeout=60)
            resp.raise_for_status()
            count = int(resp.json().get("count", 0))
            current_counts[key] = count
            prev_count = manifest.get("record_counts", {}).get(key, 0)
            if count > prev_count:
                logger.info(f"  NEW COUNTY DATA: {key}: {prev_count:,} -> {count:,}")
                has_new_data = True
            else:
                logger.info(f"  {key}: {count:,} (unchanged)")
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"  County check failed for {key}: {e}")

    return has_new_data, current_counts


def main():
    logger.info("=" * 50)
    logger.info("USDA QuickStats Incremental Check")
    logger.info("=" * 50)

    try:
        api_key = get_api_key()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(2)

    manifest = load_manifest()
    last_success = manifest.get("last_success", "Never")
    logger.info(f"Last successful ingestion: {last_success}")
    logger.info("")

    has_new_data, current_counts = check_counts(api_key, manifest)

    logger.info("")
    if has_new_data:
        logger.info("RESULT: New data detected. Run quickstats_ingest.py to update.")
        sys.exit(1)
    else:
        logger.info("RESULT: No new data detected. Pipeline is up to date.")
        sys.exit(0)


if __name__ == "__main__":
    main()
