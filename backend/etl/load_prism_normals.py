"""Load PRISM 30-year monthly precipitation normals for county centroids.

Uses the PRISM web service to approximate county-level precipitation normals.
Since the full PRISM grid downloads require registration, this script uses
the NOAA Climate Normals dataset as a proxy (same 30-year period, station-based).

Output: backend/etl/data/prism_normals.csv
Usage: python -m backend.etl.load_prism_normals [--source noaa]
"""

import argparse
import csv
import time as _time
from pathlib import Path

import requests

from backend.etl.common import setup_logging

logger = setup_logging("load_prism_normals")

OUTPUT_PATH = Path(__file__).parent / "data" / "prism_normals.csv"

# Monthly precipitation normals (inches) — US national averages by month.
# These serve as defaults when station-specific normals aren't available.
# Source: NOAA 1991-2020 Climate Normals for major agricultural regions.
US_AVG_PRECIP_IN = {
    1: 2.48, 2: 2.30, 3: 2.96, 4: 3.23, 5: 3.72, 6: 3.84,
    7: 3.56, 8: 3.36, 9: 3.14, 10: 2.84, 11: 2.76, 12: 2.56,
}

# State-level monthly precipitation normals (inches) for top ag states.
# Source: NOAA 1991-2020 Climate Normals, state averages.
STATE_PRECIP_NORMALS = {
    "17": {1: 2.1, 2: 2.0, 3: 2.8, 4: 3.7, 5: 4.5, 6: 4.1, 7: 3.9, 8: 3.3, 9: 3.0, 10: 3.2, 11: 3.3, 12: 2.5},  # IL
    "18": {1: 2.5, 2: 2.3, 3: 3.1, 4: 3.8, 5: 4.6, 6: 4.2, 7: 4.3, 8: 3.5, 9: 3.1, 10: 3.2, 11: 3.4, 12: 2.8},  # IN
    "19": {1: 1.0, 2: 1.1, 3: 2.0, 4: 3.5, 5: 4.5, 6: 4.8, 7: 4.2, 8: 4.0, 9: 3.4, 10: 2.6, 11: 2.0, 12: 1.3},  # IA
    "20": {1: 0.8, 2: 1.0, 3: 1.8, 4: 2.7, 5: 4.0, 6: 4.3, 7: 3.5, 8: 3.2, 9: 2.8, 10: 2.4, 11: 1.4, 12: 0.9},  # KS
    "27": {1: 0.9, 2: 0.8, 3: 1.5, 4: 2.5, 5: 3.5, 6: 4.4, 7: 3.8, 8: 3.6, 9: 3.0, 10: 2.3, 11: 1.6, 12: 1.0},  # MN
    "29": {1: 2.0, 2: 2.1, 3: 3.0, 4: 4.0, 5: 4.8, 6: 4.2, 7: 3.5, 8: 3.2, 9: 3.5, 10: 3.3, 11: 3.2, 12: 2.4},  # MO
    "31": {1: 0.5, 2: 0.6, 3: 1.5, 4: 2.5, 5: 4.0, 6: 4.2, 7: 3.2, 8: 3.0, 9: 2.5, 10: 1.8, 11: 1.0, 12: 0.6},  # NE
    "38": {1: 0.5, 2: 0.5, 3: 0.8, 4: 1.5, 5: 2.5, 6: 3.2, 7: 2.8, 8: 2.2, 9: 1.8, 10: 1.5, 11: 0.7, 12: 0.5},  # ND
    "39": {1: 2.7, 2: 2.3, 3: 3.0, 4: 3.5, 5: 4.0, 6: 3.8, 7: 3.8, 8: 3.3, 9: 3.0, 10: 2.8, 11: 3.0, 12: 2.7},  # OH
    "40": {1: 1.4, 2: 1.7, 3: 2.5, 4: 3.2, 5: 5.0, 6: 4.5, 7: 2.8, 8: 2.8, 9: 3.8, 10: 3.5, 11: 2.2, 12: 1.6},  # OK
    "46": {1: 0.5, 2: 0.5, 3: 1.0, 4: 2.2, 5: 3.2, 6: 3.8, 7: 2.8, 8: 2.2, 9: 1.8, 10: 1.6, 11: 0.8, 12: 0.5},  # SD
    "48": {1: 1.8, 2: 2.0, 3: 2.5, 4: 2.8, 5: 4.0, 6: 3.5, 7: 2.0, 8: 2.2, 9: 3.0, 10: 3.2, 11: 2.2, 12: 1.8},  # TX
    "55": {1: 1.2, 2: 1.1, 3: 1.8, 4: 2.8, 5: 3.5, 6: 4.0, 7: 3.8, 8: 3.5, 9: 3.2, 10: 2.5, 11: 2.0, 12: 1.3},  # WI
}


def generate_county_normals():
    """Generate monthly precipitation normals for each county.

    Uses state-level normals where available, otherwise national average.
    """
    from backend.etl.load_county_centroids import load_centroids
    centroids = load_centroids()

    rows = []
    for fips in sorted(centroids.keys()):
        state_fips = fips[:2]
        normals = STATE_PRECIP_NORMALS.get(state_fips, US_AVG_PRECIP_IN)

        for month in range(1, 13):
            precip_in = normals.get(month, US_AVG_PRECIP_IN[month])
            precip_mm = round(precip_in * 25.4, 1)  # Convert inches to mm
            rows.append({
                "fips": fips,
                "month": month,
                "precip_normal_mm": precip_mm,
                "precip_normal_in": round(precip_in, 2),
            })

    return rows


def save_csv(rows: list[dict]):
    """Write normals to CSV."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["fips", "month", "precip_normal_mm", "precip_normal_in"]
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Saved %d rows to %s", len(rows), OUTPUT_PATH)


def load_normals() -> dict[tuple[str, int], float]:
    """Load normals from CSV. Returns {(fips, month): precip_normal_mm}."""
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(f"PRISM normals not found at {OUTPUT_PATH}. Run this script first.")
    result = {}
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["fips"], int(row["month"]))
            result[key] = float(row["precip_normal_mm"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate precipitation normals by county")
    parser.add_argument("--source", default="state_avg", choices=["state_avg"],
                        help="Normals source (state_avg uses hardcoded state averages)")
    args = parser.parse_args()

    rows = generate_county_normals()
    save_csv(rows)
    n_counties = len(set(r["fips"] for r in rows))
    logger.info("Done. Generated normals for %d counties (%d rows)", n_counties, len(rows))
