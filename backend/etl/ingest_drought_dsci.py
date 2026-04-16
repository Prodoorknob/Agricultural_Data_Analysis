"""Ingest state-level Drought Severity and Coverage Index (DSCI) from USDM.

Computes annual drought features for the acreage prediction module:
  - dsci_nov: DSCI on/nearest November 1
  - dsci_fall_avg: mean DSCI over September-November
  - dsci_winter_avg: mean DSCI over December-February (for wheat)
  - drought_weeks_d2plus: weeks with DSCI > 200 in calendar year

API: https://usdmdataservices.unl.edu/api/StateStatistics/GetDSCI
No authentication required. Weekly DSCI per state (0-500 scale).

Usage:
    python -m backend.etl.ingest_drought_dsci --backfill
    python -m backend.etl.ingest_drought_dsci --year 2025
"""

import argparse
import time as _time
from datetime import datetime

import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary
from backend.models.db_tables import DroughtIndex

logger = setup_logging("ingest_drought_dsci")

DSCI_API = "https://usdmdataservices.unl.edu/api/StateStatistics/GetDSCI"

# 50 states by FIPS (same set as acreage_features.FIPS_TO_STATE minus "00")
STATE_FIPS = [
    "01", "04", "05", "06", "08", "09", "10", "12", "13", "16",
    "17", "18", "19", "20", "21", "22", "23", "24", "25", "26",
    "27", "28", "29", "30", "31", "32", "33", "34", "35", "36",
    "37", "38", "39", "40", "41", "42", "44", "45", "46", "47",
    "48", "49", "50", "51", "53", "54", "55", "56",
]

API_DELAY = 0.5  # seconds between calls to be polite


