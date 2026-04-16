"""Ingest USDA FAS weekly export sales data for acreage features.

Downloads commodity-level export commitments from the FAS Export Sales
Reporting and Query System (ESRQS) OpenData API, extracts the November 1
snapshot for each marketing year, and upserts to export_commitments.

API: https://apps.fas.usda.gov/OpenData/api/esr/
No authentication required. Returns JSON.

Marketing years: corn/soy = Sep 1 - Aug 31, wheat = Jun 1 - May 31.

Usage:
    python -m backend.etl.ingest_fas_exports --backfill
    python -m backend.etl.ingest_fas_exports --year 2025
"""

import argparse
import time as _time
from datetime import date, datetime

import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary
from backend.models.db_tables import ExportCommitment

logger = setup_logging("ingest_fas_exports")

FAS_API_BASE = "https://apps.fas.usda.gov/OpenData/api/esr"

# FAS commodity codes for our target crops
COMMODITY_CODES = {
    "corn": "104",
    "soybean": "801",
    "wheat": "107",  # All wheat
}

# Marketing year start months
MY_START = {"corn": 9, "soybean": 9, "wheat": 6}

API_DELAY = 1.0  # seconds between API calls


def _my_string(commodity: str, year: int) -> str:
    """Build marketing year string like '2024/2025' given the start year."""
    return f"{year}/{year + 1}"


def fetch_export_data(commodity: str, market_year: int) -> list[dict] | None:
    """Fetch weekly export data for a commodity/marketing year from FAS API.

    Returns list of dicts with keys: weekEndingDate, outstandingSales,
    grossSales, netSales, accumulatedExports, etc.
    """
    code = COMMODITY_CODES.get(commodity)
    if not code:
        return None

    url = f"{FAS_API_BASE}/exports/commodityCode/{code}/allCountries/marketYear/{market_year}"
    logger.info("Fetching %s MY %d ...", commodity, market_year)

    try:
        resp = requests.get(url, timeout=60, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("FAS API failed for %s MY %d: %s", commodity, market_year, exc)
        return None

    if not data:
        logger.warning("No export data for %s MY %d", commodity, market_year)
        return None

    return data


def aggregate_weekly_to_snapshot(
    weekly_data: list[dict], commodity: str, market_year: int
) -> list[dict]:
    """Aggregate country-level weekly data to total commodity-level snapshots.

    Groups by week ending date, sums across all destination countries.
    Returns a row per week with total outstanding, accumulated exports, net sales.
    """
    # Group by week ending date
    by_week: dict[str, dict] = {}
    for entry in weekly_data:
        week_date = entry.get("weekEndingDate", "")
        if not week_date:
            continue
        # Parse date (ISO format)
        try:
            dt_str = week_date.split("T")[0]
            dt = datetime.strptime(dt_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        key = str(dt)
        if key not in by_week:
            by_week[key] = {
                "as_of_date": dt,
                "outstanding_sales_mt": 0.0,
                "accumulated_exports_mt": 0.0,
                "net_sales_mt": 0.0,
            }

        # Sum across countries (values are in metric tons)
        outstanding = entry.get("outstandingSales", 0) or 0
        accum = entry.get("accumulatedExports", 0) or 0
        net = entry.get("netSales", 0) or 0

        by_week[key]["outstanding_sales_mt"] += float(outstanding)
        by_week[key]["accumulated_exports_mt"] += float(accum)
        by_week[key]["net_sales_mt"] += float(net)

    my_str = _my_string(commodity, market_year)
    rows = []
    for _, snap in sorted(by_week.items()):
        rows.append({
            "commodity": commodity,
            "marketing_year": my_str,
            "as_of_date": snap["as_of_date"],
            "outstanding_sales_mt": round(snap["outstanding_sales_mt"], 1),
            "accumulated_exports_mt": round(snap["accumulated_exports_mt"], 1),
            "net_sales_mt": round(snap["net_sales_mt"], 1),
        })

    return rows


def upsert_rows(rows: list[dict]) -> int:
    """Upsert export commitment rows to the database."""
    if not rows:
        return 0

    session = get_sync_session()
    try:
        stmt = insert(ExportCommitment.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_export_commits",
            set_={
                "outstanding_sales_mt": stmt.excluded.outstanding_sales_mt,
                "accumulated_exports_mt": stmt.excluded.accumulated_exports_mt,
                "net_sales_mt": stmt.excluded.net_sales_mt,
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


def run_backfill(year_start: int = 2005, year_end: int = 2025):
    """Backfill export commitments for all commodities and marketing years."""
    start = datetime.utcnow()
    total = 0

    for commodity in COMMODITY_CODES:
        for my_start in range(year_start, year_end + 1):
            data = fetch_export_data(commodity, my_start)
            if not data:
                _time.sleep(API_DELAY)
                continue

            rows = aggregate_weekly_to_snapshot(data, commodity, my_start)
            n = upsert_rows(rows)
            logger.info("%s MY %d/%d: upserted %d weekly snapshots",
                        commodity, my_start, my_start + 1, n)
            total += n
            _time.sleep(API_DELAY)

    log_ingest_summary(logger, "export_commitments", total, start)
    return total


def run_refresh(year: int | None = None):
    """Refresh current marketing year only."""
    year = year or datetime.utcnow().year
    start = datetime.utcnow()
    total = 0

    for commodity in COMMODITY_CODES:
        # Current marketing year: based on current month vs MY start
        my_start_month = MY_START[commodity]
        today = date.today()
        if today.month >= my_start_month:
            current_my = today.year
        else:
            current_my = today.year - 1

        data = fetch_export_data(commodity, current_my)
        if data:
            rows = aggregate_weekly_to_snapshot(data, commodity, current_my)
            n = upsert_rows(rows)
            logger.info("%s MY %d: upserted %d snapshots", commodity, current_my, n)
            total += n
        _time.sleep(API_DELAY)

    log_ingest_summary(logger, "export_commitments", total, start)
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest FAS weekly export sales data")
    parser.add_argument("--backfill", action="store_true", help="Backfill 2005-2025")
    parser.add_argument("--year", type=int, default=None, help="Refresh a specific marketing year")
    parser.add_argument("--year-start", type=int, default=2005, help="Backfill start year")
    parser.add_argument("--year-end", type=int, default=2025, help="Backfill end year")
    args = parser.parse_args()

    if args.backfill:
        run_backfill(args.year_start, args.year_end)
    else:
        run_refresh(args.year)
