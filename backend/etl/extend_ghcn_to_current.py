"""Extend the consolidated GHCN parquet with current-year data.

The original ``county_weather_2000_2025.parquet`` was built once from a
bulk GHCN-Daily snapshot. To support live in-season inference (2026
forecasts during the 2026 growing season), we need 2026-01-01 through
today's daily TMAX / TMIN / PRCP appended to the same file shape.

This pulls from NCEI's Access date-range API (no auth, supports
batched stations + date filters), converts metric → the parquet's
existing imperial format, joins via station_county_map, and appends
into a new ``county_weather_2000_<thru-year>.parquet``. The stale 2025
file is left in place so this is reversible — we just point train_yield
at the newer file via the GHCN_PATH update.

Usage:
    python -m backend.etl.extend_ghcn_to_current
    python -m backend.etl.extend_ghcn_to_current --start 2026-01-01 --end 2026-05-07

API behavior:
- ``https://www.ncei.noaa.gov/access/services/data/v1`` returns CSV with
  metric units when ``units=metric`` (PRCP in mm, TMAX/TMIN in °C).
- Up to ~50 stations per request keeps URLs under server limits while
  amortizing per-call overhead. ~3,200 stations / 50 = ~65 batches at
  ~1 sec each → ~1-2 min total.
"""

import argparse
import csv
import io
import time as _time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from backend.etl.common import setup_logging

logger = setup_logging("extend_ghcn")

ACCESS_API = "https://www.ncei.noaa.gov/access/services/data/v1"
DATA_DIR = Path(__file__).parent / "data"
GHCN_DIR = DATA_DIR / "ghcn_processed"
STATION_MAP_PATH = DATA_DIR / "station_county_map.csv"
EXISTING_PARQUET = GHCN_DIR / "county_weather_2000_2025.parquet"


def fetch_batch(stations: list[str], start: date, end: date, session: requests.Session) -> str:
    """Fetch one batch of stations in CSV form. Returns raw CSV text."""
    params = {
        "dataset": "daily-summaries",
        "dataTypes": "TMAX,TMIN,PRCP",
        "stations": ",".join(stations),
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "format": "csv",
        "units": "metric",
    }
    resp = session.get(ACCESS_API, params=params, timeout=120)
    resp.raise_for_status()
    return resp.text


