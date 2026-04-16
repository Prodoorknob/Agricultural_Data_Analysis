"""Ingest USDA Prospective Plantings (March 31 release) into acreage_accuracy.

Populates the `usda_prospective` column on the acreage_accuracy table, which
lets the Forecasts tab (§5.3.B/D in frontend-spec-v1.md) compare our model
output against the official USDA benchmark.

Data scope:
    3 commodities (CORN, SOYBEANS, WHEAT) x 50 states x ~25 years
    ≈ 450 state rows + 75 national rows = ~525 total.

Two modes:

1. --api   Query the NASS QuickStats API. Uses QUICKSTATS_API_KEY from .env.
           Walks (year, commodity) and pulls Prospective Plantings values.

2. --csv PATH   Load from a local CSV with columns:
                forecast_year, state_fips, commodity, prospective_acres
           Fallback when the API path fails or for one-off backfills.

After upserting usda_prospective, the script also computes model_vs_usda_pct
for any row that already has a model_forecast.

Usage:
    python -m backend.etl.ingest_prospective_plantings --api --year-start 2000
    python -m backend.etl.ingest_prospective_plantings --csv ./prospective_plantings.csv
    python -m backend.etl.ingest_prospective_plantings --api --year 2026
"""

import argparse
import csv
import sys
import time as _time
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_env, get_sync_session, setup_logging, log_ingest_summary
from backend.models.db_tables import AcreageAccuracy

logger = setup_logging("ingest_prospective_plantings")

NASS_API = "https://quickstats.nass.usda.gov/api/api_GET"
MAX_RECORDS = 50000
REQUEST_DELAY = 1.0

# Commodity → (NASS commodity_desc, our canonical name(s))
# Wheat is queried once and split into wheat_winter / wheat_spring by class_desc.
COMMODITY_QUERIES = {
    "corn":    {"commodity_desc": "CORN",     "class_filter": None},
    "soybean": {"commodity_desc": "SOYBEANS", "class_filter": None},
    "wheat":   {"commodity_desc": "WHEAT",    "class_filter": None},  # split later
}

# NASS class_desc → our canonical name
WHEAT_CLASS_MAP = {
    "WINTER": "wheat_winter",
    "SPRING, (EXCL DURUM)": "wheat_spring",
    "ALL CLASSES": "wheat",  # used when winter/spring not separated
}

# State alpha → FIPS (matches backend/models/train_acreage.py)
STATE_ALPHA_TO_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
    "US": "00",  # national rollup
}


def _nass_commodity_to_ours(row: dict) -> str | None:
    """Map a NASS row to our canonical commodity name."""
    cd = row.get("commodity_desc", "").upper()
    cls = row.get("class_desc", "").upper()
    if cd == "CORN":
        return "corn"
    if cd == "SOYBEANS":
        return "soybean"
    if cd == "WHEAT":
        for nass_class, our_name in WHEAT_CLASS_MAP.items():
            if cls == nass_class:
                return our_name
    return None


def _parse_value(val) -> float | None:
    """Parse NASS Value field, handling commas and null markers."""
    if val is None:
        return None
    s = str(val).strip()
    if s in ("", "(D)", "(Z)", "(NA)", "(S)"):
        return None
    try:
        return float(s.replace(",", ""))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# API mode
# ---------------------------------------------------------------------------

PROSPECTIVE_PERIOD = "YEAR - MAR ACREAGE"   # March release = Prospective Plantings
JUNE_ACTUAL_PERIOD = "YEAR - JUN ACREAGE"   # June release = actual acreage survey


def fetch_from_nass_api(year_start: int, year_end: int) -> tuple[list[dict], list[dict]]:
    """Fetch Prospective Plantings (March) AND June Acreage (actual) from NASS.

    NASS distinguishes the releases via `reference_period_desc`:
      - "YEAR - MAR ACREAGE" → Prospective Plantings (March 31 release)
      - "YEAR - JUN ACREAGE" → Acreage report (June 30 release — actual planted)

    Both come from the same query; we split by reference_period_desc.

    Returns (prospective_rows, june_actual_rows).
    """
    api_key = get_env("QUICKSTATS_API_KEY")
    if not api_key:
        logger.error("QUICKSTATS_API_KEY not set in .env — cannot use --api mode")
        return [], []

    prospective_rows: list[dict] = []
    june_rows: list[dict] = []

    for our_name, q in COMMODITY_QUERIES.items():
        commodity = q["commodity_desc"]
        logger.info("Fetching Prospective + June Acreage: %s (%d-%d)", commodity, year_start, year_end)

        for year in range(year_start, year_end + 1):
            # Single query pulls all releases for the year — filter locally
            for agg_level in ("STATE", "NATIONAL"):
                params = {
                    "key": api_key,
                    "source_desc": "SURVEY",
                    "commodity_desc": commodity,
                    "statisticcat_desc": "AREA PLANTED",
                    "unit_desc": "ACRES",
                    "agg_level_desc": agg_level,
                    "year": year,
                    "format": "JSON",
                }
                rows = _query_nass(params)

                p_rows = [r for r in rows if r.get("reference_period_desc") == PROSPECTIVE_PERIOD]
                j_rows = [r for r in rows if r.get("reference_period_desc") == JUNE_ACTUAL_PERIOD]

                prospective_rows.extend(p_rows)
                june_rows.extend(j_rows)

                _time.sleep(REQUEST_DELAY)

            logger.info(
                "  %s %d: prospective=%d june_actual=%d",
                commodity, year,
                sum(1 for r in prospective_rows if int(r.get("year", 0)) == year and r.get("commodity_desc") == commodity),
                sum(1 for r in june_rows if int(r.get("year", 0)) == year and r.get("commodity_desc") == commodity),
            )

    logger.info("Total: prospective=%d, june_actual=%d", len(prospective_rows), len(june_rows))
    return prospective_rows, june_rows


