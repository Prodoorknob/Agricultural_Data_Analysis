"""ETL: Ingest USDA WASDE supply/demand data from PSD Online CSV.

Schedule: Monthly, ~12th of month at 14:00 UTC (day after WASDE release).
Source: https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip (~15MB)
Target table: wasde_releases

Unit convention (2026-08-26 correction): PSD publishes quantities in 1000 MT;
we convert to MILLION BUSHELS at ingest so stored values match the numbers
USDA prints in the WASDE domestic balance sheets (corn ending stocks ~1,360,
not 34,551). stocks_to_use is a fraction: ending_stocks / (total_domestic_use
+ us_exports), i.e. the standard WASDE stocks-to-use definition.

History of the bug this replaces: TARGET_ATTRS asked for "Total Domestic
Cons.", which is not a PSD attribute name, and COMMODITY_MAP asked for
"Soybeans" where PSD says "Oilseed, Soybean". Both misses were silent:
`df.get("total_domestic_cons", 0)` zero-filled domestic use (so STU became
stocks / exports, ~6x too high) and soybean rows were never ingested at all.
Missing attributes and commodities now raise instead.

Usage:
    python -m backend.etl.ingest_wasde              # normal monthly upsert
    python -m backend.etl.ingest_wasde --backfill   # correct existing rows
                                                    # in place + fill missing
                                                    # (commodity, year) pairs
"""

import argparse
import io
import zipfile
from datetime import date, datetime

import pandas as pd
import requests
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary

logger = setup_logging("ingest_wasde")

WASDE_URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"

# Map PSD commodity names to our normalized names. These must match
# Commodity_Description verbatim (note: PSD calls soybeans "Oilseed, Soybean").
COMMODITY_MAP = {
    "Corn": "corn",
    "Oilseed, Soybean": "soybean",
    "Wheat": "wheat",
}

# PSD attribute names we need, verbatim from Attribute_Description.
# "Domestic Consumption" is PSD's total domestic use (feed + FSI for grains,
# crush + food + feed/waste for soybeans) — the WASDE "domestic use" line.
TARGET_ATTRS = {
    "Production",
    "Domestic Consumption",
    "Exports",
    "Ending Stocks",
}

# Bushels per metric ton (corn 56 lb/bu; soybeans and wheat 60 lb/bu).
# PSD values are 1000 MT; multiplying by BU_PER_MT / 1000 yields million bu.
BU_PER_MT = {
    "corn": 39.368,
    "soybean": 36.7437,
    "wheat": 36.7437,
}

# Columns that must exist after the pivot. A miss means a PSD attribute name
# changed upstream — fail loudly rather than silently zero-filling.
REQUIRED_COLS = {"us_production", "us_exports", "ending_stocks", "total_domestic_use"}

QUANTITY_COLS = ["us_production", "us_exports", "ending_stocks", "total_domestic_use"]


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
    """Filter PSD data to US corn/soy/wheat, pivot, convert to million bu."""

    # Filter to United States + target commodities + target attributes
    mask = (
        (df["Country_Name"] == "United States")
        & (df["Commodity_Description"].isin(COMMODITY_MAP.keys()))
        & (df["Attribute_Description"].isin(TARGET_ATTRS))
    )
    df = df[mask].copy()
    logger.info(f"  After filtering: {len(df)} rows")

    if df.empty:
        raise ValueError(
            "PSD filter matched 0 rows — Country/Commodity/Attribute names "
            "may have changed upstream"
        )

    # Normalize commodity name
    df["commodity"] = df["Commodity_Description"].map(COMMODITY_MAP)

    missing_commodities = set(COMMODITY_MAP.values()) - set(df["commodity"].unique())
    if missing_commodities:
        raise ValueError(
            f"PSD data missing commodities {sorted(missing_commodities)} — "
            "check COMMODITY_MAP against Commodity_Description"
        )

    # Build marketing year string: e.g. "2025/2026" -> "2025-2026"
    df["marketing_year"] = (
        df["Market_Year"].astype(str)
        + "-"
        + (df["Market_Year"].astype(int) + 1).astype(str)
    )

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
        "Domestic Consumption": "total_domestic_use",
    }
    pivot = pivot.rename(columns=col_renames)

    missing_cols = REQUIRED_COLS - set(pivot.columns)
    if missing_cols:
        raise ValueError(
            f"PSD pivot missing expected columns {sorted(missing_cols)} — "
            "an Attribute_Description string changed upstream"
        )

    # 1000 MT -> million bushels, per-commodity conversion factor.
    factors = pivot["commodity"].map(BU_PER_MT)
    for col in QUANTITY_COLS:
        pivot[col] = (pivot[col] * factors / 1000).round(2)

    return pivot


