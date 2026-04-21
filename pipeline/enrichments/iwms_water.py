"""USDA IWMS 2023 — water-applied-per-acre by crop and state (nationwide).

Ported from `aquifer-watch/aquiferwatch/pipeline/iwms_water.py`. Expanded to
all 50 states. Small output (~300 rows) — we write both parquet AND JSON so
the frontend can drop the JSON into `web_app/public/enrichments/` for direct
static fetch without a parquet-decode step.

Source: NASS QuickStats API, CENSUS 2023 Irrigation & Water Management Survey,
`statisticcat_desc=WATER APPLIED` + `unit_desc=ACRE FEET / ACRE`.

Outputs
-------
    pipeline/output/enrichments/iwms_water_per_acre.parquet
    web_app/public/enrichments/iwms_water_per_acre.json

Usage
-----
    python -m pipeline.enrichments.iwms_water
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import requests

from pipeline.enrichments.nass_irrigated_county import (
    ALL_STATES, CROPS, _api_key
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "pipeline" / "output" / "enrichments"
WEB_PUBLIC_DIR = REPO_ROOT / "web_app" / "public" / "enrichments"
OUTPUT_PARQUET = PROCESSED_DIR / "iwms_water_per_acre.parquet"
OUTPUT_JSON = WEB_PUBLIC_DIR / "iwms_water_per_acre.json"

API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"


def fetch_one(state: str, crop_label: str, commodity: str, year: int, api_key: str) -> pd.DataFrame:
    params = {
        "key": api_key,
        "source_desc": "CENSUS",
        "sector_desc": "CROPS",
        "commodity_desc": commodity,
        "statisticcat_desc": "WATER APPLIED",
        "unit_desc": "ACRE FEET / ACRE",
        "agg_level_desc": "STATE",
        "year": year,
        "state_alpha": state,
        "format": "JSON",
    }
    r = requests.get(API_URL, params=params, timeout=60)
    if r.status_code == 400:
        return pd.DataFrame()
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["crop"] = crop_label
    return df


def fetch_all(year: int = 2023) -> pd.DataFrame:
    key = _api_key()
    frames: list[pd.DataFrame] = []
    for state in ALL_STATES:
        for crop_label, commodity in CROPS.items():
            try:
                df = fetch_one(state, crop_label, commodity, year, key)
            except Exception as e:
                log.warning("  [%s %s %d] failed: %s", state, crop_label, year, e)
                continue
            if not df.empty:
                frames.append(df)
                log.info("  [%s %s %d] %d rows", state, crop_label, year, len(df))
    if not frames:
        log.warning("no IWMS data returned")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["acre_feet_per_acre"] = pd.to_numeric(
        df["Value"].astype(str).str.replace(",", "", regex=False)
           .replace({"(D)": None, "(Z)": None, "(NA)": None}),
        errors="coerce",
    )
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    out = df[["state_alpha", "state_name", "crop", "year", "acre_feet_per_acre"]].rename(
        columns={"state_alpha": "state"}
    ).dropna(subset=["acre_feet_per_acre"])

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    WEB_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUTPUT_PARQUET, index=False)
    out_records = out.to_dict(orient="records")
    # cast Int64 year to int for JSON
    for r in out_records:
        if pd.notna(r.get("year")):
            r["year"] = int(r["year"])
    with open(OUTPUT_JSON, "w") as f:
        json.dump({"dataset": "iwms_water_per_acre", "year": year, "rows": out_records}, f, indent=2)
    log.info("wrote %s (%d rows) + %s", OUTPUT_PARQUET, len(out), OUTPUT_JSON)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="USDA IWMS water-applied per acre (nationwide)")
    p.add_argument("--year", type=int, default=2023)
    args = p.parse_args()
    fetch_all(args.year)


if __name__ == "__main__":
    main()
