"""ETL: Load fertilizer price data from multiple sources.

Sources:
  1. USDA ERS Excel (2000-2014) — historical dollar prices, one-time backfill
  2. FRED PPI indices (2014-present) — calibrated to dollar prices via 2014 anchor
  3. USDA AMS bi-weekly PDFs (current) — actual retail prices from Iowa/Illinois

Schedule: Quarterly (Jan, Apr, Jul, Oct) for FRED update.
          Bi-weekly for AMS PDF scrape (optional, adds current snapshot).
Target table: ers_fertilizer_prices
"""

import re
import sys
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_env, get_sync_session, setup_logging, log_ingest_summary

logger = setup_logging("ingest_fertilizer")

CACHE_DIR = Path(__file__).resolve().parent / "data"

# ---------------------------------------------------------------------------
# Source 1: USDA ERS Excel (2000-2014)
# ---------------------------------------------------------------------------

ERS_FERTILIZER_URL = (
    "https://www.ers.usda.gov/media/5291/"
    "all-fertilizer-use-and-price-tables-in-a-single-workbook.xls"
)


def fetch_ers_historical() -> pd.DataFrame:
    """Download and parse ERS Table 7 (fertilizer prices 2000-2014)."""
    CACHE_DIR.mkdir(exist_ok=True)
    dest = CACHE_DIR / "ers_fertilizer_prices.xls"

    logger.info(f"Downloading ERS fertilizer prices from {ERS_FERTILIZER_URL}")
    resp = requests.get(ERS_FERTILIZER_URL, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)

    df = pd.read_excel(dest, sheet_name="Table7", header=None)

    COL_YEAR = 0
    COL_MONTH = 1
    COL_AMMONIA = 2   # Anhydrous ammonia ($/ton)
    COL_DAP = 9       # Diammonium phosphate 18-46-0 ($/ton)
    COL_POTASH = 10   # Potassium chloride 60% ($/ton)

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    rows = []
    for idx in range(6, len(df)):
        try:
            year = int(df.iloc[idx, COL_YEAR])
        except (ValueError, TypeError):
            continue
        if year < 2000:
            continue

        month_str = str(df.iloc[idx, COL_MONTH]).strip().lower()[:3]
        month = month_map.get(month_str)
        if month is None:
            continue

        quarter = (month - 1) // 3 + 1

        def safe_float(val):
            try:
                return round(float(val), 2)
            except (ValueError, TypeError):
                return None

        rows.append({
            "quarter": f"{year}-Q{quarter}",
            "anhydrous_ammonia_ton": safe_float(df.iloc[idx, COL_AMMONIA]),
            "dap_ton": safe_float(df.iloc[idx, COL_DAP]) if COL_DAP < len(df.columns) else None,
            "potash_ton": safe_float(df.iloc[idx, COL_POTASH]) if COL_POTASH < len(df.columns) else None,
        })

    result = pd.DataFrame(rows)
    logger.info(f"  ERS: {len(result)} records (2000-2014)")
    return result


# ---------------------------------------------------------------------------
# Source 2: FRED PPI Indices (2014-present), calibrated to dollars
# ---------------------------------------------------------------------------

# FRED series for each fertilizer type
FRED_SERIES = {
    "anhydrous_ammonia_ton": "PCU325311325311",  # PPI Nitrogenous Fertilizer Mfg
    "dap_ton": "WPU0653",                        # PPI Phosphatic Fertilizer
    "potash_ton": "WPU0652",                      # PPI Fertilizer Materials (general)
}

# Calibration anchors: known ERS dollar prices at 2014-Q1
# These are the last reliable dollar values from the ERS dataset.
# FRED indices at the same date are used to compute a $/index-point ratio.
CALIBRATION_DATE = "2014-03-01"
CALIBRATION_PRICES = {
    "anhydrous_ammonia_ton": 851.0,  # ERS 2014 Mar anhydrous ammonia $/ton
    "dap_ton": 565.0,               # ERS 2014 Mar DAP $/ton (estimated)
    "potash_ton": 420.0,            # ERS 2014 Mar potash $/ton (estimated)
}


