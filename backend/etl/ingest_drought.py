"""Ingest US Drought Monitor county-level drought severity data.

Fetches D0-D4 drought category percentages per county from the USDM API.
Released weekly on Thursdays. No authentication required.

Usage: python -m backend.etl.ingest_drought [--date 2026-05-07] [--local-only]
"""

import argparse
import csv
import time as _time
from datetime import date, timedelta
from pathlib import Path

import requests

from backend.etl.common import get_env, setup_logging, log_ingest_summary

logger = setup_logging("ingest_drought")

USDM_API_BASE = "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent"
LOCAL_RAW_DIR = Path(__file__).parent / "data" / "drought_raw"


def fetch_drought_data(target_date: str) -> list[dict]:
    """Fetch county-level drought statistics for a given date.

    USDM API returns percentage of each county area in D0-D4 categories.
    """
    params = {
        "aoi": "county",
        "startdate": target_date,
        "enddate": target_date,
        "statisticsType": 2,  # Percent area
    }

    try:
        resp = requests.get(USDM_API_BASE, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error("USDM API request failed: %s", exc)
        return []

    if not data:
        logger.warning("No drought data returned for %s", target_date)
        return []

    rows = []
    for entry in data:
        fips = str(entry.get("FIPS", "")).zfill(5)
        if len(fips) != 5:
            continue

        # Extract D0-D4 percentages
        d0 = float(entry.get("D0", 0) or 0)
        d1 = float(entry.get("D1", 0) or 0)
        d2 = float(entry.get("D2", 0) or 0)
        d3 = float(entry.get("D3", 0) or 0)
        d4 = float(entry.get("D4", 0) or 0)
        none_pct = float(entry.get("None", 0) or 0)

        rows.append({
            "fips": fips,
            "date": target_date,
            "none_pct": round(none_pct, 2),
            "d0_pct": round(d0, 2),
            "d1_pct": round(d1, 2),
            "d2_pct": round(d2, 2),
            "d3_pct": round(d3, 2),
            "d4_pct": round(d4, 2),
            "d3d4_pct": round(d3 + d4, 2),
        })

    logger.info("Fetched drought data for %d counties on %s", len(rows), target_date)
    return rows


def save_local(rows: list[dict], target_date: str) -> Path:
    """Save drought data to local CSV."""
    week_label = target_date.replace("-", "")
    out_dir = LOCAL_RAW_DIR / week_label
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "usdm_county.csv"

    fieldnames = ["fips", "date", "none_pct", "d0_pct", "d1_pct", "d2_pct", "d3_pct", "d4_pct", "d3d4_pct"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Saved %d rows to %s", len(rows), out_path)
    return out_path


def upload_to_s3(local_path: Path, target_date: str):
    """Upload raw CSV to S3."""
    import boto3

    env = get_env()
    bucket = env.get("S3_BUCKET", "usda-analysis-datasets")
    week_label = target_date.replace("-", "")
    s3_key = f"raw/drought_monitor/{week_label}/usdm_county.csv"

    try:
        s3 = boto3.client("s3", region_name=env.get("AWS_REGION", "us-east-2"))
        s3.upload_file(str(local_path), bucket, s3_key)
        logger.info("Uploaded to s3://%s/%s", bucket, s3_key)
    except Exception as exc:
        logger.warning("S3 upload failed: %s", exc)


def get_latest_thursday() -> str:
    """Get the most recent Thursday (USDM release day)."""
    today = date.today()
    days_since_thursday = (today.weekday() - 3) % 7
    latest = today - timedelta(days=days_since_thursday)
    return str(latest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest US Drought Monitor county data")
    parser.add_argument("--date", default=get_latest_thursday(), help="Target date YYYY-MM-DD (should be a Thursday)")
    parser.add_argument("--local-only", action="store_true", help="Skip S3 upload")
    args = parser.parse_args()

    t0 = _time.time()
    rows = fetch_drought_data(args.date)

    if rows:
        local_path = save_local(rows, args.date)
        if not args.local_only:
            upload_to_s3(local_path, args.date)

    log_ingest_summary(logger, "drought_monitor", len(rows), _time.time() - t0)
