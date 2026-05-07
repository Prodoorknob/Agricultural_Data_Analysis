"""Backfill NOAA HURDAT2 Atlantic tropical cyclone tracks into a parquet cache.

The yield-model fix v1 deferred a hurricane/flood feature, leaving NC corn
2024 (Tropical Storm Debby + Hurricane Helene) as the dominant outlier
class. This script downloads the HURDAT2 Atlantic best-track database
(1851-2025), parses the multi-line storm + per-6h track records, and
writes a flat parquet that ``train_yield.attach_hurricane_features`` reads.

Output columns at ``backend/etl/data/hurdat2.parquet``:
  storm_id (e.g. AL022024)        — HURDAT2 system id
  storm_name                       — e.g. "DEBBY"
  date                             — track point timestamp (UTC)
  status                           — TD / TS / HU / SS / SD / EX / LO
  is_landfall                      — bool, true when record marker == 'L'
  lat, lon                         — float decimal degrees
  max_wind_kt                      — int, sustained wind kts (-999 → NaN)
  min_pressure_mb                  — int, central pressure (-999 → NaN)

Status filtering happens at feature time, not here.

Usage:
  python -m backend.etl.backfill_hurdat2
  python -m backend.etl.backfill_hurdat2 --url <override>
"""

import argparse
import re
import time as _time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from backend.etl.common import setup_logging

logger = setup_logging("backfill_hurdat2")

DEFAULT_URL = "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-02272026.txt"
DEFAULT_OUTPUT = Path(__file__).parent / "data" / "hurdat2.parquet"

HEADER_RE = re.compile(r"^(AL\d{2}\d{4})\s*,\s*([^,]+?)\s*,\s*(\d+)\s*,?\s*$")


def _parse_lat(s: str) -> float:
    s = s.strip()
    sign = 1 if s[-1] == "N" else -1
    return sign * float(s[:-1])


def _parse_lon(s: str) -> float:
    s = s.strip()
    sign = -1 if s[-1] == "W" else 1
    return sign * float(s[:-1])


def parse_hurdat2(text: str) -> pd.DataFrame:
    rows: list[dict] = []
    storm_id = ""
    storm_name = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = HEADER_RE.match(line)
        if m:
            storm_id, storm_name, _ = m.groups()
            storm_name = storm_name.strip()
            continue
        # Track record. First two cols are date and time.
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue
        ymd, hhmm, ident, status, lat_s, lon_s, wind_s, pres_s = parts[:8]
        try:
            dt = datetime.strptime(ymd + hhmm, "%Y%m%d%H%M")
        except ValueError:
            continue
        try:
            lat = _parse_lat(lat_s)
            lon = _parse_lon(lon_s)
        except (ValueError, IndexError):
            continue
        try:
            wind = int(wind_s)
            wind_val = float(wind) if wind != -999 else float("nan")
        except ValueError:
            wind_val = float("nan")
        try:
            pres = int(pres_s)
            pres_val = float(pres) if pres != -999 else float("nan")
        except ValueError:
            pres_val = float("nan")
        rows.append({
            "storm_id": storm_id,
            "storm_name": storm_name,
            "date": dt,
            "status": status,
            "is_landfall": ident == "L",
            "lat": lat,
            "lon": lon,
            "max_wind_kt": wind_val,
            "min_pressure_mb": pres_val,
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download + parse HURDAT2 Atlantic best-track")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--year-start", type=int, default=1990,
                        help="Drop rows with year < this. The yield-model "
                        "training panel starts at 2001; we keep a small "
                        "lead-in for any future research uses.")
    args = parser.parse_args()

    t0 = _time.time()
    logger.info("Fetching HURDAT2 from %s", args.url)
    resp = requests.get(args.url, timeout=120)
    resp.raise_for_status()
    text = resp.text
    logger.info("Downloaded %.1f MB in %.1fs", len(text) / 1e6, _time.time() - t0)

    df = parse_hurdat2(text)
    logger.info(
        "Parsed %d track points spanning %d storms (%d..%d)",
        len(df),
        df["storm_id"].nunique(),
        df["date"].dt.year.min(),
        df["date"].dt.year.max(),
    )

    df = df[df["date"].dt.year >= args.year_start].reset_index(drop=True)
    logger.info(
        "Filtered to year >= %d: %d rows, %d storms",
        args.year_start, len(df), df["storm_id"].nunique(),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, index=False)
    logger.info("Wrote %s in %.1fs", args.output, _time.time() - t0)


if __name__ == "__main__":
    main()