def parse_batch(csv_text: str) -> pd.DataFrame:
    """CSV → DataFrame with imperial units matching the existing parquet."""
    if not csv_text or csv_text.count("\n") <= 1:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(csv_text), dtype={"STATION": str})
    df = df.rename(columns={"STATION": "station_id", "DATE": "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["station_id", "date"])
    # Keep rows that have at least one of TMAX/TMIN/PRCP — we drop fully-blank
    # ones. The existing parquet allows partial rows so we mirror that.
    have_cols = [c for c in ("PRCP", "TMAX", "TMIN") if c in df.columns]
    if not have_cols:
        return pd.DataFrame()
    df = df.dropna(subset=have_cols, how="all")
    if df.empty:
        return pd.DataFrame()

    # Metric → imperial. NCEI Access with units=metric returns:
    #   TMAX/TMIN in °C, PRCP in mm.
    if "TMAX" in df.columns:
        df["tmax_f"] = df["TMAX"].astype(float) * 9.0 / 5.0 + 32.0
    else:
        df["tmax_f"] = float("nan")
    if "TMIN" in df.columns:
        df["tmin_f"] = df["TMIN"].astype(float) * 9.0 / 5.0 + 32.0
    else:
        df["tmin_f"] = float("nan")
    if "PRCP" in df.columns:
        df["prcp_in"] = df["PRCP"].astype(float) / 25.4
    else:
        df["prcp_in"] = float("nan")

    return df[["date", "tmax_f", "tmin_f", "prcp_in", "station_id"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Extend GHCN parquet to current date")
    parser.add_argument("--start", type=lambda s: date.fromisoformat(s),
                        default=date(date.today().year, 1, 1),
                        help="Start date (YYYY-MM-DD), default Jan 1 of current year")
    parser.add_argument("--end", type=lambda s: date.fromisoformat(s),
                        default=date.today(),
                        help="End date (YYYY-MM-DD), default today")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Stations per API call")
    parser.add_argument("--throttle", type=float, default=0.3,
                        help="Seconds between API calls")
    parser.add_argument("--existing", type=Path, default=EXISTING_PARQUET,
                        help="Existing parquet to append to (kept untouched)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output parquet path (default: county_weather_2000_<end_year>.parquet)")
    args = parser.parse_args()

    if args.output is None:
        args.output = GHCN_DIR / f"county_weather_2000_{args.end.year}.parquet"

    logger.info("Fetching GHCN extension for %s..%s", args.start, args.end)

    station_map = pd.read_csv(STATION_MAP_PATH, dtype={"fips": str, "station_id": str})
    station_map["fips"] = station_map["fips"].str.zfill(5)
    station_map = station_map.dropna(subset=["station_id"])
    station_map = station_map[station_map["station_id"].astype(str).str.strip() != ""]
    stations = (
        station_map["station_id"].astype(str).str.strip().drop_duplicates().tolist()
    )
    logger.info("Station universe: %d unique IDs across %d counties",
                len(stations), station_map["fips"].nunique())

    session = requests.Session()
    new_rows: list[pd.DataFrame] = []
    t0 = _time.time()
    n_batches = (len(stations) + args.batch_size - 1) // args.batch_size
    for i in range(n_batches):
        batch = stations[i * args.batch_size : (i + 1) * args.batch_size]
        try:
            csv_text = fetch_batch(batch, args.start, args.end, session)
        except requests.RequestException as exc:
            logger.warning("  batch %d/%d failed: %s", i + 1, n_batches, exc)
            continue
        df = parse_batch(csv_text)
        if not df.empty:
            new_rows.append(df)
        if (i + 1) % 10 == 0 or i + 1 == n_batches:
            cum = sum(len(d) for d in new_rows)
            logger.info("  batch %d/%d -> %d rows so far (%.1fs elapsed)",
                        i + 1, n_batches, cum, _time.time() - t0)
        if args.throttle > 0:
            _time.sleep(args.throttle)

    if not new_rows:
        logger.error("No rows fetched — aborting (output not written).")
        return

    new_df = pd.concat(new_rows, ignore_index=True)
    logger.info("Fetched %d raw rows for %d stations", len(new_df), new_df["station_id"].nunique())

    # Join to FIPS via station map. A few stations map to multiple counties
    # only on first-build edge cases; keep nearest mapping by distance_km.
    smap_best = (
        station_map.sort_values(["station_id", "distance_km"])
        .drop_duplicates(subset=["station_id"], keep="first")
        [["station_id", "fips"]]
    )
    new_df = new_df.merge(smap_best, on="station_id", how="inner")
    if new_df.empty:
        logger.error("After station_county_map join: 0 rows. Aborting.")
        return
    new_df = new_df[["fips", "date", "tmax_f", "tmin_f", "prcp_in", "station_id"]]
    logger.info("After FIPS join: %d rows, %d counties", len(new_df), new_df["fips"].nunique())

    # Append to existing.
    if args.existing.exists():
        existing = pd.read_parquet(args.existing)
        existing["date"] = pd.to_datetime(existing["date"], errors="coerce")
        # Drop any overlap with the new range so re-runs are idempotent.
        existing = existing[
            (existing["date"] < pd.Timestamp(args.start))
            | (existing["date"] > pd.Timestamp(args.end))
        ]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined = combined.drop_duplicates(subset=["fips", "date", "station_id"], keep="last")
    combined = combined.sort_values(["fips", "date"]).reset_index(drop=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(args.output, index=False)
    logger.info(
        "Wrote %d rows (%d counties, %s..%s) to %s in %.1fs",
        len(combined),
        combined["fips"].nunique(),
        combined["date"].min().strftime("%Y-%m-%d"),
        combined["date"].max().strftime("%Y-%m-%d"),
        args.output,
        _time.time() - t0,
    )


if __name__ == "__main__":
    main()