def fetch_dsci_year(state_fips: str, year: int) -> list[dict]:
    """Fetch weekly DSCI values for a state-year from the USDM API.

    Returns list of dicts with keys: date (str), dsci (float).
    """
    params = {
        "aoi": state_fips,
        "startdate": f"1/1/{year}",
        "enddate": f"12/31/{year}",
        "statisticsType": 1,  # 1 = state level
    }

    try:
        resp = requests.get(DSCI_API, params=params, timeout=60,
                            headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("API failed for fips=%s year=%d: %s", state_fips, year, exc)
        return []

    if not data:
        return []

    rows = []
    for entry in data:
        # API returns lowercase keys: 'dsci', 'mapDate', 'name'
        dsci_val = entry.get("dsci") or entry.get("DSCI")
        date_str = (entry.get("mapDate") or entry.get("MapDate")
                    or entry.get("releaseDate") or entry.get("ReleaseDate")
                    or entry.get("validStart") or entry.get("ValidStart"))
        if dsci_val is not None and date_str:
            try:
                # Parse date — API returns ISO format "YYYY-MM-DDTHH:MM:SS"
                dt_str = str(date_str).split("T")[0]
                if "/" in dt_str:
                    dt = datetime.strptime(dt_str, "%m/%d/%Y")
                elif "-" in dt_str:
                    dt = datetime.strptime(dt_str, "%Y-%m-%d")
                else:
                    dt = datetime.strptime(dt_str[:8], "%Y%m%d")
                rows.append({"date": dt, "dsci": float(dsci_val)})
            except (ValueError, TypeError):
                continue

    return rows


def aggregate_annual(weekly: list[dict], year: int) -> dict:
    """Compute annual drought features from weekly DSCI data.

    Features (all use data available by Nov 1 of the forecast year):
      dsci_nov: DSCI value nearest to November 1
      dsci_fall_avg: mean DSCI Sep-Nov
      dsci_winter_avg: mean DSCI Dec(year-1) - Feb(year) — for wheat
      drought_weeks_d2plus: count of weeks with DSCI > 200
    """
    if not weekly:
        return {}

    # Sort by date
    weekly = sorted(weekly, key=lambda r: r["date"])

    # November 1 value — find closest week on or before Nov 1
    nov1 = datetime(year, 11, 1)
    dsci_nov = None
    best_diff = float("inf")
    for w in weekly:
        diff = abs((w["date"] - nov1).days)
        if diff < best_diff:
            best_diff = diff
            dsci_nov = w["dsci"]

    # Fall average (Sep-Nov of this year)
    fall_vals = [w["dsci"] for w in weekly if 9 <= w["date"].month <= 11]
    dsci_fall_avg = round(sum(fall_vals) / len(fall_vals), 1) if fall_vals else None

    # Winter average (Dec of prior year through Feb of this year)
    winter_vals = [
        w["dsci"] for w in weekly
        if (w["date"].month <= 2 and w["date"].year == year)
    ]
    dsci_winter_avg = round(sum(winter_vals) / len(winter_vals), 1) if winter_vals else None

    # Weeks with severe drought (DSCI > 200 ≈ most of state in D2+)
    d2plus = sum(1 for w in weekly if w["dsci"] > 200)

    return {
        "dsci_nov": round(dsci_nov, 1) if dsci_nov is not None else None,
        "dsci_fall_avg": dsci_fall_avg,
        "dsci_winter_avg": dsci_winter_avg,
        "drought_weeks_d2plus": d2plus,
    }


def upsert_rows(rows: list[dict]) -> int:
    """Upsert aggregated drought index rows to the database."""
    if not rows:
        return 0

    session = get_sync_session()
    try:
        stmt = insert(DroughtIndex.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_drought_index",
            set_={
                "dsci_nov": stmt.excluded.dsci_nov,
                "dsci_fall_avg": stmt.excluded.dsci_fall_avg,
                "dsci_winter_avg": stmt.excluded.dsci_winter_avg,
                "drought_weeks_d2plus": stmt.excluded.drought_weeks_d2plus,
            },
        )
        result = session.execute(stmt)
        session.commit()
        return result.rowcount
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_backfill(year_start: int = 2000, year_end: int = 2025):
    """Backfill all states for a range of years."""
    start = datetime.utcnow()
    total_rows = []
    total_calls = len(STATE_FIPS) * (year_end - year_start + 1)
    call_num = 0

    for year in range(year_start, year_end + 1):
        year_rows = []
        for fips in STATE_FIPS:
            call_num += 1
            if call_num % 50 == 0:
                logger.info("Progress: %d / %d API calls", call_num, total_calls)

            weekly = fetch_dsci_year(fips, year)
            agg = aggregate_annual(weekly, year)
            if agg:
                agg["state_fips"] = fips
                agg["year"] = year
                year_rows.append(agg)
            _time.sleep(API_DELAY)

        # Upsert per-year batch
        if year_rows:
            n = upsert_rows(year_rows)
            logger.info("Year %d: upserted %d state rows", year, n)
            total_rows.extend(year_rows)

    log_ingest_summary(logger, "drought_index", len(total_rows), start)
    return len(total_rows)


def run_refresh(year: int | None = None):
    """Refresh current year only."""
    year = year or datetime.utcnow().year
    start = datetime.utcnow()
    rows = []
    for fips in STATE_FIPS:
        weekly = fetch_dsci_year(fips, year)
        agg = aggregate_annual(weekly, year)
        if agg:
            agg["state_fips"] = fips
            agg["year"] = year
            rows.append(agg)
        _time.sleep(API_DELAY)

    n = upsert_rows(rows)
    log_ingest_summary(logger, "drought_index", n, start)
    return n


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest state-level DSCI from USDM")
    parser.add_argument("--backfill", action="store_true", help="Backfill 2000-2025")
    parser.add_argument("--year", type=int, default=None, help="Refresh a specific year")
    parser.add_argument("--year-start", type=int, default=2000, help="Backfill start year")
    parser.add_argument("--year-end", type=int, default=2025, help="Backfill end year")
    args = parser.parse_args()

    if args.backfill:
        run_backfill(args.year_start, args.year_end)
    else:
        run_refresh(args.year)
