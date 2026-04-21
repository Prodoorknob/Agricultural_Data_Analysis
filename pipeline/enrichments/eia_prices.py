"""EIA industrial-sector electricity prices — per-state ¢/kWh (nationwide).

Ported from `aquifer-watch/aquiferwatch/pipeline/eia_prices.py`. Expanded to
all 50 states + DC. Writes JSON for direct frontend fetch.

Strategy
--------
- If `EIA_API_KEY` is set, pull monthly industrial prices 2020+ via API v2
  and report the trailing-12-month mean per state.
- Otherwise fall back to the published 2024 State Electricity Profile values
  (Table 8, https://www.eia.gov/electricity/state/). These are stable
  enough for UI contextualization — industrial rates move ~5% YoY.

Output
------
    web_app/public/enrichments/eia_state_prices.json
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_PUBLIC_DIR = REPO_ROOT / "web_app" / "public" / "enrichments"
OUTPUT_JSON = WEB_PUBLIC_DIR / "eia_state_prices.json"

ALL_STATES = (
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM",
    "NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA",
    "WV","WI","WY",
)

# 2024 annual average industrial electricity price (cents/kWh) by state.
# Source: EIA State Electricity Profiles 2024, Table 8 — https://www.eia.gov/electricity/state/
# Used as the fallback when no EIA_API_KEY is set.
STATIC_2024_PRICES: dict[str, float] = {
    "AL": 7.58, "AK": 19.48, "AZ": 7.53, "AR": 7.34, "CA": 17.52, "CO": 9.06,
    "CT": 13.64, "DE": 9.10, "DC": 14.96, "FL": 8.54, "GA": 7.18, "HI": 24.10,
    "ID": 7.72, "IL": 8.50, "IN": 8.37, "IA": 6.58, "KS": 9.21, "KY": 7.76,
    "LA": 7.12, "ME": 11.59, "MD": 10.12, "MA": 16.26, "MI": 8.63, "MN": 8.68,
    "MS": 7.85, "MO": 8.24, "MT": 6.40, "NE": 7.97, "NV": 7.75, "NH": 13.99,
    "NJ": 12.47, "NM": 7.44, "NY": 9.56, "NC": 7.31, "ND": 7.18, "OH": 7.71,
    "OK": 6.61, "OR": 7.40, "PA": 8.24, "RI": 14.95, "SC": 7.50, "SD": 7.27,
    "TN": 7.78, "TX": 6.48, "UT": 6.57, "VT": 11.00, "VA": 7.87, "WA": 6.86,
    "WV": 7.72, "WI": 8.43, "WY": 6.93,
}

API_URL = "https://api.eia.gov/v2/electricity/retail-sales/data/"


def _fetch_from_api(api_key: str) -> list[dict]:
    params: list[tuple[str, str]] = [
        ("api_key", api_key),
        ("frequency", "monthly"),
        ("data[0]", "price"),
        ("facets[sectorid][]", "IND"),
        ("start", "2023-01"),
        ("end", "2025-12"),
        ("length", "5000"),
        ("sort[0][column]", "period"),
        ("sort[0][direction]", "asc"),
    ]
    for s in ALL_STATES:
        params.append(("facets[stateid][]", s))
    r = requests.get(API_URL, params=params, timeout=60)
    r.raise_for_status()
    j = r.json()
    rows = j.get("response", {}).get("data", [])
    if not rows:
        raise RuntimeError("EIA returned no rows — check filters / key")
    df = pd.DataFrame(rows)
    df["period"] = pd.to_datetime(df["period"])
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    latest_year = df["period"].max().year
    recent = df[df["period"] >= f"{latest_year - 1}-01"]
    grouped = (
        recent.groupby("stateid")["price"].mean().reset_index()
        .rename(columns={"stateid": "state", "price": "cents_per_kwh"})
    )
    return [
        {"state": r["state"], "cents_per_kwh": round(float(r["cents_per_kwh"]), 2),
         "year": int(latest_year), "source": "eia_api_v2_industrial_trailing12"}
        for _, r in grouped.iterrows()
    ]


def _static_fallback() -> list[dict]:
    return [
        {"state": s, "cents_per_kwh": v, "year": 2024,
         "source": "eia_state_profiles_2024_static"}
        for s, v in sorted(STATIC_2024_PRICES.items())
    ]


def build() -> list[dict]:
    key = os.environ.get("EIA_API_KEY", "").strip()
    if key:
        try:
            log.info("fetching EIA API (industrial monthly, all states)…")
            rows = _fetch_from_api(key)
            log.info("  got %d states from API", len(rows))
        except Exception as e:
            log.warning("  EIA API failed (%s) — using static fallback", e)
            rows = _static_fallback()
    else:
        log.info("EIA_API_KEY not set — using published 2024 static values")
        rows = _static_fallback()

    WEB_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump({"dataset": "eia_state_prices", "rows": rows}, f, indent=2)
    avg = sum(r["cents_per_kwh"] for r in rows) / len(rows) if rows else 0
    log.info("wrote %s  (%d states, mean=%.2f ¢/kWh)", OUTPUT_JSON, len(rows), avg)
    return rows


def main() -> None:
    argparse.ArgumentParser(description="EIA state industrial electricity prices").parse_args()
    build()


if __name__ == "__main__":
    main()
