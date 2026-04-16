"""Ingest USDA FSA Conservation Reserve Program enrollment and expiration data.

Downloads state-level CRP enrollment history and contract expirations from FSA,
parses Excel files, and upserts to crp_enrollment table.

Sources:
  - CRP Enrollment and Rental Payments by State, 1986-2024:
    https://www.fsa.usda.gov/documents/crphistorystate
  - CRP Contract Expirations by State, 2020-2031+:
    https://www.fsa.usda.gov/sites/default/files/documents/EXPIRE STATE.xlsx

Usage:
    python -m backend.etl.ingest_crp --backfill
    python -m backend.etl.ingest_crp --year 2025
"""

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary
from backend.models.db_tables import CrpEnrollment

logger = setup_logging("ingest_crp")

CACHE_DIR = Path(__file__).parent / "data" / "crp_cache"
MANUAL_BACKFILL = Path(__file__).parent / "data" / "crp_manual_backfill.csv"

# FSA download URLs
ENROLLMENT_URL = "https://www.fsa.usda.gov/documents/crphistorystate"
EXPIRATION_URL = "https://www.fsa.usda.gov/sites/default/files/documents/EXPIRE%20STATE.xlsx"

# State name → FIPS mapping (reverse of acreage_features.FIPS_TO_STATE)
STATE_TO_FIPS = {
    "Alabama": "01", "Alaska": "02", "Arizona": "04", "Arkansas": "05",
    "California": "06", "Colorado": "08", "Connecticut": "09", "Delaware": "10",
    "Florida": "12", "Georgia": "13", "Hawaii": "15", "Idaho": "16",
    "Illinois": "17", "Indiana": "18", "Iowa": "19", "Kansas": "20",
    "Kentucky": "21", "Louisiana": "22", "Maine": "23", "Maryland": "24",
    "Massachusetts": "25", "Michigan": "26", "Minnesota": "27", "Mississippi": "28",
    "Missouri": "29", "Montana": "30", "Nebraska": "31", "Nevada": "32",
    "New Hampshire": "33", "New Jersey": "34", "New Mexico": "35", "New York": "36",
    "North Carolina": "37", "North Dakota": "38", "Ohio": "39", "Oklahoma": "40",
    "Oregon": "41", "Pennsylvania": "42", "Rhode Island": "44",
    "South Carolina": "45", "South Dakota": "46", "Tennessee": "47",
    "Texas": "48", "Utah": "49", "Vermont": "50", "Virginia": "51",
    "Washington": "53", "West Virginia": "54", "Wisconsin": "55", "Wyoming": "56",
}


