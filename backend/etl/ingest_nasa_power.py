"""Ingest NASA POWER daily weather data (solar radiation, VPD) for crop counties.

Uses the NASA POWER API to fetch gridded daily weather data by county centroid.
No authentication required. 2-day data lag, always complete (no gaps).

Usage: python -m backend.etl.ingest_nasa_power [--start-date 2026-05-01] [--end-date 2026-05-07] [--local-only]
"""

import argparse
import csv
import math
import time as _time
from datetime import date, timedelta
from pathlib import Path

import requests

from backend.etl.common import get_env, setup_logging, log_ingest_summary

logger = setup_logging("ingest_nasa_power")

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = "T2M_MAX,T2M_MIN,T2MDEW,ALLSKY_SFC_SW_DWN"
LOCAL_RAW_DIR = Path(__file__).parent / "data" / "nasa_power_raw"


def compute_vpd(tmax_c: float, tdew_c: float) -> float:
    """Compute Vapor Pressure Deficit (kPa) from max temp and dewpoint (Celsius).

    VPD = es(Tmax) - es(Tdew)
    es(T) = 0.6108 * exp(17.27 * T / (T + 237.3))
    """
    def saturation_vp(t: float) -> float:
        return 0.6108 * math.exp(17.27 * t / (t + 237.3))

    return max(0.0, saturation_vp(tmax_c) - saturation_vp(tdew_c))


def fetch_county_power(lat: float, lon: float, start_date: str, end_date: str) -> list[dict]:
    """Fetch NASA POWER daily data for a single point (county centroid)."""
    # NASA POWER API expects YYYYMMDD format
    start_fmt = start_date.replace("-", "")
    end_fmt = end_date.replace("-", "")

    params = {
        "parameters": PARAMETERS,
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start_fmt,
        "end": end_fmt,
        "format": "JSON",
    }

    try:
        resp = requests.get(NASA_POWER_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("NASA POWER request failed for (%.4f, %.4f): %s", lat, lon, exc)
        return []

    # Parse the nested response structure
    properties = data.get("properties", {})
    params_data = properties.get("parameter", {})

    if not params_data:
        return []

    t2m_max = params_data.get("T2M_MAX", {})
    t2m_min = params_data.get("T2M_MIN", {})
    t2m_dew = params_data.get("T2MDEW", {})
    solar = params_data.get("ALLSKY_SFC_SW_DWN", {})

    rows = []
    for date_key in sorted(t2m_max.keys()):
        tmax_c = t2m_max.get(date_key, -999)
        tmin_c = t2m_min.get(date_key, -999)
        tdew_c = t2m_dew.get(date_key, -999)
        solar_val = solar.get(date_key, -999)

        # NASA POWER uses -999 for missing
        if any(v == -999 for v in (tmax_c, tmin_c, tdew_c, solar_val)):
            continue

        # Convert date key YYYYMMDD to YYYY-MM-DD
        obs_date = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:8]}"

        # Compute VPD
        vpd = compute_vpd(tmax_c, tdew_c)

        # Convert temps to Fahrenheit for GDD computation
        tmax_f = tmax_c * 9 / 5 + 32
        tmin_f = tmin_c * 9 / 5 + 32

        rows.append({
            "date": obs_date,
            "tmax_c": round(tmax_c, 2),
            "tmin_c": round(tmin_c, 2),
            "tmax_f": round(tmax_f, 2),
            "tmin_f": round(tmin_f, 2),
            "tdew_c": round(tdew_c, 2),
            "vpd_kpa": round(vpd, 3),
            "solar_mj_m2": round(solar_val, 2),
        })

    return rows


def fetch_all_counties(
    centroids: dict[str, tuple[float, float]],
    start_date: str,
    end_date: str,
    batch_size: int = 100,
) -> list[dict]:
    """Fetch NASA POWER data for all counties.

    NASA POWER API has no strict rate limit but we pace requests to be polite.
    """
    all_rows = []
    total = len(centroids)
    fetched = 0

    for fips, (lat, lon) in centroids.items():
        daily = fetch_county_power(lat, lon, start_date, end_date)
        for row in daily:
            row["fips"] = fips
        all_rows.extend(daily)

        fetched += 1
        if fetched % batch_size == 0:
            logger.info("Fetched %d/%d counties (%d rows)", fetched, total, len(all_rows))
            _time.sleep(2)  # Pause between batches
        else:
            _time.sleep(0.1)

    logger.info("Total NASA POWER rows: %d from %d counties", len(all_rows), total)
    return all_rows


def save_local(rows: list[dict], start_date: str) -> Path:
    """Save raw data to local CSV."""
    week_label = start_date.replace("-", "")
    out_dir = LOCAL_RAW_DIR / week_label
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "solar_vpd.csv"

    fieldnames = ["fips", "date", "tmax_c", "tmin_c", "tmax_f", "tmin_f", "tdew_c", "vpd_kpa", "solar_mj_m2"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
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
    s3_key = f"raw/nasa_power/{week_label}/solar_vpd.csv"

    try:
        s3 = boto3.client("s3", region_name=env.get("AWS_REGION", "us-east-2"))
        s3.upload_file(str(local_path), bucket, s3_key)
        logger.info("Uploaded to s3://%s/%s", bucket, s3_key)
    except Exception as exc:
        logger.warning("S3 upload failed: %s", exc)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest NASA POWER daily weather data")
    today = date.today()
    week_ago = today - timedelta(days=9)  # 2-day lag
    data_end = today - timedelta(days=2)
    parser.add_argument("--start-date", default=str(week_ago), help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", default=str(data_end), help="End date YYYY-MM-DD")
    parser.add_argument("--local-only", action="store_true", help="Skip S3 upload")
    args = parser.parse_args()

    t0 = _time.time()

    from backend.etl.load_county_centroids import load_centroids
    centroids = load_centroids()

    rows = fetch_all_counties(centroids, args.start_date, args.end_date)
    local_path = save_local(rows, args.start_date)

    if not args.local_only:
        upload_to_s3(local_path, args.start_date)

    log_ingest_summary(logger, "nasa_power", len(rows), _time.time() - t0)
