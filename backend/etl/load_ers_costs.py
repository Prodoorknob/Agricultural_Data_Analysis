"""ETL: Load USDA ERS production cost data from Excel files.

Schedule: Annual, January (during yearly maintenance).
Source: https://www.ers.usda.gov/webdocs/DataFiles/50048/{commodity}costandreturn.xlsx
Target table: ers_production_costs
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary

logger = setup_logging("load_ers_costs")

# ERS cost-and-return spreadsheet URLs
ERS_URLS = {
    "corn": "https://www.ers.usda.gov/webdocs/DataFiles/50048/CornCostReturn.xlsx",
    "soybean": "https://www.ers.usda.gov/webdocs/DataFiles/50048/SoybeanCostReturn.xlsx",
    "wheat": "https://www.ers.usda.gov/webdocs/DataFiles/50048/WheatCostReturn.xlsx",
}

# Local cache directory for downloaded Excel files
CACHE_DIR = Path(__file__).resolve().parent / "data"


def download_ers_excel(commodity: str) -> Path:
    """Download ERS Excel file to local cache. Returns path to file."""
    CACHE_DIR.mkdir(exist_ok=True)
    url = ERS_URLS[commodity]
    dest = CACHE_DIR / f"ers_{commodity}_costs.xlsx"

    logger.info(f"Downloading ERS costs for {commodity} from {url}")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    logger.info(f"  Saved to {dest} ({len(resp.content)} bytes)")
    return dest


def parse_ers_excel(filepath: Path, commodity: str) -> pd.DataFrame:
    """Parse ERS cost-and-return Excel into standardized rows.

    The ERS Excel files have a complex layout with multiple header rows.
    We look for rows containing year and cost data in the main sheet.
    """
    logger.info(f"Parsing {filepath}")

    # Try reading the first sheet — ERS files vary in structure
    try:
        # Read all sheets to find the one with cost data
        xls = pd.ExcelFile(filepath)
        sheet_names = xls.sheet_names
        logger.info(f"  Sheets found: {sheet_names}")

        # The main data is typically in a sheet containing "Cost" or the first sheet
        target_sheet = None
        for name in sheet_names:
            if "cost" in name.lower() or "return" in name.lower():
                target_sheet = name
                break
        if target_sheet is None:
            target_sheet = sheet_names[0]

        df = pd.read_excel(filepath, sheet_name=target_sheet, header=None)
    except Exception as e:
        logger.error(f"  Failed to read Excel: {e}")
        return pd.DataFrame()

    # Strategy: scan rows for year-like values (2000-2030) and extract costs
    # ERS files have "Item" column with cost labels and year columns
    rows = []

    # Try to find header row (contains years as column headers)
    header_row = None
    for idx in range(min(20, len(df))):
        row_vals = df.iloc[idx].astype(str)
        year_count = sum(1 for v in row_vals if v.isdigit() and 2000 <= int(v) <= 2030)
        if year_count >= 5:
            header_row = idx
            break

    if header_row is None:
        logger.warning("  Could not find header row with year columns — skipping")
        return pd.DataFrame()

    # Extract years from header
    headers = df.iloc[header_row]
    year_cols = {}
    for col_idx, val in enumerate(headers):
        try:
            year = int(float(val))
            if 2000 <= year <= 2030:
                year_cols[col_idx] = year
        except (ValueError, TypeError):
            continue

    logger.info(f"  Found {len(year_cols)} year columns (header row {header_row})")

    # Find rows for variable cost and total cost
    # Common labels: "Variable costs", "Total costs listed"
    item_col = 0  # First column usually has the item labels
    variable_cost_row = None
    total_cost_row = None

    for idx in range(header_row + 1, len(df)):
        label = str(df.iloc[idx, item_col]).strip().lower()
        if "variable cost" in label and variable_cost_row is None:
            variable_cost_row = idx
        if "total cost" in label and "listed" not in label and total_cost_row is None:
            total_cost_row = idx

    # Build output rows
    for col_idx, year in year_cols.items():
        var_cost = None
        tot_cost = None

        if variable_cost_row is not None:
            try:
                var_cost = float(df.iloc[variable_cost_row, col_idx])
            except (ValueError, TypeError):
                pass

        if total_cost_row is not None:
            try:
                tot_cost = float(df.iloc[total_cost_row, col_idx])
            except (ValueError, TypeError):
                pass

        if var_cost is not None or tot_cost is not None:
            rows.append({
                "year": year,
                "commodity": commodity,
                "variable_cost_per_bu": var_cost,
                "total_cost_per_bu": tot_cost,
            })

    result = pd.DataFrame(rows)
    logger.info(f"  Extracted {len(result)} year-commodity cost records")
    return result


def upsert_ers_costs(df: pd.DataFrame) -> int:
    """Upsert ERS cost data into the ers_production_costs table."""
    if df.empty:
        return 0

    session = get_sync_session()
    try:
        from backend.models.db_tables import ErsProductionCost

        rows = df.to_dict(orient="records")
        stmt = insert(ErsProductionCost.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ers_costs",
            set_={
                "variable_cost_per_bu": stmt.excluded.variable_cost_per_bu,
                "total_cost_per_bu": stmt.excluded.total_cost_per_bu,
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


def run(commodities: list[str] | None = None):
    """Main entry point — download and load ERS costs for specified commodities."""
    start = datetime.utcnow()
    if commodities is None:
        commodities = list(ERS_URLS.keys())

    total_rows = 0
    for commodity in commodities:
        try:
            filepath = download_ers_excel(commodity)
            df = parse_ers_excel(filepath, commodity)
            n = upsert_ers_costs(df)
            total_rows += n
            logger.info(f"  {commodity}: {n} rows upserted")
        except requests.HTTPError as e:
            logger.error(f"  {commodity}: HTTP error downloading ERS file — {e}")
            raise
        except Exception as e:
            logger.error(f"  {commodity}: error — {e}")
            raise

    log_ingest_summary(logger, "ers_production_costs", total_rows, start)


if __name__ == "__main__":
    # Optional: pass commodity names as args (e.g., "corn soybean")
    commodities = sys.argv[1:] if len(sys.argv) > 1 else None
    run(commodities=commodities)
