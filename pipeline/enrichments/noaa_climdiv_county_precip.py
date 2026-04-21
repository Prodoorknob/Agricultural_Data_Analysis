"""NOAA nClimDiv county precipitation — nationwide.

Ported from `aquifer-watch/aquiferwatch/pipeline/noaa_climdiv.py`. The original
filtered to the 8 High Plains Aquifer states; this version covers all 50
states + DC so the Crops tab can render a county-level precipitation
anomaly for any state selection.

Pulls NCEI's per-county monthly precipitation file (one flat ASCII file
covering 1895–present, no API key). Produces a single parquet with
1991–2020 normal, 2019–2023 recent, and the anomaly percentage.

File format (fixed-width per NCEI docs):
    cols 1-2   NCDC state code (NOT Census FIPS — lookup below)
    cols 3-5   county code
    cols 6-7   element code ('01' = precipitation)
    cols 8-11  year
    cols 12..  12 monthly values (inches, missing = -9.99)

Output
------
    pipeline/output/enrichments/noaa_county_precip.parquet
        fips · precip_normal_mm_yr · precip_recent_mm_yr · precip_anomaly_pct

Upload target
-------------
    s3://usda-analysis-datasets/enrichment/county_precip.parquet

Usage
-----
    python -m pipeline.enrichments.noaa_climdiv_county_precip
    python -m pipeline.enrichments.noaa_climdiv_county_precip --upload-s3
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "pipeline" / "output" / "enrichments" / "raw" / "noaa_climdiv"
PROCESSED_DIR = REPO_ROOT / "pipeline" / "output" / "enrichments"
OUTPUT = PROCESSED_DIR / "noaa_county_precip.parquet"

INDEX_URL = "https://www.ncei.noaa.gov/pub/data/cirs/climdiv/"

# NCDC climdiv state codes → Census state FIPS. NCDC uses a non-standard
# sequential numbering (01 Alabama, 02 Arizona, 03 Arkansas, ...). Compiled
# from the NCEI State-Code-Mapping documentation + cross-checked against the
# file contents.
NCDC_TO_FIPS = {
    "01": "01",  # Alabama
    "02": "04",  # Arizona
    "03": "05",  # Arkansas
    "04": "06",  # California
    "05": "08",  # Colorado
    "06": "09",  # Connecticut
    "07": "10",  # Delaware
    "08": "12",  # Florida
    "09": "13",  # Georgia
    "10": "16",  # Idaho
    "11": "17",  # Illinois
    "12": "18",  # Indiana
    "13": "19",  # Iowa
    "14": "20",  # Kansas
    "15": "21",  # Kentucky
    "16": "22",  # Louisiana
    "17": "23",  # Maine
    "18": "24",  # Maryland
    "19": "25",  # Massachusetts
    "20": "26",  # Michigan
    "21": "27",  # Minnesota
    "22": "28",  # Mississippi
    "23": "29",  # Missouri
    "24": "30",  # Montana
    "25": "31",  # Nebraska
    "26": "32",  # Nevada
    "27": "33",  # New Hampshire
    "28": "34",  # New Jersey
    "29": "35",  # New Mexico
    "30": "36",  # New York
    "31": "37",  # North Carolina
    "32": "38",  # North Dakota
    "33": "39",  # Ohio
    "34": "40",  # Oklahoma
    "35": "41",  # Oregon
    "36": "42",  # Pennsylvania
    "37": "44",  # Rhode Island
    "38": "45",  # South Carolina
    "39": "46",  # South Dakota
    "40": "47",  # Tennessee
    "41": "48",  # Texas
    "42": "49",  # Utah
    "43": "50",  # Vermont
    "44": "51",  # Virginia
    "45": "53",  # Washington
    "46": "54",  # West Virginia
    "47": "55",  # Wisconsin
    "48": "56",  # Wyoming
    "50": "02",  # Alaska
    "51": "15",  # Hawaii
}

NORMAL_START, NORMAL_END = 1991, 2020
RECENT_START, RECENT_END = 2019, 2023


def _latest_file_url() -> str:
    """Find the latest climdiv-pcpncy-* filename in the NCEI directory listing."""
    r = requests.get(INDEX_URL, timeout=60)
    r.raise_for_status()
    matches = re.findall(r"(climdiv-pcpncy-v[\d.]+-\d{8})", r.text)
    if not matches:
        raise RuntimeError("couldn't find climdiv-pcpncy in NCEI listing")
    return INDEX_URL + sorted(set(matches))[-1]


def _download(url: str) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    dst = RAW_DIR / url.rsplit("/", 1)[-1]
    if dst.exists():
        log.info("  using cached %s (%.1f MB)", dst.name, dst.stat().st_size / 1024 / 1024)
        return dst
    log.info("  downloading %s", url)
    r = requests.get(url, timeout=300, stream=True)
    r.raise_for_status()
    dst.write_bytes(r.content)
    log.info("  wrote %s (%.1f MB)", dst, dst.stat().st_size / 1024 / 1024)
    return dst


def _parse_climdiv(path: Path) -> pd.DataFrame:
    """Parse the climdiv file into tidy (fips, year, annual_mm) for every US county."""
    rows: list[dict] = []
    skipped_state_codes: set[str] = set()
    with open(path, "r") as f:
        for line in f:
            if len(line) < 90:
                continue
            header = line[:11]
            rest = line[11:].split()
            if len(rest) < 12:
                continue
            ncdc_state = header[0:2]
            county_code = header[2:5]
            element = header[5:7]
            year_s = header[7:11]
            if element != "01":
                continue
            try:
                year = int(year_s)
            except ValueError:
                continue
            if ncdc_state not in NCDC_TO_FIPS:
                skipped_state_codes.add(ncdc_state)
                continue
            fips = NCDC_TO_FIPS[ncdc_state] + county_code
            try:
                months = [float(v) for v in rest[:12]]
            except ValueError:
                continue
            # NCEI pcpncy reports inches to 2 decimals; missing = -9.99.
            valid = [m for m in months if m > -9.0]
            if len(valid) < 12:
                continue
            annual_in = sum(months)
            annual_mm = annual_in * 25.4
            rows.append({"fips": fips, "year": year, "annual_mm": annual_mm})
    if skipped_state_codes:
        log.info("  skipped NCDC state codes not in our FIPS map: %s",
                 sorted(skipped_state_codes))
    return pd.DataFrame(rows)


def build() -> pd.DataFrame:
    url = _latest_file_url()
    path = _download(url)
    panel = _parse_climdiv(path)
    log.info("  parsed %d (fips, year) rows across %d counties, years %d–%d",
             len(panel), panel["fips"].nunique(),
             int(panel["year"].min()), int(panel["year"].max()))

    normal = (
        panel[(panel["year"] >= NORMAL_START) & (panel["year"] <= NORMAL_END)]
        .groupby("fips")["annual_mm"].mean().rename("precip_normal_mm_yr")
    )
    recent = (
        panel[(panel["year"] >= RECENT_START) & (panel["year"] <= RECENT_END)]
        .groupby("fips")["annual_mm"].mean().rename("precip_recent_mm_yr")
    )
    out = pd.concat([normal, recent], axis=1).reset_index()
    out["precip_anomaly_pct"] = np.where(
        out["precip_normal_mm_yr"] > 0,
        (out["precip_recent_mm_yr"] - out["precip_normal_mm_yr"])
        / out["precip_normal_mm_yr"] * 100,
        np.nan,
    )
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUTPUT, index=False)
    log.info("wrote %s  (%d counties, normal median=%.0f mm/yr, recent median=%.0f mm/yr)",
             OUTPUT, len(out),
             out["precip_normal_mm_yr"].median(),
             out["precip_recent_mm_yr"].median())
    return out


def upload_s3(path: Path) -> None:
    """Upload the parquet to s3://usda-analysis-datasets/enrichment/county_precip.parquet."""
    import boto3  # imported late so non-upload runs don't require boto3

    region = os.environ.get("AWS_REGION", "us-east-2")
    client = boto3.client("s3", region_name=region)
    key = "enrichment/county_precip.parquet"
    bucket = "usda-analysis-datasets"
    log.info("uploading %s -> s3://%s/%s", path, bucket, key)
    client.upload_file(str(path), bucket, key, ExtraArgs={"ChecksumAlgorithm": "SHA256"})
    log.info("  ok — %d bytes", path.stat().st_size)


def main() -> None:
    p = argparse.ArgumentParser(description="NOAA nClimDiv county precipitation (nationwide)")
    p.add_argument("--upload-s3", action="store_true", help="Upload the parquet to S3 after building")
    args = p.parse_args()
    out_df = build()
    if args.upload_s3:
        upload_s3(OUTPUT)


if __name__ == "__main__":
    main()