def _download_file(url: str, filename: str) -> Path | None:
    """Download a file to the cache directory."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local = CACHE_DIR / filename
    if local.exists():
        logger.info("Using cached %s", local.name)
        return local

    logger.info("Downloading %s ...", url)
    try:
        resp = requests.get(url, timeout=120, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Download failed: %s", exc)
        return None

    with open(local, "wb") as f:
        f.write(resp.content)
    logger.info("Downloaded %s (%.1f KB)", local.name, len(resp.content) / 1024)
    return local


def _resolve_fips(state_name: str) -> str | None:
    """Convert state name to 2-char FIPS code."""
    name = state_name.strip().title()
    return STATE_TO_FIPS.get(name)


def parse_enrollment_history(filepath: Path) -> pd.DataFrame:
    """Parse the CRP enrollment history Excel (state x year matrix).

    Expected format: rows = states, columns = years, values = enrolled acres (1,000 acres).
    The Excel may have multiple sheets; try common patterns.
    """
    rows = []
    try:
        # Try reading all sheets and find the one with state names
        xls = pd.ExcelFile(filepath, engine="openpyxl")
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet, header=None)

            # Find the header row (look for year-like numbers in a row)
            header_row = None
            for i in range(min(10, len(df))):
                vals = df.iloc[i].dropna().astype(str).tolist()
                year_count = sum(1 for v in vals if v.isdigit() and 1986 <= int(v) <= 2030)
                if year_count >= 5:
                    header_row = i
                    break

            if header_row is None:
                continue

            # Set header and filter to state rows
            headers = df.iloc[header_row].tolist()
            df = df.iloc[header_row + 1:]
            df.columns = headers

            # Find the state name column (first non-year text column)
            state_col = None
            for col in headers:
                if isinstance(col, str) and not col.isdigit():
                    state_col = col
                    break
            if state_col is None:
                state_col = headers[0]

            # Extract year columns
            year_cols = [c for c in headers if isinstance(c, (int, float)) and 1986 <= c <= 2030]

            for _, row in df.iterrows():
                state_name = str(row.get(state_col, "")).strip()
                fips = _resolve_fips(state_name)
                if not fips:
                    continue

                for year_col in year_cols:
                    year = int(year_col)
                    val = row.get(year_col)
                    try:
                        enrolled_acres = float(val) * 1000  # Convert from 1,000 acres
                    except (ValueError, TypeError):
                        continue
                    if enrolled_acres > 0:
                        rows.append({
                            "state_fips": fips,
                            "year": year,
                            "enrolled_acres": round(enrolled_acres, 1),
                        })
            if rows:
                break  # Found data, stop checking sheets

    except Exception as exc:
        logger.error("Failed to parse enrollment history: %s", exc)

    logger.info("Parsed %d enrollment rows from %s", len(rows), filepath.name)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def parse_expiration_data(filepath: Path) -> pd.DataFrame:
    """Parse the CRP contract expirations by state Excel.

    Expected format: rows = states, columns = fiscal years of expiration.
    Values = acres expiring in that year.
    """
    rows = []
    try:
        xls = pd.ExcelFile(filepath, engine="openpyxl")
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet, header=None)

            # Find header row with year-like values
            header_row = None
            for i in range(min(10, len(df))):
                vals = df.iloc[i].dropna().astype(str).tolist()
                year_count = sum(1 for v in vals if v.isdigit() and 2020 <= int(v) <= 2040)
                if year_count >= 3:
                    header_row = i
                    break

            if header_row is None:
                continue

            headers = df.iloc[header_row].tolist()
            df = df.iloc[header_row + 1:]
            df.columns = headers

            state_col = None
            for col in headers:
                if isinstance(col, str) and not col.replace(",", "").replace(" ", "").isdigit():
                    state_col = col
                    break
            if state_col is None:
                state_col = headers[0]

            year_cols = [c for c in headers if isinstance(c, (int, float)) and 2020 <= c <= 2040]

            for _, row in df.iterrows():
                state_name = str(row.get(state_col, "")).strip()
                fips = _resolve_fips(state_name)
                if not fips:
                    continue

                for year_col in year_cols:
                    year = int(year_col)
                    val = row.get(year_col)
                    try:
                        expiring = float(val)
                        # If values look like they're in 1,000 acres, multiply
                        if expiring < 10000:
                            expiring *= 1000
                    except (ValueError, TypeError):
                        continue
                    if expiring > 0:
                        rows.append({
                            "state_fips": fips,
                            "year": year,
                            "expiring_acres": round(expiring, 1),
                        })
            if rows:
                break

    except Exception as exc:
        logger.error("Failed to parse expiration data: %s", exc)

    logger.info("Parsed %d expiration rows from %s", len(rows), filepath.name)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def load_manual_backfill() -> pd.DataFrame:
    """Load manually curated CRP backfill data if it exists.

    CSV columns: state_fips, year, enrolled_acres, expiring_acres, new_enrollment_acres
    """
    if not MANUAL_BACKFILL.exists():
        return pd.DataFrame()
    logger.info("Loading manual backfill from %s", MANUAL_BACKFILL)
    return pd.read_csv(MANUAL_BACKFILL, dtype={"state_fips": str})


def upsert_rows(rows: list[dict]) -> int:
    """Upsert CRP enrollment rows to the database."""
    if not rows:
        return 0

    session = get_sync_session()
    try:
        stmt = insert(CrpEnrollment.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_crp_enrollment",
            set_={
                "enrolled_acres": stmt.excluded.enrolled_acres,
                "expiring_acres": stmt.excluded.expiring_acres,
                "new_enrollment_acres": stmt.excluded.new_enrollment_acres,
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


def run_backfill():
    """Backfill CRP data from all available sources."""
    start = datetime.utcnow()

    # 1. Download and parse enrollment history
    enrollment_file = _download_file(ENROLLMENT_URL, "crp_enrollment_history.xlsx")
    enrollment_df = parse_enrollment_history(enrollment_file) if enrollment_file else pd.DataFrame()

    # 2. Download and parse expirations
    expiration_file = _download_file(EXPIRATION_URL, "crp_expirations_state.xlsx")
    expiration_df = parse_expiration_data(expiration_file) if expiration_file else pd.DataFrame()

    # 3. Load manual backfill
    manual_df = load_manual_backfill()

    # 4. Merge: enrollment provides enrolled_acres, expirations provides expiring_acres
    # Build a dict keyed by (state_fips, year) with all available fields
    merged: dict[tuple[str, int], dict] = {}

    for _, row in enrollment_df.iterrows():
        key = (row["state_fips"], int(row["year"]))
        merged.setdefault(key, {
            "state_fips": row["state_fips"],
            "year": int(row["year"]),
            "enrolled_acres": None,
            "expiring_acres": None,
            "new_enrollment_acres": None,
        })
        merged[key]["enrolled_acres"] = row.get("enrolled_acres")

    for _, row in expiration_df.iterrows():
        key = (row["state_fips"], int(row["year"]))
        merged.setdefault(key, {
            "state_fips": row["state_fips"],
            "year": int(row["year"]),
            "enrolled_acres": None,
            "expiring_acres": None,
            "new_enrollment_acres": None,
        })
        merged[key]["expiring_acres"] = row.get("expiring_acres")

    # Manual backfill overrides/fills gaps
    for _, row in manual_df.iterrows():
        key = (str(row["state_fips"]).zfill(2), int(row["year"]))
        merged.setdefault(key, {
            "state_fips": str(row["state_fips"]).zfill(2),
            "year": int(row["year"]),
            "enrolled_acres": None,
            "expiring_acres": None,
            "new_enrollment_acres": None,
        })
        for col in ("enrolled_acres", "expiring_acres", "new_enrollment_acres"):
            if col in row and pd.notna(row[col]):
                merged[key][col] = float(row[col])

    records = list(merged.values())
    n = upsert_rows(records)
    log_ingest_summary(logger, "crp_enrollment", n, start)
    return n


def run_refresh(year: int | None = None):
    """Refresh by re-downloading and re-parsing all data."""
    # CRP data is annual and comes in bulk files, so refresh = re-download
    # Clear cache to force fresh download
    for f in CACHE_DIR.glob("*.xlsx"):
        f.unlink()
    return run_backfill()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest FSA CRP enrollment and expiration data")
    parser.add_argument("--backfill", action="store_true", help="Full backfill from FSA")
    parser.add_argument("--year", type=int, default=None, help="(ignored, always full refresh)")
    args = parser.parse_args()

    run_backfill()
