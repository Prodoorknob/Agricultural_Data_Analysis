"""Ingest RMA Summary of Business crop insurance data for acreage features.

Downloads annual ZIP files from RMA's State/County/Crop coverage-level dataset,
filters to corn (0041), soybean (0081), wheat (0011), aggregates to state level,
and upserts net_reported_acres / policies / liability into rma_insured_acres.

Source: https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/state_county_crop/
File format: pipe (|) delimited flat files

Usage:
    python -m backend.etl.ingest_rma --backfill
    python -m backend.etl.ingest_rma --year 2025
"""

import argparse
import csv
import io
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary
from backend.models.db_tables import RmaInsuredAcres

logger = setup_logging("ingest_rma")

SOB_BASE_URL = "https://pubfs-rma.fpac.usda.gov/pub/Web_Data_Files/Summary_of_Business/state_county_crop"
CACHE_DIR = Path(__file__).parent / "data" / "rma_cache"

# RMA crop codes → our commodity names
CROP_CODES = {
    "0041": "corn",
    "0081": "soybean",
    "0011": "wheat",
}

# Expected column indices in sobcov pipe-delimited files (0-indexed).
# Based on the coverage-level record layout:
#  0: Commodity Year, 1: State Code, 2: State Abbreviation,
#  3: County Code, 4: County Name, 5: Crop Code, 6: Crop Name,
#  7: Insurance Plan Code, 8: Insurance Plan Abbreviation,
#  9: Coverage Category, 10: Stage Code,
# 11: Policies Sold Count, 12: Policies Earning Premium Count,
# 13: Policies Indemnified Count, 14: Units Earning Premium Count,
# 15: Units Indemnified Count, 16: Quantity Type,
# 17: Net Reported Quantity, 18: Endorsed/Companion Acres,
# 19: Liability Amount, 20: Total Premium Amount, 21: Subsidy Amount,
# 22: State/Private Subsidy, 23: Additional Subsidy,
# 24: EFA Premium Discount, 25: Net Farmer Paid Premium,
# 25: Indemnity Amount, 26: Loss Ratio
IDX_YEAR = 0
IDX_STATE_CODE = 1
IDX_CROP_CODE = 5
IDX_POLICIES_EARNING = 12
IDX_ACRES = 18  # Endorsed/Companion Acres
IDX_LIABILITY = 19


def _safe_float(val: str) -> float:
    """Convert string to float, handling commas and blanks."""
    if not val or val.strip() in ("", "N/A"):
        return 0.0
    return float(val.strip().replace(",", ""))


def _safe_int(val: str) -> int:
    if not val or val.strip() in ("", "N/A"):
        return 0
    return int(float(val.strip().replace(",", "")))


