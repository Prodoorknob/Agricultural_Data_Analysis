"""USDA NASS QuickStats — county-level irrigated acres by crop (nationwide).

Ported from `aquifer-watch/aquiferwatch/pipeline/nass_crops.py`. The original
pulled 8 High Plains Aquifer states only; this version covers all 50 states +
DC so the Crops tab can show an "irrigated share" overlay nationwide.

Irrigation splits at county level exist only in CENSUS rows (every 5 years —
most recent are 2017 and 2022). Annual SURVEY rows don't carry the
prodn_practice_desc=IRRIGATED breakdown at county scale.

Output
------
    pipeline/output/enrichments/nass_irrigated_county.parquet
        fips · state · state_name · county_name · crop · year · irrigated_acres

Upload target
-------------
    s3://usda-analysis-datasets/enrichment/nass_irrigated_county.parquet

Usage
-----
    python -m pipeline.enrichments.nass_irrigated_county
    python -m pipeline.enrichments.nass_irrigated_county --upload-s3
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
PROCESSED_DIR = REPO_ROOT / "pipeline" / "output" / "enrichments"
OUTPUT = PROCESSED_DIR / "nass_irrigated_county.parquet"

API_URL = "https://quickstats.nass.usda.gov/api/api_GET/"

# All 50 states + DC. AK / HI / DC return empty for most row crops, which is
# fine — the endpoint 400s cleanly and we skip.
ALL_STATES = (
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM",
    "NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA",
    "WV","WI","WY",
)

CROPS = {
    "corn":     "CORN",
    "soybeans": "SOYBEANS",
    "sorghum":  "SORGHUM",
    "wheat":    "WHEAT",
    "cotton":   "COTTON",
    "rice":     "RICE",
    "alfalfa":  "HAY",     # alfalfa is reported under HAY with util IRRIGATED
}

CENSUS_YEARS = (2017, 2022)


def _api_key() -> str:
    key = os.environ.get("QUICKSTATS_API_KEY", "").strip()
    if not key:
        env = REPO_ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("QUICKSTATS_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        raise RuntimeError("QUICKSTATS_API_KEY not set (env or .env)")
    return key


def fetch_one(state: str, crop_label: str, commodity: str, year: int, api_key: str) -> pd.DataFrame:
    params = {
        "key": api_key,
        "source_desc": "CENSUS",
        "sector_desc": "CROPS",
        "commodity_desc": commodity,
        "statisticcat_desc": "AREA HARVESTED",
        "prodn_practice_desc": "IRRIGATED",
        "unit_desc": "ACRES",
        "agg_level_desc": "COUNTY",
        "year": year,
        "state_alpha": state,
        "format": "JSON",
    }
    r = requests.get(API_URL, params=params, timeout=60)
    if r.status_code == 400:
        return pd.DataFrame()  # no data for slice — normal
    r.raise_for_status()
    records = r.json().get("data", [])
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["crop"] = crop_label
    return df


def fetch_all() -> pd.DataFrame:
    key = _api_key()
    frames: list[pd.DataFrame] = []
    tasks = [(s, lbl, com, yr)
             for s in ALL_STATES
             for lbl, com in CROPS.items()
             for yr in CENSUS_YEARS]

    def _task(args):
        state, label, commodity, year = args
        try:
            df = fetch_one(state, label, commodity, year, key)
        except requests.exceptions.RequestException as e:
            log.warning("  [%s %s %d] network: %s", state, label, year, e)
            return None
        except Exception as e:
            log.warning("  [%s %s %d] failed: %s", state, label, year, e)
            return None
        if df.empty:
            return None
        log.info("  [%s %s %d] %d rows", state, label, year, len(df))
        return df

    with ThreadPoolExecutor(max_workers=6) as ex:
        for f in as_completed(ex.submit(_task, t) for t in tasks):
            result = f.result()
            if result is not None:
                frames.append(result)
            # respect NASS throttle: gentle 150ms between completed requests
            time.sleep(0.15)

    if not frames:
        log.warning("no NASS irrigated rows returned")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["irrigated_acres"] = pd.to_numeric(
        df["Value"].astype(str).str.replace(",", "", regex=False)
           .replace({"(D)": None, "(Z)": None, "(NA)": None}),
        errors="coerce",
    )
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["state_fips_code"] = df["state_fips_code"].astype(str).str.zfill(2)
    df["county_code"] = df["county_code"].astype(str).str.zfill(3)
    df["fips"] = df["state_fips_code"] + df["county_code"]
    out = df[[
        "fips", "state_alpha", "state_name", "county_name", "crop", "year", "irrigated_acres"
    ]].rename(columns={"state_alpha": "state"})
    out = out.dropna(subset=["irrigated_acres"])
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUTPUT, index=False)
    log.info("wrote %s  (%d rows, %d counties, %d crops)",
             OUTPUT, len(out), out["fips"].nunique(), out["crop"].nunique())
    return out


def upload_s3(path: Path) -> None:
    import boto3
    region = os.environ.get("AWS_REGION", "us-east-2")
    client = boto3.client("s3", region_name=region)
    key = "enrichment/nass_irrigated_county.parquet"
    bucket = "usda-analysis-datasets"
    log.info("uploading %s -> s3://%s/%s", path, bucket, key)
    client.upload_file(str(path), bucket, key, ExtraArgs={"ChecksumAlgorithm": "SHA256"})
    log.info("  ok — %d bytes", path.stat().st_size)


def main() -> None:
    p = argparse.ArgumentParser(description="NASS irrigated county acres (nationwide)")
    p.add_argument("--upload-s3", action="store_true", help="Upload the parquet to S3 after building")
    args = p.parse_args()
    fetch_all()
    if args.upload_s3 and OUTPUT.exists():
        upload_s3(OUTPUT)


if __name__ == "__main__":
    main()
