"""Ingest NASS weekly crop condition ratings and compute CCI.

Fetches weekly Crop Condition ratings (Excellent/Good/Fair/Poor/Very Poor)
from USDA QuickStats API, computes the Crop Condition Index (CCI), and
stores raw data on S3 for feature engineering.

CCI formula: CCI = 2*(Excellent + Good) + 0*Fair - 2*(Poor + Very Poor)
Range: roughly -200 to +200 (before dividing by 100).

Usage: python -m backend.etl.ingest_crop_conditions [--year 2026] [--local-only]
"""

import argparse
import csv
import json
import time as _time
from datetime import date
from pathlib import Path

import requests

from backend.etl.common import get_env, setup_logging, log_ingest_summary

logger = setup_logging("ingest_crop_conditions")

QUICKSTATS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
LOCAL_RAW_DIR = Path(__file__).parent / "data" / "crop_conditions_raw"

COMMODITIES = {
    "corn": "CORN",
    "soybean": "SOYBEANS",
    "wheat": "WHEAT",
}

# Condition rating -> CCI weight
CCI_WEIGHTS = {
    "EXCELLENT": 2,
    "GOOD": 1,
    "FAIR": 0,
    "POOR": -1,
    "VERY POOR": -2,
}


def _get_api_key() -> str:
    """Get NASS QuickStats API key."""
    env = get_env()
    key = env.get("QUICKSTATS_API_KEY", "") or env.get("USDA_QUICKSTATS_API_KEY", "")
    if not key:
        raise ValueError("QUICKSTATS_API_KEY not found in .env")
    return key


def fetch_conditions(commodity_nass: str, year: int, api_key: str) -> list[dict]:
    """Fetch weekly crop condition ratings from NASS QuickStats.

    Returns state-level weekly percentages for each condition category.
    """
    params = {
        "key": api_key,
        "commodity_desc": commodity_nass,
        "statisticcat_desc": "CONDITION",
        "unit_desc": "PCT OF CROP RATED",
        "freq_desc": "WEEKLY",
        "year": str(year),
        "agg_level_desc": "STATE",
        "format": "JSON",
    }

    try:
        resp = requests.get(QUICKSTATS_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error("NASS API request failed for %s %d: %s", commodity_nass, year, exc)
        return []

    rows = data.get("data", [])
    logger.info("Fetched %d condition rows for %s %d", len(rows), commodity_nass, year)
    return rows


def compute_cci_by_state_week(raw_rows: list[dict]) -> list[dict]:
    """Aggregate condition ratings into CCI per state per week.

    Groups by (state_fips, reference_period) and computes:
    CCI = sum(weight * percentage) for each rating category.
    """
    # Group by state + week
    groups: dict[tuple[str, str, str], dict[str, float]] = {}

    for row in raw_rows:
        state_fips = str(row.get("state_fips_code", "")).zfill(2)
        week_ref = row.get("reference_period_desc", "")  # e.g., "WEEK #12"
        short_desc = row.get("short_desc", "")

        # Extract rating category from short_desc
        # e.g., "CORN - CONDITION, MEASURED IN PCT OF CROP RATED EXCELLENT"
        rating = None
        for cat in CCI_WEIGHTS:
            if cat in short_desc.upper():
                rating = cat
                break

        if not rating:
            continue

        value_str = str(row.get("Value", "")).strip().replace(",", "")
        try:
            value = float(value_str)
        except (ValueError, TypeError):
            continue

        key = (state_fips, week_ref, row.get("commodity_desc", ""))
        groups.setdefault(key, {})[rating] = value

    # Compute CCI for each group
    results = []
    for (state_fips, week_ref, commodity), ratings in groups.items():
        cci = sum(CCI_WEIGHTS.get(cat, 0) * ratings.get(cat, 0) for cat in CCI_WEIGHTS)

        # Extract week number from "WEEK #12"
        week_num = None
        if "WEEK #" in week_ref:
            try:
                week_num = int(week_ref.split("#")[1].strip())
            except (IndexError, ValueError):
                pass

        results.append({
            "state_fips": state_fips,
            "commodity": commodity,
            "week_ref": week_ref,
            "week_num": week_num,
            "pct_excellent": ratings.get("EXCELLENT", 0),
            "pct_good": ratings.get("GOOD", 0),
            "pct_fair": ratings.get("FAIR", 0),
            "pct_poor": ratings.get("POOR", 0),
            "pct_very_poor": ratings.get("VERY POOR", 0),
            "cci": round(cci, 1),
        })

    results.sort(key=lambda x: (x["state_fips"], x["week_num"] or 0))
    return results


def save_local(rows: list[dict], year: int, commodity: str) -> Path:
    """Save CCI data to local CSV."""
    out_dir = LOCAL_RAW_DIR / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{commodity}_conditions.csv"

    fieldnames = [
        "state_fips", "commodity", "week_ref", "week_num",
        "pct_excellent", "pct_good", "pct_fair", "pct_poor", "pct_very_poor", "cci",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Saved %d CCI rows to %s", len(rows), out_path)
    return out_path


def save_raw_json(raw_rows: list[dict], year: int, commodity: str) -> Path:
    """Save raw NASS response to JSON for archival."""
    out_dir = LOCAL_RAW_DIR / str(year)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{commodity}_raw.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw_rows, f, indent=2, default=str)
    return out_path


def upload_to_s3(local_path: Path, year: int, commodity: str):
    """Upload to S3."""
    import boto3

    env = get_env()
    bucket = env.get("S3_BUCKET", "usda-analysis-datasets")
    s3_key = f"raw/nass/{year}/{commodity}_conditions.csv"

    try:
        s3 = boto3.client("s3", region_name=env.get("AWS_REGION", "us-east-2"))
        s3.upload_file(str(local_path), bucket, s3_key)
        logger.info("Uploaded to s3://%s/%s", bucket, s3_key)
    except Exception as exc:
        logger.warning("S3 upload failed: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest NASS crop condition ratings")
    parser.add_argument("--year", type=int, default=date.today().year, help="Crop year")
    parser.add_argument("--commodity", default="all", help="corn|soybean|wheat|all")
    parser.add_argument("--local-only", action="store_true", help="Skip S3 upload")
    args = parser.parse_args()

    t0 = _time.time()
    api_key = _get_api_key()
    total_rows = 0

    commodities = COMMODITIES if args.commodity == "all" else {args.commodity: COMMODITIES[args.commodity]}

    for comm_key, comm_nass in commodities.items():
        raw = fetch_conditions(comm_nass, args.year, api_key)
        if not raw:
            continue

        save_raw_json(raw, args.year, comm_key)
        cci_rows = compute_cci_by_state_week(raw)
        local_path = save_local(cci_rows, args.year, comm_key)
        total_rows += len(cci_rows)

        if not args.local_only:
            upload_to_s3(local_path, args.year, comm_key)

        _time.sleep(1)  # Rate limit between commodities

    log_ingest_summary(logger, "crop_conditions", total_rows, _time.time() - t0)