def download_sob_zip(year: int) -> Path | None:
    """Download the sobcov ZIP for a given year and cache locally."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local_zip = CACHE_DIR / f"sobcov_{year}.zip"

    if local_zip.exists():
        logger.info("Using cached %s", local_zip.name)
        return local_zip

    url = f"{SOB_BASE_URL}/sobcov_{year}.zip"
    logger.info("Downloading %s ...", url)
    try:
        resp = requests.get(url, timeout=120, stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to download sobcov_%d.zip: %s", year, exc)
        return None

    with open(local_zip, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 64):
            f.write(chunk)

    size_mb = local_zip.stat().st_size / (1024 * 1024)
    logger.info("Downloaded sobcov_%d.zip (%.1f MB)", year, size_mb)
    return local_zip


def parse_sob_zip(zip_path: Path, year: int) -> list[dict]:
    """Parse a sobcov ZIP, filter to target crops, aggregate to state level.

    Returns list of dicts ready for DB upsert with keys:
      state_fips, commodity, crop_year, net_reported_acres, policies_earning, liability_amount
    """
    # Accumulate by (state_fips, commodity)
    agg: dict[tuple[str, str], dict] = {}

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            # Skip directories and non-data files (record layouts, etc.)
            if name.endswith("/") or not name.lower().endswith(".txt"):
                # Also try .csv or no extension
                if not any(name.lower().endswith(ext) for ext in (".csv", ".dat")):
                    continue

            logger.info("Parsing %s from %s", name, zip_path.name)
            with zf.open(name) as f:
                # Detect encoding
                raw = f.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")

                reader = csv.reader(io.StringIO(text), delimiter="|")
                for line_num, fields in enumerate(reader):
                    if len(fields) < 20:
                        continue

                    # Skip header rows (first field would be non-numeric)
                    crop_code = fields[IDX_CROP_CODE].strip()
                    if crop_code not in CROP_CODES:
                        continue

                    state_code = fields[IDX_STATE_CODE].strip().zfill(2)
                    if len(state_code) != 2 or not state_code.isdigit():
                        continue

                    commodity = CROP_CODES[crop_code]
                    acres = _safe_float(fields[IDX_ACRES])
                    policies = _safe_int(fields[IDX_POLICIES_EARNING])
                    liability = _safe_float(fields[IDX_LIABILITY])

                    key = (state_code, commodity)
                    if key not in agg:
                        agg[key] = {
                            "state_fips": state_code,
                            "commodity": commodity,
                            "crop_year": year,
                            "net_reported_acres": 0.0,
                            "policies_earning": 0,
                            "liability_amount": 0.0,
                        }
                    agg[key]["net_reported_acres"] += acres
                    agg[key]["policies_earning"] += policies
                    agg[key]["liability_amount"] += liability

    rows = list(agg.values())
    # Round numeric fields
    for r in rows:
        r["net_reported_acres"] = round(r["net_reported_acres"], 1)
        r["liability_amount"] = round(r["liability_amount"], 2)

    logger.info("Parsed %d state-commodity rows for %d", len(rows), year)
    return rows


def upsert_rows(rows: list[dict]) -> int:
    """Upsert RMA insured acres to the database."""
    if not rows:
        return 0

    session = get_sync_session()
    try:
        stmt = insert(RmaInsuredAcres.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_rma_insured",
            set_={
                "net_reported_acres": stmt.excluded.net_reported_acres,
                "policies_earning": stmt.excluded.policies_earning,
                "liability_amount": stmt.excluded.liability_amount,
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
    """Backfill all years from RMA SOB downloads."""
    start = datetime.utcnow()
    total = 0
    for year in range(year_start, year_end + 1):
        zip_path = download_sob_zip(year)
        if not zip_path:
            continue
        rows = parse_sob_zip(zip_path, year)
        n = upsert_rows(rows)
        logger.info("Year %d: upserted %d rows", year, n)
        total += n

    log_ingest_summary(logger, "rma_insured_acres", total, start)
    return total


def run_refresh(year: int | None = None):
    """Refresh current or specified year only."""
    year = year or datetime.utcnow().year
    start = datetime.utcnow()

    # Delete cached ZIP to force re-download
    cached = CACHE_DIR / f"sobcov_{year}.zip"
    if cached.exists():
        cached.unlink()

    zip_path = download_sob_zip(year)
    if not zip_path:
        logger.error("Could not download SOB for %d", year)
        return 0

    rows = parse_sob_zip(zip_path, year)
    n = upsert_rows(rows)
    log_ingest_summary(logger, "rma_insured_acres", n, start)
    return n


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest RMA crop insurance insured acreage")
    parser.add_argument("--backfill", action="store_true", help="Backfill 2000-2025")
    parser.add_argument("--year", type=int, default=None, help="Refresh a specific year")
    parser.add_argument("--year-start", type=int, default=2000, help="Backfill start year")
    parser.add_argument("--year-end", type=int, default=2025, help="Backfill end year")
    args = parser.parse_args()

    if args.backfill:
        run_backfill(args.year_start, args.year_end)
    else:
        run_refresh(args.year)
