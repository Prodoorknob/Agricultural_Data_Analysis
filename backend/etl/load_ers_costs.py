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

# ERS cost-and-return spreadsheet URLs.
#
# ERS publishes annual cost-of-production tables for each major field crop
# under /media/<id>/<name>.xlsx. The IDs occasionally change when ERS refreshes
# the dataset; if download fails the ETL falls back to a manually-downloaded
# copy at backend/etl/data/ers_<commodity>_costs.xlsx so operators can patch
# without blocking the cron.
#
# If a commodity has no ERS series (e.g. hay isn't in Commodity Costs and
# Returns), leave it out — the profit endpoint will respond 404 gracefully.
ERS_URLS = {
    # URLs confirmed by scraping the ERS Commodity Costs and Returns index page
    # at /data-products/commodity-costs-and-returns/ — they differ from the
    # ones discoverable via naive media-ID sweeps.
    "corn":    "https://www.ers.usda.gov/media/4961/corn.xlsx",
    "cotton":  "https://www.ers.usda.gov/media/4963/cotton.xlsx",
    "barley":  "https://www.ers.usda.gov/media/4965/barley.xlsx",
    "peanut":  "https://www.ers.usda.gov/media/4967/peanuts.xlsx",
    "rice":    "https://www.ers.usda.gov/media/4969/rice.xlsx",
    "sorghum": "https://www.ers.usda.gov/media/4971/sorghum.xlsx",
    "oats":    "https://www.ers.usda.gov/media/4973/oats.xlsx",
    "soybean": "https://www.ers.usda.gov/media/4975/soybeans.xlsx",
    "wheat":   "https://www.ers.usda.gov/media/4977/wheat.xlsx",
}

# Local cache directory for downloaded Excel files
CACHE_DIR = Path(__file__).resolve().parent / "data"


def download_ers_excel(commodity: str) -> Path:
    """Download ERS Excel to local cache. Falls back to existing cache on
    HTTP failure so a stale media ID doesn't break the whole ingest run."""
    CACHE_DIR.mkdir(exist_ok=True)
    url = ERS_URLS[commodity]
    dest = CACHE_DIR / f"ers_{commodity}_costs.xlsx"

    logger.info(f"Downloading ERS costs for {commodity} from {url}")
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        logger.info(f"  Saved to {dest} ({len(resp.content)} bytes)")
        return dest
    except requests.HTTPError as e:
        if dest.exists():
            logger.warning(
                f"  {commodity}: download failed ({e}); using cached copy {dest}"
            )
            return dest
        raise FileNotFoundError(
            f"{commodity}: download failed and no cached copy at {dest}. "
            f"Either fix ERS_URLS[{commodity!r}] or manually save the Excel to {dest}."
        ) from e


def parse_ers_excel(filepath: Path, commodity: str) -> pd.DataFrame:
    """Parse ERS cost-and-return Excel into standardized rows.

    The ERS Excel files (updated 2025+) have a 'Data sheet (machine readable)'
    with tidy-format data: columns [Commodity, Category, Item, Units, Region, Year, Value].
    Falls back to the pivot-sheet scan for older file formats.
    """
    logger.info(f"Parsing {filepath}")

    try:
        xls = pd.ExcelFile(filepath)
        sheet_names = xls.sheet_names
        logger.info(f"  Sheets found: {sheet_names}")
    except Exception as e:
        logger.error(f"  Failed to read Excel: {e}")
        return pd.DataFrame()

    # --- Prefer machine-readable sheet (new ERS format) ---
    mr_sheet = None
    for name in sheet_names:
        if "machine readable" in name.lower() or "data sheet" in name.lower():
            mr_sheet = name
            break

    if mr_sheet:
        return _parse_machine_readable(filepath, mr_sheet, commodity)

    # --- Fallback: pivot-sheet scan (legacy format) ---
    return _parse_pivot_sheet(filepath, sheet_names, commodity)


