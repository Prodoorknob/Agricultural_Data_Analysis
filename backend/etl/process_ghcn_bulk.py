"""Process GHCN daily bulk archive into county-level weather data.

Reads the NOAA daily-summaries-latest.tar.gz bulk file, extracts only the
stations mapped to counties (from station_county_map.csv), and produces
a consolidated CSV with TMAX/TMIN/PRCP per county per day.

The bulk archive contains ~75K station CSVs. We only need ~3,140 stations
(one per county). This is MUCH faster than the API for historical backfill.

GHCN units: PRCP in tenths of mm, TMAX/TMIN in tenths of degrees Celsius.
We convert to: PRCP in inches, TMAX/TMIN in Fahrenheit (for GDD computation).

Usage:
    python -m backend.etl.process_ghcn_bulk --archive data/daily-summaries-latest.tar.gz
    python -m backend.etl.process_ghcn_bulk --archive data/daily-summaries-latest.tar.gz --year-start 2000 --year-end 2025
"""

import argparse
import csv
import io
import os
import tarfile
import time as _time
from datetime import date
from pathlib import Path

import pandas as pd

from backend.etl.common import setup_logging

logger = setup_logging("process_ghcn_bulk")

OUTPUT_DIR = Path(__file__).parent / "data" / "ghcn_processed"


def load_needed_stations() -> dict[str, list[str]]:
    """Load station -> county FIPS mapping. Returns {station_id: [fips1, fips2, ...]}."""
    station_map_path = Path(__file__).parent / "data" / "station_county_map.csv"
    if not station_map_path.exists():
        raise FileNotFoundError(f"Station map not found at {station_map_path}. Run build_station_map.py first.")

    station_to_fips: dict[str, list[str]] = {}
    with open(station_map_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row["station_id"]
            if sid:  # Skip NASA POWER fallback rows (empty station_id)
                station_to_fips.setdefault(sid, []).append(row["fips"])

    logger.info("Need data from %d unique stations covering %d counties",
                len(station_to_fips), sum(len(v) for v in station_to_fips.values()))
    return station_to_fips


def process_station_csv(
    csv_content: str,
    station_id: str,
    fips_list: list[str],
    year_start: int,
    year_end: int,
) -> list[dict]:
    """Parse a single GHCN station CSV file and map to county FIPS.

    GHCN CSV columns: STATION, DATE, LATITUDE, LONGITUDE, ELEVATION, NAME,
                      PRCP, PRCP_ATTRIBUTES, SNOW, ..., TMAX, TMAX_ATTRIBUTES,
                      TMIN, TMIN_ATTRIBUTES, ...

    Units: PRCP = tenths of mm, TMAX/TMIN = tenths of degrees C.
    We convert to: PRCP = inches, TMAX/TMIN = degrees Fahrenheit.
    """
    rows = []

    reader = csv.DictReader(io.StringIO(csv_content))
    for rec in reader:
        obs_date = rec.get("DATE", "")
        if not obs_date:
            continue

        # Filter by year range
        try:
            year = int(obs_date[:4])
        except ValueError:
            continue
        if year < year_start or year > year_end:
            continue

        # Parse weather values
        tmax_raw = rec.get("TMAX", "").strip()
        tmin_raw = rec.get("TMIN", "").strip()
        prcp_raw = rec.get("PRCP", "").strip()

        # Convert from tenths of C to Fahrenheit
        tmax_f = None
        tmin_f = None
        if tmax_raw:
            try:
                tmax_c = float(tmax_raw) / 10.0
                tmax_f = round(tmax_c * 9 / 5 + 32, 1)
            except ValueError:
                pass
        if tmin_raw:
            try:
                tmin_c = float(tmin_raw) / 10.0
                tmin_f = round(tmin_c * 9 / 5 + 32, 1)
            except ValueError:
                pass

        # Convert from tenths of mm to inches
        prcp_in = None
        if prcp_raw:
            try:
                prcp_mm = float(prcp_raw) / 10.0
                prcp_in = round(prcp_mm / 25.4, 3)
            except ValueError:
                pass

        # Map to all counties using this station
        for fips in fips_list:
            rows.append({
                "fips": fips,
                "date": obs_date,
                "tmax_f": tmax_f,
                "tmin_f": tmin_f,
                "prcp_in": prcp_in,
                "station_id": station_id,
            })

    return rows


def process_archive(
    archive_path: str,
    year_start: int = 2000,
    year_end: int = 2025,
):
    """Extract and process GHCN daily bulk archive."""
    station_to_fips = load_needed_stations()
    needed_filenames = {f"{sid}.csv" for sid in station_to_fips}

    logger.info("Opening archive %s (%.1f GB)...", archive_path, os.path.getsize(archive_path) / 1e9)
    logger.info("Looking for %d station files, years %d-%d", len(needed_filenames), year_start, year_end)

    all_rows = []
    stations_found = 0
    stations_skipped = 0

    t0 = _time.time()

    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue

            filename = os.path.basename(member.name)

            if filename not in needed_filenames:
                stations_skipped += 1
                continue

            # Extract station ID from filename (e.g., "USW00014837.csv" -> "USW00014837")
            station_id = filename.replace(".csv", "")
            fips_list = station_to_fips.get(station_id, [])

            if not fips_list:
                continue

            # Read CSV content
            try:
                f = tar.extractfile(member)
                if f is None:
                    continue
                csv_content = f.read().decode("utf-8", errors="replace")
                f.close()
            except Exception as exc:
                logger.warning("Failed to read %s: %s", filename, exc)
                continue

            rows = process_station_csv(csv_content, station_id, fips_list, year_start, year_end)
            all_rows.extend(rows)
            stations_found += 1

            if stations_found % 100 == 0:
                elapsed = _time.time() - t0
                logger.info(
                    "Processed %d/%d stations (%d rows, %.1f min elapsed, %d skipped)",
                    stations_found, len(needed_filenames), len(all_rows), elapsed / 60, stations_skipped,
                )

    elapsed = _time.time() - t0
    logger.info(
        "Archive processing complete: %d stations, %d rows in %.1f minutes",
        stations_found, len(all_rows), elapsed / 60,
    )

    return all_rows


def save_output(rows: list[dict], year_start: int, year_end: int):
    """Save processed weather data to CSV and parquet."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not rows:
        logger.warning("No rows to save!")
        return

    df = pd.DataFrame(rows)
    logger.info("DataFrame: %d rows x %d cols", len(df), len(df.columns))

    # Save as parquet (much smaller, faster to read)
    pq_path = OUTPUT_DIR / f"county_weather_{year_start}_{year_end}.parquet"
    df.to_parquet(pq_path, index=False, engine="pyarrow", compression="snappy")
    logger.info("Saved parquet: %s (%.1f MB)", pq_path, pq_path.stat().st_size / 1e6)

    # Also save a small sample CSV for inspection
    sample_path = OUTPUT_DIR / f"county_weather_sample.csv"
    df.head(1000).to_csv(sample_path, index=False)
    logger.info("Saved sample CSV: %s", sample_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process GHCN daily bulk archive")
    parser.add_argument("--archive", required=True, help="Path to daily-summaries-latest.tar.gz")
    parser.add_argument("--year-start", type=int, default=2000, help="Start year (default: 2000)")
    parser.add_argument("--year-end", type=int, default=2025, help="End year (default: 2025)")
    args = parser.parse_args()

    t0 = _time.time()
    rows = process_archive(args.archive, args.year_start, args.year_end)
    save_output(rows, args.year_start, args.year_end)
    logger.info("Total time: %.1f minutes", (_time.time() - t0) / 60)
