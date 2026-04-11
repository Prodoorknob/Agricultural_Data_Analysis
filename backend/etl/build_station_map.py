"""Build NOAA GHCN station-to-county FIPS mapping.

Downloads GHCN station inventory, computes Haversine distance to county centroids,
and selects the nearest station within 50km.

One-time script. Output: backend/etl/data/station_county_map.csv
Usage: python -m backend.etl.build_station_map [--max-distance-km 50]
"""

import argparse
import csv
import io
import math
from pathlib import Path

import numpy as np
import requests

from backend.etl.common import setup_logging
from backend.etl.load_county_centroids import load_centroids

logger = setup_logging("build_station_map")

GHCN_STATIONS_URL = "https://www1.ncdc.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt"
GHCN_INVENTORY_URL = "https://www1.ncdc.noaa.gov/pub/data/ghcn/daily/ghcnd-inventory.txt"
OUTPUT_PATH = Path(__file__).parent / "data" / "station_county_map.csv"

# Earth radius in km
R_EARTH = 6371.0


def haversine_vectorized(lat1: float, lon1: float, lats2: np.ndarray, lons2: np.ndarray) -> np.ndarray:
    """Vectorized Haversine distance from one point to many points. Returns km."""
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lats2_r = np.radians(lats2)
    lons2_r = np.radians(lons2)

    dlat = lats2_r - lat1_r
    dlon = lons2_r - lon1_r

    a = np.sin(dlat / 2) ** 2 + math.cos(lat1_r) * np.cos(lats2_r) * np.sin(dlon / 2) ** 2
    return R_EARTH * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def download_stations() -> list[dict]:
    """Download and parse GHCN station inventory (fixed-width format)."""
    logger.info("Downloading GHCN station inventory...")
    resp = requests.get(GHCN_STATIONS_URL, timeout=120)
    resp.raise_for_status()

    stations = []
    for line in resp.text.strip().split("\n"):
        if len(line) < 31:
            continue
        station_id = line[0:11].strip()
        lat = line[12:20].strip()
        lon = line[21:30].strip()

        # Only US stations (start with "US")
        if not station_id.startswith("US"):
            continue

        try:
            stations.append({
                "station_id": station_id,
                "lat": float(lat),
                "lon": float(lon),
            })
        except ValueError:
            continue

    logger.info("Parsed %d US GHCN stations", len(stations))
    return stations


def download_inventory() -> dict[str, set]:
    """Download GHCN inventory to check which stations have TMAX/TMIN/PRCP data.

    Returns {station_id: set of elements (TMAX, TMIN, PRCP)}.
    """
    logger.info("Downloading GHCN inventory for data completeness check...")
    resp = requests.get(GHCN_INVENTORY_URL, timeout=120)
    resp.raise_for_status()

    inventory: dict[str, set] = {}
    for line in resp.text.strip().split("\n"):
        if len(line) < 35:
            continue
        station_id = line[0:11].strip()
        element = line[31:35].strip()

        if station_id.startswith("US") and element in ("TMAX", "TMIN", "PRCP"):
            inventory.setdefault(station_id, set()).add(element)

    logger.info("Inventory covers %d US stations", len(inventory))
    return inventory


def build_mapping(max_distance_km: float = 50.0):
    """Build the FIPS -> nearest GHCN station mapping."""
    centroids = load_centroids()
    stations = download_stations()
    inventory = download_inventory()

    # Filter stations that have all 3 required elements
    complete_stations = [
        s for s in stations
        if inventory.get(s["station_id"], set()) >= {"TMAX", "TMIN", "PRCP"}
    ]
    logger.info("%d stations have TMAX+TMIN+PRCP data", len(complete_stations))

    # Build numpy arrays for vectorized distance computation
    s_lats = np.array([s["lat"] for s in complete_stations])
    s_lons = np.array([s["lon"] for s in complete_stations])
    s_ids = [s["station_id"] for s in complete_stations]

    results = []
    no_station_count = 0

    for fips, (lat, lon) in centroids.items():
        distances = haversine_vectorized(lat, lon, s_lats, s_lons)
        min_idx = np.argmin(distances)
        min_dist = distances[min_idx]

        if min_dist <= max_distance_km:
            results.append({
                "fips": fips,
                "station_id": s_ids[min_idx],
                "distance_km": round(float(min_dist), 2),
                "needs_nasa_fallback": False,
            })
        else:
            results.append({
                "fips": fips,
                "station_id": "",
                "distance_km": round(float(min_dist), 2),
                "needs_nasa_fallback": True,
            })
            no_station_count += 1

    logger.info(
        "Mapped %d counties: %d with stations, %d need NASA POWER fallback",
        len(results), len(results) - no_station_count, no_station_count,
    )
    return results


def save_csv(rows: list[dict]):
    """Write station mapping to CSV."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["fips", "station_id", "distance_km", "needs_nasa_fallback"]
        )
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Saved station mapping to %s", OUTPUT_PATH)


def load_station_map() -> dict[str, str]:
    """Load station mapping from CSV. Returns {fips: station_id} (empty string if NASA fallback)."""
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(f"Station map not found at {OUTPUT_PATH}. Run this script first.")
    result = {}
    with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row["fips"]] = row["station_id"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build NOAA station-to-county mapping")
    parser.add_argument("--max-distance-km", type=float, default=50.0, help="Max station distance (km)")
    args = parser.parse_args()

    rows = build_mapping(max_distance_km=args.max_distance_km)
    save_csv(rows)
    logger.info("Done. %d mappings written.", len(rows))
