"""Fetch state-level NASS acreage and yield data for 1990-2000.

Supplements the existing S3 parquet data (2001-2025) with older records
needed for acreage model training with a proper lookback window.

Usage:
    python pipeline/fetch_nass_historical.py
    python pipeline/fetch_nass_historical.py --year-start 1985 --year-end 2000

Output:
    backend/etl/data/nass_cache/nass_historical_1990_2000.csv
"""

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd

# Add project root so we can import from pipeline
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from quickstats_ingest import (
    api_get_data,
    clean_nass_value,
    get_api_key,
    logger,
    REQUEST_DELAY_SECONDS,
)

# State alpha to FIPS mapping
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
}

COMMODITIES = {
    "CORN": "corn",
    "SOYBEANS": "soybean",
    "WHEAT": "wheat",
}

OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "backend", "etl", "data", "nass_cache", "nass_historical_1990_2000.csv",
)


def fetch_commodity_stat(
    api_key: str,
    commodity: str,
    stat_cat: str,
    unit: str,
    year_start: int,
    year_end: int,
) -> list[dict]:
    """Fetch state-level records for one commodity/stat/unit combo."""
    all_records = []
    for year in range(year_start, year_end + 1):
        params = {
            "source_desc": "SURVEY",
            "sector_desc": "CROPS",
            "commodity_desc": commodity,
            "class_desc": "ALL CLASSES",
            "statisticcat_desc": stat_cat,
            "unit_desc": unit,
            "domain_desc": "TOTAL",
            "prodn_practice_desc": "ALL PRODUCTION PRACTICES",
            "agg_level_desc": "STATE",
            "freq_desc": "ANNUAL",
            "reference_period_desc": "YEAR",
            "year": str(year),
        }
        records = api_get_data(api_key, params)
        all_records.extend(records)
        logger.info(f"  {commodity} {stat_cat} {year}: {len(records)} records")
        time.sleep(REQUEST_DELAY_SECONDS)

    return all_records


def main():
    parser = argparse.ArgumentParser(description="Fetch historical NASS data (1990-2000)")
    parser.add_argument("--year-start", type=int, default=1990)
    parser.add_argument("--year-end", type=int, default=2000)
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

    # Also check the QUICKSTATS_API_KEY name used in .env
    if not os.environ.get("USDA_QUICKSTATS_API_KEY"):
        key = os.environ.get("QUICKSTATS_API_KEY", "")
        if key:
            os.environ["USDA_QUICKSTATS_API_KEY"] = key

    api_key = get_api_key()
    logger.info(f"Fetching NASS state-level data for {args.year_start}-{args.year_end}")

    all_records = []

    for nass_commodity, our_commodity in COMMODITIES.items():
        logger.info(f"=== {nass_commodity} ===")

        # Area planted
        planted_records = fetch_commodity_stat(
            api_key, nass_commodity, "AREA PLANTED", "ACRES",
            args.year_start, args.year_end,
        )

        # Yield (BU / ACRE)
        yield_records = fetch_commodity_stat(
            api_key, nass_commodity, "YIELD", "BU / ACRE",
            args.year_start, args.year_end,
        )

        # Process planted
        for r in planted_records:
            state_alpha = r.get("state_alpha", "")
            fips = STATE_ALPHA_TO_FIPS.get(state_alpha)
            if not fips:
                continue
            val = clean_nass_value(r.get("Value"))
            if val is None or np.isnan(val):
                continue
            all_records.append({
                "state_fips": fips,
                "commodity": our_commodity,
                "year": int(r.get("year", 0)),
                "acres_planted": val,
                "yield_bu": np.nan,  # will be filled by merge
                "_type": "planted",
            })

        # Process yield
        for r in yield_records:
            state_alpha = r.get("state_alpha", "")
            fips = STATE_ALPHA_TO_FIPS.get(state_alpha)
            if not fips:
                continue
            val = clean_nass_value(r.get("Value"))
            if val is None or np.isnan(val):
                continue
            all_records.append({
                "state_fips": fips,
                "commodity": our_commodity,
                "year": int(r.get("year", 0)),
                "acres_planted": np.nan,  # will be filled by merge
                "yield_bu": val,
                "_type": "yield",
            })

    if not all_records:
        logger.error("No records fetched!")
        return

    df = pd.DataFrame(all_records)

    # Merge planted + yield on (state_fips, commodity, year)
    planted = df[df["_type"] == "planted"][["state_fips", "commodity", "year", "acres_planted"]]
    yields = df[df["_type"] == "yield"][["state_fips", "commodity", "year", "yield_bu"]]

    merged = planted.merge(yields, on=["state_fips", "commodity", "year"], how="outer")

    # Keep yield-only rows: the acreage model training uses prior-year yield as
    # a feature, so dropping state-years where NASS has yield but no planted
    # response removes signal. Previously `dropna(subset=["acres_planted"])`
    # silently discarded 15-20% of the training matrix.
    merged = merged[
        (merged["acres_planted"].isna() | (merged["acres_planted"] > 0))
        & ~(merged["acres_planted"].isna() & merged["yield_bu"].isna())
    ]

    merged = merged.drop_duplicates(subset=["state_fips", "commodity", "year"])

    n_both = int((merged["acres_planted"].notna() & merged["yield_bu"].notna()).sum())
    n_yield_only = int((merged["acres_planted"].isna() & merged["yield_bu"].notna()).sum())
    n_planted_only = int((merged["acres_planted"].notna() & merged["yield_bu"].isna()).sum())
    logger.info(
        "Historical merge retention: %d both, %d yield-only (kept), %d planted-only (kept)",
        n_both, n_yield_only, n_planted_only,
    )

    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    merged.to_csv(OUTPUT_PATH, index=False)
    logger.info(
        f"Saved {len(merged)} records to {OUTPUT_PATH} "
        f"({merged['year'].min()}-{merged['year'].max()}, "
        f"{merged['state_fips'].nunique()} states, "
        f"{merged['commodity'].nunique()} commodities)"
    )


if __name__ == "__main__":
    main()