def fetch_fred_fertilizer(start_date: str = "2014-01-01") -> pd.DataFrame:
    """Fetch FRED PPI indices and calibrate to approximate dollar prices.

    Calibration method: ratio = known_dollar_price / index_at_calibration_date
    Estimated dollar price = index_value * ratio
    """
    api_key = get_env("FRED_API_KEY")
    if not api_key:
        logger.warning("FRED_API_KEY not set, skipping FRED fertilizer fetch")
        return pd.DataFrame()

    # Fetch calibration-date index values
    cal_indices = {}
    for product, series_id in FRED_SERIES.items():
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json"
            f"&observation_start={CALIBRATION_DATE}&observation_end={CALIBRATION_DATE}"
        )
        resp = requests.get(url, timeout=15)
        obs = resp.json().get("observations", [])
        if obs and obs[0]["value"] != ".":
            cal_indices[product] = float(obs[0]["value"])
        else:
            logger.warning(f"  No calibration value for {series_id} at {CALIBRATION_DATE}")

    # Compute calibration ratios
    ratios = {}
    for product in FRED_SERIES:
        if product in cal_indices and cal_indices[product] > 0:
            ratios[product] = CALIBRATION_PRICES[product] / cal_indices[product]

    if not ratios:
        logger.error("  Could not compute calibration ratios")
        return pd.DataFrame()

    logger.info(f"  Calibration ratios: { {k: round(v, 4) for k, v in ratios.items()} }")

    # Fetch full history from start_date
    price_data = {}  # {quarter_str: {product: dollar_value}}

    for product, series_id in FRED_SERIES.items():
        if product not in ratios:
            continue

        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={api_key}&file_type=json"
            f"&observation_start={start_date}&sort_order=asc"
        )
        resp = requests.get(url, timeout=15)
        obs = resp.json().get("observations", [])

        for o in obs:
            if o["value"] == ".":
                continue
            d = o["date"]  # "YYYY-MM-DD"
            year = int(d[:4])
            month = int(d[5:7])
            quarter = (month - 1) // 3 + 1
            q_str = f"{year}-Q{quarter}"

            index_val = float(o["value"])
            dollar_val = round(index_val * ratios[product], 2)

            if q_str not in price_data:
                price_data[q_str] = {}
            if product not in price_data[q_str]:
                price_data[q_str][product] = []
            price_data[q_str][product].append(dollar_val)

    # Average monthly values within each quarter
    rows = []
    for q_str in sorted(price_data.keys()):
        row = {"quarter": q_str}
        for product in FRED_SERIES:
            vals = price_data.get(q_str, {}).get(product, [])
            if vals:
                row[product] = round(sum(vals) / len(vals), 2)
        rows.append(row)

    result = pd.DataFrame(rows)
    logger.info(f"  FRED: {len(result)} quarterly records ({start_date} to present)")
    return result


# ---------------------------------------------------------------------------
# Source 3: USDA AMS PDF scraper (current bi-weekly prices)
# ---------------------------------------------------------------------------

AMS_REPORTS = {
    "IA": "https://www.ams.usda.gov/mnreports/ams_2863.pdf",
    "IL": "https://www.ams.usda.gov/mnreports/ams_3195.pdf",
}


