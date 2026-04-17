"""
build_county_aggregates.py — Per-state county-level aggregates for the Overview
map's drill-down mode.

When a user clicks a state on the Overview choropleth, the frontend needs to
re-render as a county-level map inside that state. Loading the raw
partitioned_states_counties/{STATE}.parquet (~200KB, 18K rows) works but the
frontend has to apply the same canonical-row filtering we now do in B3.
Pre-aggregating once here keeps the client hot-path simple.

Input:
  survey_datasets/partitioned_states_counties/{STATE}.parquet

Output (per state):
  survey_datasets/overview/county_metrics/{STATE}.parquet
  One row per (year, fips, commodity_desc):
    county_name, area_harvested_acres, area_planted_acres, production,
    production_unit, yield_value, yield_unit

Usage:
    python -m pipeline.build_county_aggregates                     # local only
    python -m pipeline.build_county_aggregates --upload            # push to S3
    python -m pipeline.build_county_aggregates --states IN,IA
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd

_THIS_DIR = Path(__file__).resolve().parent
OUT_DIR = _THIS_DIR / "output_overview" / "county_metrics"
CACHE_DIR = _THIS_DIR / "output_counties_cached"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("county_agg")

S3_BUCKET = "usda-analysis-datasets"
COUNTY_INPUT_PREFIX = "survey_datasets/partitioned_states_counties"
COUNTY_OUTPUT_PREFIX = "survey_datasets/overview/county_metrics"

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

# Canonical filters — same rationale as build_overview_aggregates but at
# county level. Drop forecast rows (AUG/OCT) and sub-class breakdowns.
CANON_PROD_PRACTICE = {"ALL PRODUCTION PRACTICES", ""}
CANON_REF_PERIOD = {"YEAR", "MARKETING YEAR", ""}


def _canonical(df: pd.DataFrame) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if "prodn_practice_desc" in df.columns:
        mask &= df["prodn_practice_desc"].fillna("").isin(CANON_PROD_PRACTICE)
    if "reference_period_desc" in df.columns:
        mask &= df["reference_period_desc"].fillna("").isin(CANON_REF_PERIOD)
    if "domain_desc" in df.columns:
        mask &= df["domain_desc"].fillna("TOTAL").eq("TOTAL")
    if "freq_desc" in df.columns:
        mask &= df["freq_desc"].fillna("").isin(["ANNUAL", ""])
    canon = df[mask].copy()
    if canon.empty:
        return canon
    canon["_class"] = canon["class_desc"].fillna("")
    key_cols = ["fips", "commodity_desc", "year", "statisticcat_desc", "unit_desc"]
    # Drop rows missing fips (some county parquets have state-agg leakage)
    canon = canon[canon["fips"].notna() & (canon["fips"] != "")]
    has_ac = (
        canon.groupby(key_cols)["_class"]
        .apply(lambda s: (s == "ALL CLASSES").any())
        .rename("_has_ac").reset_index()
    )
    merged = canon.merge(has_ac, on=key_cols, how="left")
    return merged[(~merged["_has_ac"]) | (merged["_class"] == "ALL CLASSES")]


def _build_for_state(state: str, cached_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(cached_path)
    if "agg_level_desc" in df.columns:
        df = df[df["agg_level_desc"] == "COUNTY"]
    canon = _canonical(df)
    if canon.empty:
        return pd.DataFrame()

    base_keys = ["fips", "commodity_desc", "year"]

    def _pick(stat: str, unit: str) -> pd.DataFrame:
        sel = canon[(canon["statisticcat_desc"] == stat) & (canon["unit_desc"] == unit)]
        sel = sel[sel["value_num"].notna()]
        if sel.empty:
            return pd.DataFrame(columns=base_keys)
        return sel.groupby(base_keys)["value_num"].sum().reset_index()

    def _pick_max_unit(stat: str, value_col: str, unit_col: str) -> pd.DataFrame:
        sel = canon[canon["statisticcat_desc"] == stat]
        sel = sel[sel["value_num"].notna()]
        if sel.empty:
            return pd.DataFrame(columns=base_keys + [value_col, unit_col])
        idx = sel.groupby(base_keys)["value_num"].idxmax().dropna().astype(int)
        return sel.loc[idx, base_keys + ["value_num", "unit_desc"]].rename(
            columns={"value_num": value_col, "unit_desc": unit_col}
        )

    area_h = _pick("AREA HARVESTED", "ACRES").rename(columns={"value_num": "area_harvested_acres"})
    area_p = _pick("AREA PLANTED", "ACRES").rename(columns={"value_num": "area_planted_acres"})
    production = _pick_max_unit("PRODUCTION", "production", "production_unit")
    yld = _pick_max_unit("YIELD", "yield_value", "yield_unit")

    # county_name lookup — canonical value is stable across rows, pick first
    names = (
        canon.groupby("fips")["county_name"]
        .agg(lambda s: s.dropna().iloc[0] if len(s.dropna()) else "")
        .reset_index()
    )

    out = area_h
    for frame in (area_p, production, yld):
        out = out.merge(frame, on=base_keys, how="outer")
    out = out.merge(names, on="fips", how="left")

    out["state_alpha"] = state
    out = out[out["year"].notna()]
    out["year"] = out["year"].astype(int)

    return out.sort_values(["year", "fips", "commodity_desc"]).reset_index(drop=True)


def process_state(state: str, s3, upload: bool) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    local = CACHE_DIR / f"{state}.parquet"
    if not local.exists():
        try:
            s3.download_file(S3_BUCKET, f"{COUNTY_INPUT_PREFIX}/{state}.parquet", str(local))
        except Exception as e:
            logger.warning(f"[{state}] download failed: {e}")
            return {"state": state, "error": "download_failed"}

    out = _build_for_state(state, local)
    if out.empty:
        logger.warning(f"[{state}] no canonical county rows")
        return {"state": state, "rows": 0}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{state}.parquet"
    out.to_parquet(dest, index=False, compression="snappy")

    result = {"state": state, "rows": len(out), "bytes": dest.stat().st_size}

    if upload:
        key = f"{COUNTY_OUTPUT_PREFIX}/{state}.parquet"
        try:
            s3.upload_file(str(dest), S3_BUCKET, key)
            result["uploaded"] = True
        except Exception as e:
            logger.error(f"[{state}] upload failed: {e}")
            result["uploaded"] = False

    logger.info(f"[{state}] rows={len(out):,} bytes={dest.stat().st_size:,}")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", help="Comma-separated codes (default: all 48 + DC)")
    ap.add_argument("--upload", action="store_true")
    args = ap.parse_args()

    target = [s.strip().upper() for s in args.states.split(",")] if args.states else STATES

    import boto3
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-2"))
    if args.upload:
        try:
            s3.head_bucket(Bucket=S3_BUCKET)
        except Exception as e:
            logger.error(f"S3 access failed: {e}. Re-authenticate and retry.")
            sys.exit(2)

    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(process_state, st, s3, args.upload): st for st in target}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"state": futs[fut], "error": str(e)})

    total_rows = sum(r.get("rows", 0) for r in results)
    logger.info(f"total county rows across {len(results)} states: {total_rows:,}")

    errs = [r for r in results if r.get("error") or r.get("uploaded") is False]
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
