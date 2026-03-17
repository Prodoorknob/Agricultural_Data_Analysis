"""ETL: Ingest USDA WASDE supply/demand data from PSD Online CSV.

Schedule: Monthly, ~12th of month at 14:00 UTC (day after WASDE release).
Source: https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip (~15MB)
Target table: wasde_releases
"""

import io
import sys
import zipfile
from datetime import datetime

import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary

logger = setup_logging("ingest_wasde")

WASDE_URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"

# Map PSD commodity names to our normalized names
COMMODITY_MAP = {
    "Corn": "corn",
    "Soybeans": "soybean",
    "Wheat": "wheat",
}

# PSD attribute names we need
TARGET_ATTRS = {
    "Beginning Stocks",
    "Production",
    "Total Domestic Cons.",
    "Exports",
    "Ending Stocks",
}


def fetch_psd_data() -> pd.DataFrame:
    """Download and extract the PSD all-data CSV from USDA."""
    logger.info(f"Downloading PSD dataset from {WASDE_URL}")
    resp = requests.get(WASDE_URL, timeout=120)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        # Find the CSV file inside the zip
        csv_names = [n for n in z.namelist() if n.endswith(".csv")]
        if not csv_names:
            raise ValueError("No CSV file found in PSD zip archive")
        csv_name = csv_names[0]
        logger.info(f"  Extracting {csv_name} ({resp.headers.get('Content-Length', '?')} bytes)")
        df = pd.read_csv(z.open(csv_name), low_memory=False)

    logger.info(f"  Raw PSD dataset: {len(df)} rows, {len(df.columns)} columns")
    return df


def filter_and_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Filter PSD data to US corn/soy/wheat and pivot into wasde_releases schema."""

    # Filter to United States + target commodities + target attributes
    mask = (
        (df["Country_Name"] == "United States")
        & (df["Commodity_Description"].isin(COMMODITY_MAP.keys()))
        & (df["Attribute_Description"].isin(TARGET_ATTRS))
    )
    df = df[mask].copy()
    logger.info(f"  After filtering: {len(df)} rows")

    if df.empty:
        return pd.DataFrame()

    # Normalize commodity name
    df["commodity"] = df["Commodity_Description"].map(COMMODITY_MAP)

    # Build marketing year string: e.g. "2025/2026" -> "2025-2026"
    df["marketing_year"] = (
        df["Market_Year"].astype(str)
        + "-"
        + (df["Market_Year"].astype(int) + 1).astype(str)
    )

    # The value column in PSD is typically 'Value' (in 1000 MT for most, but
    # for US domestic we use the unit as-is — convert later as needed)
    df["value"] = pd.to_numeric(df["Value"].astype(str).str.replace(",", ""), errors="coerce")

    # Pivot attributes into columns
    pivot = df.pivot_table(
        index=["commodity", "marketing_year", "Calendar_Year"],
        columns="Attribute_Description",
        values="value",
        aggfunc="first",
    ).reset_index()

    # Rename columns to match our schema
    col_renames = {
        "Production": "us_production",
        "Exports": "us_exports",
        "Ending Stocks": "ending_stocks",
        "Beginning Stocks": "beginning_stocks",
        "Total Domestic Cons.": "total_domestic_cons",
    }
    pivot = pivot.rename(columns=col_renames)

    return pivot


def compute_stocks_to_use(df: pd.DataFrame) -> pd.DataFrame:
    """Compute stocks-to-use ratio = ending_stocks / total_use."""
    if df.empty:
        return df

    # Total use = total domestic consumption + exports
    total_use = df.get("total_domestic_cons", 0) + df.get("us_exports", 0)
    # Avoid division by zero
    df["stocks_to_use"] = df["ending_stocks"] / total_use.replace(0, pd.NA)
    df["stocks_to_use"] = df["stocks_to_use"].round(4)

    return df


def build_wasde_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Build rows matching the wasde_releases table schema."""
    if df.empty:
        return pd.DataFrame()

    df = compute_stocks_to_use(df)

    # Use Calendar_Year as a proxy for release date (actual release dates
    # would require a separate lookup; we use year-month approximation)
    # For the latest data, we set release_date to today
    today = datetime.utcnow().date()

    rows = []
    for _, row in df.iterrows():
        calendar_year = int(row.get("Calendar_Year", today.year))
        # Approximate release date as December of the calendar year
        # (latest marketing year data gets today's date)
        if calendar_year >= today.year:
            release_date = today
        else:
            from datetime import date
            release_date = date(calendar_year, 12, 1)

        rows.append({
            "release_date": release_date,
            "commodity": row["commodity"],
            "marketing_year": row["marketing_year"],
            "us_production": row.get("us_production"),
            "us_exports": row.get("us_exports"),
            "ending_stocks": row.get("ending_stocks"),
            "stocks_to_use": row.get("stocks_to_use"),
            "world_production": None,  # PSD US-only data; world data available separately
            "source": "usda_wasde",
        })

    return pd.DataFrame(rows)


def upsert_wasde(df: pd.DataFrame) -> int:
    """Upsert WASDE data into the wasde_releases table."""
    if df.empty:
        return 0

    session = get_sync_session()
    try:
        from backend.models.db_tables import WasdeRelease

        rows = df.to_dict(orient="records")
        stmt = insert(WasdeRelease.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_wasde_releases",
            set_={
                "us_production": stmt.excluded.us_production,
                "us_exports": stmt.excluded.us_exports,
                "ending_stocks": stmt.excluded.ending_stocks,
                "stocks_to_use": stmt.excluded.stocks_to_use,
                "world_production": stmt.excluded.world_production,
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


def run():
    """Main entry point — download PSD data, filter, compute, upsert."""
    start = datetime.utcnow()

    raw = fetch_psd_data()
    pivoted = filter_and_pivot(raw)
    wasde_rows = build_wasde_rows(pivoted)

    logger.info(f"  Prepared {len(wasde_rows)} WASDE rows for upsert")
    n = upsert_wasde(wasde_rows)

    log_ingest_summary(logger, "wasde_releases", n, start)


if __name__ == "__main__":
    run()
