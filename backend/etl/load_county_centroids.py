"""Download US Census Gazetteer file and extract county FIPS centroids.

One-time script. Output: backend/etl/data/county_centroids.csv
Usage: python -m backend.etl.load_county_centroids
"""

import csv
import io
import os
from pathlib import Path

import requests

from backend.etl.common import setup_logging

logger = setup_logging("load_county_centroids")

GAZETTEER_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
    "2024_Gaz_counties_national.zip"
)
OUTPUT_PATH = Path(__file__).parent / "data" / "county_centroids.csv"


def download_and_parse():
    """Download Census Gazetteer ZIP file, parse county centroids."""
    import zipfile

    logger.info("Downloading Census Gazetteer from %s", GAZETTEER_URL)
    resp = requests.get(GAZETTEER_URL, timeout=60)
    resp.raise_for_status()

    # Extract the text file from the ZIP
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    txt_name = [n for n in z.namelist() if n.endswith(".txt")][0]
    logger.info("Extracting %s from ZIP", txt_name)
    txt_content = z.read(txt_name).decode("utf-8")

    rows = []
    reader = csv.DictReader(io.StringIO(txt_content), delimiter="\t")
    for row in reader:
        # Strip whitespace from keys and values (Census files have trailing spaces)
        row = {k.strip(): v.strip() for k, v in row.items()}

        geoid = row.get("GEOID", "")
        if not geoid or len(geoid) != 5:
            continue

        lat = row.get("INTPTLAT", "")
        lon = row.get("INTPTLONG", "")
        name = row.get("NAME", "")
        state_fips = geoid[:2]

        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (ValueError, TypeError):
            logger.warning("Skipping FIPS %s — invalid lat/lon: %s, %s", geoid, lat, lon)
            continue

        # Continental US filter (exclude territories, AK, HI for crop yield purposes)
        # Keep AK (02) and HI (15) in the file but they'll be filtered at model time
        rows.append({
            "fips": geoid,
            "lat": round(lat_f, 6),
            "lon": round(lon_f, 6),
            "state_fips": state_fips,
            "county_name": name,
        })

    logger.info("Parsed %d county centroids", len(rows))
    return rows


def save_csv(rows: list[dict]):
    """Write county centroids to CSV."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["fips", "lat", "lon", "state_fips", "county_name"])
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Saved %d rows to %s", len(rows), OUTPUT_PATH)


def load_centroids() -> dict[str, tuple[float, float]]:
    """Load county centroids from CSV. Returns {fips: (lat, lon)}."""
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(f"County centroids not found at {OUTPUT_PATH}. Run this script first.")
    result = {}
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row["fips"]] = (float(row["lat"]), float(row["lon"]))
    return result


if __name__ == "__main__":
    rows = download_and_parse()
    save_csv(rows)
    logger.info("Done. %d counties written to %s", len(rows), OUTPUT_PATH)