def _query_nass(params: dict) -> list[dict]:
    """Execute a single NASS API query. Returns list of row dicts."""
    try:
        resp = requests.get(NASS_API, params=params, timeout=60)
        if resp.status_code == 400:
            # 400 usually means zero rows matched (NASS returns 400, not empty)
            return []
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except requests.RequestException as exc:
        logger.warning("  NASS API call failed: %s", exc)
        return []


def transform_nass_rows(rows: list[dict], column: str) -> list[dict]:
    """Convert raw NASS rows to acreage_accuracy upsert format.

    Args:
        rows: raw rows from NASS API
        column: which column to populate — 'usda_prospective' or 'usda_june_actual'
    """
    out = []
    for r in rows:
        our_commodity = _nass_commodity_to_ours(r)
        if not our_commodity:
            continue
        value = _parse_value(r.get("Value"))
        if value is None:
            continue
        state_alpha = r.get("state_alpha", "US")
        state_fips = STATE_ALPHA_TO_FIPS.get(state_alpha)
        if state_fips is None:
            continue
        try:
            year = int(r.get("year"))
        except (TypeError, ValueError):
            continue

        out.append({
            "forecast_year": year,
            "state_fips": state_fips,
            "commodity": our_commodity,
            column: value,
        })
    return out


# ---------------------------------------------------------------------------
# CSV fallback mode
# ---------------------------------------------------------------------------

def load_from_csv(csv_path: Path) -> list[dict]:
    """Load Prospective Plantings from a local CSV.

    Expected columns:
        forecast_year, state_fips, commodity, prospective_acres
    """
    if not csv_path.exists():
        logger.error("CSV not found: %s", csv_path)
        return []

    out = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                out.append({
                    "forecast_year": int(row["forecast_year"]),
                    "state_fips": str(row["state_fips"]).zfill(2),
                    "commodity": row["commodity"].strip().lower(),
                    "usda_prospective": float(row["prospective_acres"]),
                })
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed row: %s (%s)", row, exc)
    logger.info("Loaded %d rows from %s", len(out), csv_path)
    return out


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_column(rows: list[dict], column: str) -> int:
    """Upsert a single column (usda_prospective or usda_june_actual) into acreage_accuracy.

    After upserting, recomputes model_vs_usda_pct for rows where both
    model_forecast and usda_prospective are present. Returns number of rows upserted.
    """
    if not rows:
        return 0
    if column not in ("usda_prospective", "usda_june_actual"):
        raise ValueError(f"Unsupported column: {column}")

    session = get_sync_session()
    try:
        stmt = insert(AcreageAccuracy.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_acreage_accuracy",
            set_={
                column: getattr(stmt.excluded, column),
                "updated_at": datetime.utcnow(),
            },
        )
        result = session.execute(stmt)
        session.commit()
        upserted = result.rowcount

        # Recompute model_vs_usda_pct whenever both are present
        updated = session.execute(
            update(AcreageAccuracy)
            .where(
                AcreageAccuracy.model_forecast.is_not(None),
                AcreageAccuracy.usda_prospective.is_not(None),
            )
            .values(
                model_vs_usda_pct=(
                    (AcreageAccuracy.model_forecast - AcreageAccuracy.usda_prospective)
                    / AcreageAccuracy.usda_prospective * 100
                )
            )
        )
        session.commit()
        logger.info(
            "[%s] upserted %d rows; recomputed model_vs_usda_pct on %d rows",
            column, upserted, updated.rowcount,
        )
        return upserted
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingest USDA Prospective Plantings")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--api", action="store_true", help="Fetch from NASS QuickStats API")
    mode.add_argument("--csv", type=Path, help="Load from local CSV file")

    parser.add_argument("--year-start", type=int, default=2000,
                        help="First year to fetch (default: 2000)")
    parser.add_argument("--year-end", type=int, default=None,
                        help="Last year to fetch (default: current year)")
    parser.add_argument("--year", type=int, default=None,
                        help="Single year shortcut (overrides year-start/year-end)")
    args = parser.parse_args()

    start_time = datetime.utcnow()

    if args.api:
        year_end = args.year_end or datetime.utcnow().year
        year_start = args.year_start
        if args.year:
            year_start = year_end = args.year

        prospective_raw, june_raw = fetch_from_nass_api(year_start, year_end)
        prospective_rows = transform_nass_rows(prospective_raw, "usda_prospective")
        june_rows = transform_nass_rows(june_raw, "usda_june_actual")
    else:
        prospective_rows = load_from_csv(args.csv)
        june_rows = []

    if not prospective_rows and not june_rows:
        logger.warning(
            "No rows to upsert. If using --api, try a wider --year-start "
            "or --csv mode with a manually downloaded file."
        )
        sys.exit(1)

    total = 0
    if prospective_rows:
        total += upsert_column(prospective_rows, "usda_prospective")
    if june_rows:
        total += upsert_column(june_rows, "usda_june_actual")

    log_ingest_summary(logger, "acreage_accuracy (prospective + june actual)", total, start_time)


if __name__ == "__main__":
    main()