def fetch_ams_current(states: list[str] | None = None) -> pd.DataFrame:
    """Scrape current fertilizer prices from USDA AMS bi-weekly PDFs.

    Returns the most recent prices averaged across requested states.
    Requires pypdf for PDF parsing.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed, skipping AMS PDF scrape (pip install pypdf)")
        return pd.DataFrame()

    if states is None:
        states = list(AMS_REPORTS.keys())

    CACHE_DIR.mkdir(exist_ok=True)
    all_prices = []

    for state in states:
        url = AMS_REPORTS.get(state)
        if not url:
            continue

        try:
            dest = CACHE_DIR / f"ams_{state.lower()}_production_cost.pdf"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            dest.write_bytes(resp.content)

            reader = PdfReader(dest)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"

            prices = _parse_ams_text(text, state)
            if prices:
                all_prices.append(prices)
                logger.info(f"  AMS {state}: ammonia=${prices.get('anhydrous_ammonia_ton')}, "
                           f"potash=${prices.get('potash_ton')}")

        except Exception as e:
            logger.warning(f"  AMS {state} failed: {e}")

    if not all_prices:
        return pd.DataFrame()

    # Average across states, determine quarter from report date
    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    q_str = f"{today.year}-Q{quarter}"

    avg = {"quarter": q_str}
    for field in ["anhydrous_ammonia_ton", "dap_ton", "potash_ton"]:
        vals = [p[field] for p in all_prices if p.get(field) is not None]
        if vals:
            avg[field] = round(sum(vals) / len(vals), 2)

    result = pd.DataFrame([avg])
    logger.info(f"  AMS current: {q_str} (averaged {len(all_prices)} states)")
    return result


def _parse_ams_text(text: str, state: str) -> dict | None:
    """Extract fertilizer prices from AMS production cost PDF text."""
    prices = {}

    # Pattern: product name followed by price range and average
    # "Anhydrous Ammonia\nAsk\n935.00 - 1,125.00\n1,031.00"
    lines = text.split("\n")

    product_map = {
        "anhydrous ammonia": "anhydrous_ammonia_ton",
        "map (monoammonium": "dap_ton",      # MAP is close proxy for DAP
        "dap": "dap_ton",
        "diammonium phosphate": "dap_ton",
        "potash": "potash_ton",
    }

    for i, line in enumerate(lines):
        line_lower = line.strip().lower()
        for keyword, field in product_map.items():
            if keyword in line_lower and field not in prices:
                # Look ahead for the average price (usually 3-4 lines after)
                for j in range(i + 1, min(i + 6, len(lines))):
                    # Match a standalone number like "1,031.00" or "495.17"
                    match = re.match(r"^\s*([\d,]+\.\d{2})\s*$", lines[j].strip())
                    if match:
                        # Skip range lines (contain " - ")
                        if " - " in lines[j]:
                            continue
                        val = float(match.group(1).replace(",", ""))
                        prices[field] = val
                        break

    return prices if prices else None


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------

def upsert_fertilizer_prices(df: pd.DataFrame) -> int:
    """Upsert fertilizer prices into ers_fertilizer_prices table."""
    if df.empty:
        return 0

    session = get_sync_session()
    try:
        from backend.models.db_tables import ErsFertilizerPrice

        records = df.to_dict(orient="records")
        stmt = insert(ErsFertilizerPrice.__table__).values(records)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_fertilizer_prices",
            set_={
                "anhydrous_ammonia_ton": stmt.excluded.anhydrous_ammonia_ton,
                "dap_ton": stmt.excluded.dap_ton,
                "potash_ton": stmt.excluded.potash_ton,
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(mode: str = "all"):
    """Main entry point.

    Modes:
      all       — Run all sources (ERS backfill + FRED calibration + AMS current)
      ers       — ERS Excel only (2000-2014 backfill)
      fred      — FRED index calibration only (2014-present)
      ams       — AMS PDF scrape only (current quarter)
    """
    start = datetime.utcnow()
    total = 0

    if mode in ("all", "ers"):
        try:
            df_ers = fetch_ers_historical()
            n = upsert_fertilizer_prices(df_ers)
            total += n
            logger.info(f"  ERS: {n} rows upserted")
        except Exception as e:
            logger.error(f"  ERS fetch failed: {e}")

    if mode in ("all", "fred"):
        try:
            # Start from 2014 to overlap with ERS calibration anchor
            df_fred = fetch_fred_fertilizer(start_date="2014-01-01")
            n = upsert_fertilizer_prices(df_fred)
            total += n
            logger.info(f"  FRED: {n} rows upserted")
        except Exception as e:
            logger.error(f"  FRED fetch failed: {e}")

    if mode in ("all", "ams"):
        try:
            df_ams = fetch_ams_current()
            n = upsert_fertilizer_prices(df_ams)
            total += n
            logger.info(f"  AMS: {n} rows upserted")
        except Exception as e:
            logger.error(f"  AMS scrape failed: {e}")

    log_ingest_summary(logger, "ers_fertilizer_prices", total, start)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    run(mode=mode)
