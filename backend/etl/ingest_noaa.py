"""Ingest NOAA GHCN-Daily weather data (TMAX, TMIN, PRCP) for crop counties.

Fetches daily observations from the NOAA Climate Data Online API, maps station
data to county FIPS codes, and stores raw CSVs on S3 for feature engineering.

Usage: python -m backend.etl.ingest_noaa [--start-date 2026-05-01] [--end-date 2026-05-07] [--local-only]
"""

import argparse
import csv
import io
import os
import time as _time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from backend.etl.common import get_env, setup_logging, log_ingest_summary

logger = setup_logging("ingest_noaa")

NOAA_API_BASE = "https://www.ncei.noaa.gov/cdo-web/api/v2/data"
DATATYPES = "TMAX,TMIN,PRCP"
DATASET_ID = "GHCND"
LOCAL_RAW_DIR = Path(__file__).parent / "data" / "noaa_raw"


def _get_api_token() -> str:
    """Get NOAA API token from environment."""
    env = get_env()
    token = env.get("NOAA_API_KEY", "")
    if not token:
        raise ValueError("NOAA_API_KEY not found in .env")
    return token


def fetch_station_data(
    station_id: str,
    start_date: str,
    end_date: str,
    token: str,
) -> list[dict]:
    """Fetch GHCN-Daily data for a single station."""
    headers = {"token": token}
    params = {
        "datasetid": DATASET_ID,
        "stationid": f"GHCND:{station_id}",
        "datatypeid": DATATYPES,
        "startdate": start_date,
        "enddate": end_date,
        "units": "standard",  # Fahrenheit for temps, inches for precip
        "limit": 1000,
    }

    try:
        resp = requests.get(NOAA_API_BASE, headers=headers, params=params, timeout=30)
        if resp.status_code == 429:
            logger.warning("Rate limited. Sleeping 60s...")
            _time.sleep(60)
            resp = requests.get(NOAA_API_BASE, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except requests.RequestException as exc:
        logger.warning("Failed to fetch station %s: %s", station_id, exc)
        return []


def pivot_daily_obs(results: list[dict]) -> list[dict]:
    """Pivot NOAA API results from long format to daily rows with TMAX/TMIN/PRCP columns."""
    daily: dict[str, dict] = {}
    for row in results:
        obs_date = row["date"][:10]  # "2026-05-01T00:00:00" -> "2026-05-01"
        dtype = row["datatype"]
        value = row["value"]

        if obs_date not in daily:
            daily[obs_date] = {"date": obs_date, "TMAX": None, "TMIN": None, "PRCP": None}
        daily[obs_date][dtype] = value

    return list(daily.values())


def fetch_county_weather(
    station_map: dict[str, str],
    start_date: str,
    end_date: str,
    token: str,
    batch_size: int = 50,
) -> list[dict]:
    """Fetch weather data for all counties using station mapping.

    Args:
        station_map: {fips: station_id}
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD
        token: NOAA API token
        batch_size: how many stations to fetch before pausing
    """
    all_rows = []
    unique_stations = {}

    # Deduplicate: multiple counties may share a station
    for fips, station_id in station_map.items():
        if not station_id:  # NASA POWER fallback counties
            continue
        unique_stations.setdefault(station_id, []).append(fips)

    logger.info("Fetching data for %d unique stations covering %d counties",
                len(unique_stations), sum(len(v) for v in unique_stations.values()))

    fetched = 0
    for station_id, fips_list in unique_stations.items():
        results = fetch_station_data(station_id, start_date, end_date, token)
        daily_obs = pivot_daily_obs(results)

        for obs in daily_obs:
            for fips in fips_list:
                all_rows.append({
                    "fips": fips,
                    "station_id": station_id,
                    "date": obs["date"],
                    "tmax_f": obs["TMAX"],
                    "tmin_f": obs["TMIN"],
                    "prcp_in": obs["PRCP"],
                })

        fetched += 1
        if fetched % batch_size == 0:
            logger.info("Fetched %d/%d stations", fetched, len(unique_stations))
            _time.sleep(1)  # Rate limit: max 5 req/sec, 1000/day
        else:
            _time.sleep(0.25)

    logger.info("Total weather rows: %d", len(all_rows))
    return all_rows


def save_local(rows: list[dict], start_date: str, end_date: str):
    """Save raw weather data to local CSV."""
    week_label = start_date.replace("-", "")
    out_dir = LOCAL_RAW_DIR / week_label
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "daily_obs.csv"

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    logger.info("Saved %d rows to %s", len(rows), out_path)
    return out_path


def upload_to_s3(local_path: Path, start_date: str):
    """Upload raw CSV to S3."""
    import boto3

    env = get_env()
    bucket = env.get("S3_BUCKET", "usda-analysis-datasets")
    week_label = start_date.replace("-", "")
    s3_key = f"raw/noaa/{week_label}/daily_obs.csv"

    try:
        s3 = boto3.client("s3", region_name=env.get("AWS_REGION", "us-east-2"))
        s3.upload_file(str(local_path), bucket, s3_key)
        logger.info("Uploaded to s3://%s/%s", bucket, s3_key)
    except Exception as exc:
        logger.warning("S3 upload failed: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest NOAA GHCN-Daily weather data")
    today = date.today()
    week_ago = today - timedelta(days=7)
    parser.add_argument("--start-date", default=str(week_ago), help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", default=str(today), help="End date YYYY-MM-DD")
    parser.add_argument("--local-only", action="store_true", help="Skip S3 upload")
    args = parser.parse_args()

    t0 = _time.time()
    token = _get_api_token()

    # Load station mapping
    from backend.etl.build_station_map import load_station_map
    station_map = load_station_map()

    rows = fetch_county_weather(station_map, args.start_date, args.end_date, token)
    local_path = save_local(rows, args.start_date, args.end_date)

    if not args.local_only:
        upload_to_s3(local_path, args.start_date)

    log_ingest_summary(logger, "noaa_weather", len(rows), _time.time() - t0)
