"""Backfill NOAA Storm Events flood records into a parquet cache.

Filters NOAA Storm Events Details CSVs (one per year) down to flood-causing
event types ("Flood", "Flash Flood", "Heavy Rain", "Tropical Storm",
"Hurricane (Typhoon)"), county-scoped rows only (CZ_TYPE='C'), and writes
a flat parquet that ``train_yield.attach_flood_features`` reads.

The yield-model fix v1 deferred the flood feature, leaving NC corn 2024
(Tropical Storm Debby flooding + Hurricane Helene) as the dominant
outlier class. Combined with the HURDAT2 hurricane proximity feature,
this should give the model a real signal for hurricane-corridor
catastrophes.

Output columns at ``backend/etl/data/storm_floods.parquet``:
  fips                — 5-digit (state_fips + cz_fips), zero-padded
  event_date          — Python date of event start
  event_type          — original NOAA event-type label
  damage_property_usd — float USD (parsed from "1.50K"/"10.00M"/"55.00B")
  flood_cause         — text classifier (e.g. "Heavy Rain", "Tropical System"); may be empty

Storm Events files run from 1950 onward; we backfill 2000+ which is the
yield-model panel coverage.

Usage:
  python -m backend.etl.backfill_storm_events
  python -m backend.etl.backfill_storm_events --year-start 2018 --year-end 2025
"""

import argparse
import csv
import gzip
import io
import re
import time as _time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

from backend.etl.common import setup_logging

logger = setup_logging("backfill_storm_events")

LISTING_URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
DEFAULT_OUTPUT = Path(__file__).parent / "data" / "storm_floods.parquet"

FLOOD_EVENT_TYPES = {
    "Flood",
    "Flash Flood",
    "Heavy Rain",
    "Tropical Storm",
    "Hurricane (Typhoon)",
    "Hurricane",
    "Storm Surge/Tide",
    "Coastal Flood",
}

DAMAGE_RE = re.compile(r"^\s*([\d\.]+)\s*([KMBmkb]?)\s*$")
MULTIPLIERS = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}


def _parse_damage(s: str) -> float:
    """NOAA uses K/M/B suffixes for thousands/millions/billions."""
    if not s or str(s).strip() in ("", "0", "0.00"):
        return 0.0
    m = DAMAGE_RE.match(str(s))
    if not m:
        return 0.0
    val, suf = m.groups()
    return float(val) * MULTIPLIERS.get(suf.upper(), 1.0)


def _parse_event_date(yearmonth: str, day: str) -> date | None:
    """Build a date from BEGIN_YEARMONTH (YYYYMM) + BEGIN_DAY."""
    try:
        ym = int(yearmonth)
        d = int(day)
        return date(ym // 100, ym % 100, d)
    except (ValueError, TypeError):
        return None


def list_year_files(session: requests.Session) -> dict[int, str]:
    """Return ``{year: filename}`` map of latest-revision details files."""
    resp = session.get(LISTING_URL, timeout=120)
    resp.raise_for_status()
    pat = re.compile(r"StormEvents_details-ftp_v1\.0_d(\d{4})_c(\d{8})\.csv\.gz")
    latest: dict[int, tuple[int, str]] = {}
    for match in pat.finditer(resp.text):
        year = int(match.group(1))
        revision = int(match.group(2))
        fname = match.group(0)
        if year not in latest or revision > latest[year][0]:
            latest[year] = (revision, fname)
    return {y: f for y, (_rev, f) in latest.items()}


def fetch_year(session: requests.Session, fname: str) -> list[dict]:
    """Download + filter one year's Details CSV."""
    url = LISTING_URL + fname
    resp = session.get(url, timeout=300, stream=True)
    resp.raise_for_status()
    raw_bytes = resp.content
    text = gzip.decompress(raw_bytes).decode("utf-8", errors="replace")

    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        if r.get("CZ_TYPE", "").strip() != "C":
            continue  # county-scoped rows only
        event_type = r.get("EVENT_TYPE", "").strip()
        if event_type not in FLOOD_EVENT_TYPES:
            continue
        state_fips = (r.get("STATE_FIPS", "") or "").strip()
        cz_fips = (r.get("CZ_FIPS", "") or "").strip()
        if not state_fips or not cz_fips:
            continue
        try:
            full_fips = f"{int(state_fips):02d}{int(cz_fips):03d}"
        except ValueError:
            continue
        event_date = _parse_event_date(r.get("BEGIN_YEARMONTH", ""), r.get("BEGIN_DAY", ""))
        if event_date is None:
            continue
        damage_usd = _parse_damage(r.get("DAMAGE_PROPERTY", ""))
        rows.append({
            "fips": full_fips,
            "event_date": pd.Timestamp(event_date),
            "event_type": event_type,
            "damage_property_usd": damage_usd,
            "flood_cause": (r.get("FLOOD_CAUSE", "") or "").strip(),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill NOAA Storm Events flood records")
    parser.add_argument("--year-start", type=int, default=2000)
    parser.add_argument("--year-end", type=int, default=date.today().year)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    t0 = _time.time()
    session = requests.Session()
    file_map = list_year_files(session)
    target_years = [y for y in range(args.year_start, args.year_end + 1) if y in file_map]
    logger.info(
        "Fetching Storm Events for %d years (%d..%d) -> %s",
        len(target_years), target_years[0] if target_years else 0,
        target_years[-1] if target_years else 0,
        args.output,
    )

    all_rows: list[dict] = []
    for i, year in enumerate(target_years):
        rows = fetch_year(session, file_map[year])
        all_rows.extend(rows)
        logger.info(
            "  [%d/%d] %d: %d flood-event rows (cumulative %d)",
            i + 1, len(target_years), year, len(rows), len(all_rows),
        )

    if not all_rows:
        logger.error("No rows fetched. Aborting.")
        return

    df = pd.DataFrame(all_rows).drop_duplicates(
        subset=["fips", "event_date", "event_type"], keep="last",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.output.exists():
        try:
            old = pd.read_parquet(args.output)
            combined = pd.concat([old, df], ignore_index=True)
            df = combined.drop_duplicates(
                subset=["fips", "event_date", "event_type"], keep="last",
            )
        except Exception as exc:
            logger.warning("Could not merge with existing parquet (%s); overwriting", exc)

    df.to_parquet(args.output, index=False)
    logger.info(
        "Wrote %d rows (%d counties, %d distinct dates) to %s in %.1fs",
        len(df), df["fips"].nunique(), df["event_date"].nunique(),
        args.output, _time.time() - t0,
    )


if __name__ == "__main__":
    main()
