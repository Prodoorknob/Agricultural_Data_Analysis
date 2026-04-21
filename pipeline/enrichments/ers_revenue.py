"""USDA ERS — commodity costs and returns (national gross revenue per acre).

Ported from `aquifer-watch/aquiferwatch/pipeline/ers_budgets.py`. Produces a
single tiny JSON the frontend reads directly.

Outputs
-------
    web_app/public/enrichments/ers_revenue_per_acre.json
        [{ crop, year, gross_value_usd_per_acre, source_file }, ...]

Usage
-----
    python -m pipeline.enrichments.ers_revenue
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from io import BytesIO
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
RAW_DIR = REPO_ROOT / "pipeline" / "output" / "enrichments" / "raw" / "ers"
WEB_PUBLIC_DIR = REPO_ROOT / "web_app" / "public" / "enrichments"
OUTPUT_JSON = WEB_PUBLIC_DIR / "ers_revenue_per_acre.json"

BASE = "https://www.ers.usda.gov/media"
FILES: dict[str, str] = {
    "corn":     f"{BASE}/4961/corn.xlsx",
    "cotton":   f"{BASE}/4963/cotton.xlsx",
    "sorghum":  f"{BASE}/4971/sorghum.xlsx",
    "soybeans": f"{BASE}/4975/soybeans.xlsx",
    "wheat":    f"{BASE}/4977/wheat.xlsx",
}


def _download(crop: str, url: str) -> bytes:
    cache = RAW_DIR / f"{crop}.xlsx"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 1000:
        return cache.read_bytes()
    r = requests.get(url, timeout=60, headers={"User-Agent": "AgDA-ERS/0.1"})
    r.raise_for_status()
    cache.write_bytes(r.content)
    return r.content


def _extract_gross_value(xlsx_bytes: bytes, crop: str) -> tuple[int | None, float | None]:
    df = pd.read_excel(BytesIO(xlsx_bytes), sheet_name="Data sheet (machine readable)")
    sub = df[
        (df["Category"].astype(str).str.strip() == "Gross value of production")
        & (df["Region"].astype(str).str.strip() == "U.S. total")
    ]
    totals = sub[sub["Item"].astype(str).str.contains("Total", case=False, na=False)]
    target = totals if not totals.empty else sub
    target = target.dropna(subset=["Year", "Value"])
    target["Year"] = pd.to_numeric(target["Year"], errors="coerce")
    target["Value"] = pd.to_numeric(target["Value"], errors="coerce")
    target = target.dropna(subset=["Year", "Value"])
    if target.empty:
        log.warning("  [%s] no Gross value rows after filtering", crop)
        return None, None
    latest = target.sort_values("Year").iloc[-1]
    return int(latest["Year"]), float(latest["Value"])


def fetch_all() -> list[dict]:
    rows: list[dict] = []
    for crop, url in FILES.items():
        try:
            content = _download(crop, url)
            year, value = _extract_gross_value(content, crop)
        except Exception as e:
            log.warning("  [%s] failed: %s", crop, e)
            continue
        if year is None or value is None:
            continue
        log.info("  [%s] %d: $%.0f/acre gross", crop, year, value)
        rows.append({
            "crop": crop,
            "year": year,
            "gross_value_usd_per_acre": round(value, 2),
            "source_file": url.rsplit("/", 1)[1],
        })
    WEB_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump({"dataset": "ers_revenue_per_acre", "rows": rows}, f, indent=2)
    log.info("wrote %s (%d crops)", OUTPUT_JSON, len(rows))
    return rows


def main() -> None:
    argparse.ArgumentParser(description="USDA ERS $/acre gross revenue").parse_args()
    fetch_all()


if __name__ == "__main__":
    main()