def compute_stocks_to_use(df: pd.DataFrame) -> pd.DataFrame:
    """Stocks-to-use ratio = ending_stocks / (domestic use + exports)."""
    if df.empty:
        return df

    # Deliberate KeyError if either column is absent — never zero-fill here.
    total_use = df["total_domestic_use"] + df["us_exports"]
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
            release_date = date(calendar_year, 12, 1)

        rows.append({
            "release_date": release_date,
            "commodity": row["commodity"],
            "marketing_year": row["marketing_year"],
            "us_production": row.get("us_production"),
            "us_exports": row.get("us_exports"),
            "ending_stocks": row.get("ending_stocks"),
            "total_domestic_use": row.get("total_domestic_use"),
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
                "total_domestic_use": stmt.excluded.total_domestic_use,
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


def backfill(pivot: pd.DataFrame) -> tuple[int, int]:
    """One-time correction of historical rows already in wasde_releases.

    The table accumulated rows under the old buggy ingest: STU computed as
    stocks / exports, values in 1000 MT, and no soybean rows at all. Two
    passes:

      1. In-place UPDATE of every existing row keyed by (commodity,
         marketing_year), across ALL release_date vintages. Vintage-specific
         PSD snapshots are unrecoverable, so all vintages of a marketing year
         converge on the current PSD values — which also means consecutive
         releases show a 0.0 STU delta and cannot fire a bogus "STU moved"
         signal off backfilled data. Real vintage deltas resume with the next
         monthly ingest.
      2. INSERT rows for (commodity, marketing_year) pairs with no row at
         all — this is what backfills soybean history.

    Returns (n_updated, n_inserted).
    """
    corrected = compute_stocks_to_use(pivot.copy())

    update_sql = text(
        """
        UPDATE wasde_releases
        SET us_production = :us_production,
            us_exports = :us_exports,
            ending_stocks = :ending_stocks,
            total_domestic_use = :total_domestic_use,
            stocks_to_use = :stocks_to_use
        WHERE commodity = :commodity AND marketing_year = :marketing_year
        """
    )

    n_updated = 0
    existing_pairs: set[tuple[str, str]] = set()
    session = get_sync_session()
    try:
        for r in session.execute(
            text("SELECT DISTINCT commodity, marketing_year FROM wasde_releases")
        ).all():
            existing_pairs.add((r.commodity, r.marketing_year))

        for _, row in corrected.iterrows():
            key = (row["commodity"], row["marketing_year"])
            if key not in existing_pairs:
                continue
            result = session.execute(
                update_sql,
                {
                    "commodity": row["commodity"],
                    "marketing_year": row["marketing_year"],
                    "us_production": _num_or_none(row["us_production"]),
                    "us_exports": _num_or_none(row["us_exports"]),
                    "ending_stocks": _num_or_none(row["ending_stocks"]),
                    "total_domestic_use": _num_or_none(row["total_domestic_use"]),
                    "stocks_to_use": _num_or_none(row["stocks_to_use"]),
                },
            )
            n_updated += result.rowcount
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    missing = pivot[
        ~pivot.apply(
            lambda r: (r["commodity"], r["marketing_year"]) in existing_pairs, axis=1
        )
    ]
    insert_rows = build_wasde_rows(missing)
    n_inserted = upsert_wasde(insert_rows)

    logger.info(
        f"  Backfill: {n_updated} existing rows corrected in place, "
        f"{n_inserted} missing (commodity, marketing_year) rows inserted"
    )
    return n_updated, n_inserted


def _num_or_none(v):
    return None if pd.isna(v) else float(v)


def run(do_backfill: bool = False):
    """Main entry point — download PSD data, filter, compute, upsert."""
    start = datetime.utcnow()

    raw = fetch_psd_data()
    pivoted = filter_and_pivot(raw)

    if do_backfill:
        n_updated, n_inserted = backfill(pivoted)
        log_ingest_summary(logger, "wasde_releases", n_updated + n_inserted, start)
        return

    wasde_rows = build_wasde_rows(pivoted)
    logger.info(f"  Prepared {len(wasde_rows)} WASDE rows for upsert")
    n = upsert_wasde(wasde_rows)

    log_ingest_summary(logger, "wasde_releases", n, start)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest USDA WASDE data from PSD.")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Correct existing rows in place (units + STU definition) and "
        "insert missing commodity/year pairs, instead of the normal upsert.",
    )
    args = parser.parse_args()
    run(do_backfill=args.backfill)