def _parse_machine_readable(filepath: Path, sheet_name: str, commodity: str) -> pd.DataFrame:
    """Parse the tidy 'Data sheet (machine readable)' format."""
    df = pd.read_excel(filepath, sheet_name=sheet_name, header=0)
    logger.info(f"  Machine-readable sheet: {len(df)} rows")

    # Filter to U.S. total only
    us = df[df["Region"].str.contains("U.S. total", case=False, na=False)].copy()

    operating = us[us["Item"].str.contains("Total, operating costs", case=False, na=False)]
    total = us[us["Item"].str.contains("Total, costs listed", case=False, na=False)]
    yields = us[us["Item"].str.contains("^Yield$", case=False, na=False, regex=True)]

    op_by_year = dict(zip(operating["Year"], operating["Value"]))
    tot_by_year = dict(zip(total["Year"], total["Value"]))
    yield_by_year = dict(zip(yields["Year"], yields["Value"]))

    # Yield units come from the Units column; same for every row of the
    # yield series, so we can pluck the first. Falls back to bushels for
    # commodities that don't publish a unit.
    yield_unit = None
    if not yields.empty and "Units" in yields.columns:
        unit_series = yields["Units"].dropna()
        if not unit_series.empty:
            yield_unit = str(unit_series.iloc[0]).strip()

    rows = []
    all_years = sorted(set(op_by_year.keys()) | set(tot_by_year.keys()))
    for year in all_years:
        if year < 2000:
            continue
        y = yield_by_year.get(year)
        op = op_by_year.get(year)
        tot = tot_by_year.get(year)

        # Per-acre costs are the ERS-published figures; per-bushel is a
        # convenience derivation. Store both — per-bu lets price-forecasting
        # compute margin-per-bushel directly; per-acre lets the Crops-tab
        # profit chart join with per-acre yield in any unit system.
        var_per_bu = (op / y) if op and y and y > 0 else None
        tot_per_bu = (tot / y) if tot and y and y > 0 else None

        if any(v is not None for v in (var_per_bu, tot_per_bu, op, tot)):
            rows.append({
                "year": int(year),
                "commodity": commodity,
                "variable_cost_per_bu": round(var_per_bu, 4) if var_per_bu else None,
                "total_cost_per_bu": round(tot_per_bu, 4) if tot_per_bu else None,
                "variable_cost_per_acre": round(op, 2) if op else None,
                "total_cost_per_acre": round(tot, 2) if tot else None,
                "yield_units": yield_unit,
                "yield_value": round(y, 2) if y else None,
            })

    result = pd.DataFrame(rows)
    logger.info(f"  Extracted {len(result)} year-commodity cost records (machine-readable)")
    return result


def _parse_pivot_sheet(filepath: Path, sheet_names: list[str], commodity: str) -> pd.DataFrame:
    """Fallback parser for older ERS pivot-format Excel files."""
    target_sheet = None
    for name in sheet_names:
        if "cost" in name.lower() or "return" in name.lower() or "pivot" in name.lower():
            target_sheet = name
            break
    if target_sheet is None:
        target_sheet = sheet_names[0]

    df = pd.read_excel(filepath, sheet_name=target_sheet, header=None)
    rows = []

    header_row = None
    for idx in range(min(20, len(df))):
        row_vals = df.iloc[idx].astype(str)
        year_count = sum(1 for v in row_vals if v.isdigit() and 2000 <= int(v) <= 2030)
        if year_count >= 5:
            header_row = idx
            break

    if header_row is None:
        logger.warning("  Could not find header row with year columns - skipping")
        return pd.DataFrame()

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

    variable_cost_row = None
    total_cost_row = None
    for idx in range(header_row + 1, len(df)):
        label = str(df.iloc[idx, 0]).strip().lower()
        if "variable cost" in label and variable_cost_row is None:
            variable_cost_row = idx
        if "total cost" in label and "listed" not in label and total_cost_row is None:
            total_cost_row = idx

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
    logger.info(f"  Extracted {len(result)} year-commodity cost records (pivot)")
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
                "variable_cost_per_acre": stmt.excluded.variable_cost_per_acre,
                "total_cost_per_acre": stmt.excluded.total_cost_per_acre,
                "yield_units": stmt.excluded.yield_units,
                "yield_value": stmt.excluded.yield_value,
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
    failed: list[str] = []
    for commodity in commodities:
        try:
            filepath = download_ers_excel(commodity)
            df = parse_ers_excel(filepath, commodity)
            n = upsert_ers_costs(df)
            total_rows += n
            logger.info(f"  {commodity}: {n} rows upserted")
        except FileNotFoundError as e:
            # No cached copy + URL dead — skip, keep going.
            logger.warning(f"  {commodity}: skipped ({e})")
            failed.append(commodity)
        except Exception as e:
            logger.error(f"  {commodity}: error — {e}")
            failed.append(commodity)
    if failed:
        logger.warning(f"ERS ingest skipped {len(failed)} commodity(s): {failed}")

    log_ingest_summary(logger, "ers_production_costs", total_rows, start)


if __name__ == "__main__":
    # Optional: pass commodity names as args (e.g., "corn soybean")
    commodities = sys.argv[1:] if len(sys.argv) > 1 else None
    run(commodities=commodities)
