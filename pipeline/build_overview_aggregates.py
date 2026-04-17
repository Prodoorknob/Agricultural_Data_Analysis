"""
build_overview_aggregates.py — Produce two small parquet files the frontend
uses for the Overview map, hero numbers, revenue mix, peer comparison,
rank calculation, and 25-year sparklines.

Inputs (local or S3):
  pipeline/output_rebuilt/{STATE}.parquet           (all 48 + DC states)
  NATIONAL.parquet is NOT read — we build our own national rollup from the
  state files so we can compute per-state ranks consistently.

Outputs:
  overview/state_totals.parquet
      One row per (year, state_alpha):
        total_sales_usd, total_area_planted_acres, top_commodity,
        top_commodity_sales_usd, commodity_count, rank_by_sales
      Drives the choropleth, overview hero, rank number, peer comparison.

  overview/state_commodity_totals.parquet
      One row per (year, state_alpha, commodity_desc):
        sales_usd, area_planted_acres, area_harvested_acres,
        production (numeric), production_unit, inventory_head,
        yield_value, yield_unit, group_desc, sector_desc
      Drives revenue-mix donut, 25-year sparklines, crop-type filter
      (via group_desc / sector_desc), and livestock inventory tiles.

Usage:
    python -m pipeline.build_overview_aggregates                         # from local rebuilt dir
    python -m pipeline.build_overview_aggregates --from-s3               # download rebuilt from S3
    python -m pipeline.build_overview_aggregates --upload                # upload aggregates to S3
    python -m pipeline.build_overview_aggregates --states IN,IA,IL       # subset for testing
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_THIS_DIR = Path(__file__).resolve().parent
REBUILT_DIR = _THIS_DIR / "output_rebuilt"
OUT_DIR = _THIS_DIR / "output_overview"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("overview_agg")

S3_BUCKET = "usda-analysis-datasets"
OVERVIEW_PREFIX = "survey_datasets/overview"
REBUILT_PREFIX = "survey_datasets/partitioned_states"

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
]

# Canonical-row filters matching quickstats_ingest._canonical_mask. Applied
# here to the rebuilt parquets so we select exactly one value per
# (state, commodity, year, stat, unit). Class-tier logic also applied.
CANON_PROD_PRACTICE = {"ALL PRODUCTION PRACTICES", ""}
CANON_REF_PERIOD = {"YEAR", "MARKETING YEAR", ""}

SUM_STATS = {"SALES", "PRODUCTION", "AREA PLANTED", "AREA HARVESTED",
             "INVENTORY", "SLAUGHTERED", "HEAD", "OPERATIONS"}

# Pick one canonical name when NASS ships overlapping ones. Rule: drop the
# "generic" name when its "& HAYLAGE" (or similar umbrella) counterpart exists.
COMMODITY_ALIASES = {
    "HAY": "HAY & HAYLAGE",     # prefer newer umbrella term
}


def _canonical_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Apply canonical filters + tier-aware class pick, return long-format
    (state_alpha, commodity_desc, year, statisticcat_desc, unit_desc, value_num,
     group_desc, sector_desc)."""
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

    # Per (state, commodity, year, stat, unit): prefer ALL CLASSES rows when present.
    key_cols = ["state_alpha", "commodity_desc", "year", "statisticcat_desc", "unit_desc"]
    has_ac = (
        canon.groupby(key_cols)["_class"]
        .apply(lambda s: (s == "ALL CLASSES").any())
        .rename("_has_ac")
        .reset_index()
    )
    merged = canon.merge(has_ac, on=key_cols, how="left")
    kept = merged[(~merged["_has_ac"]) | (merged["_class"] == "ALL CLASSES")]

    def _agg(stat: str):
        return "sum" if stat in SUM_STATS else "max"

    frames = []
    meta_cols = [c for c in ("group_desc", "sector_desc") if c in kept.columns]
    for stat, sub in kept.groupby("statisticcat_desc"):
        agg_val = sub.groupby(key_cols)["value_num"].agg(_agg(stat)).reset_index()
        if meta_cols:
            meta = (
                sub.groupby(key_cols)[meta_cols]
                .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "")
                .reset_index()
            )
            agg_val = agg_val.merge(meta, on=key_cols, how="left")
        frames.append(agg_val)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _build_state_commodity_totals(canon: pd.DataFrame) -> pd.DataFrame:
    """Long-format → one row per (year, state, commodity) with metric columns."""
    if canon.empty:
        return pd.DataFrame()

    base_keys = ["state_alpha", "commodity_desc", "year"]

    def _pick(stat: str, unit: str | None = None) -> pd.Series:
        sel = canon[canon["statisticcat_desc"] == stat]
        if unit is not None:
            sel = sel[sel["unit_desc"] == unit]
        return sel.groupby(base_keys)["value_num"].max() if not sel.empty else pd.Series(dtype=float)

    def _as_frame(series: pd.Series, name: str) -> pd.DataFrame:
        if series.empty:
            return pd.DataFrame(columns=base_keys + [name])
        return series.rename(name).reset_index()

    sales_usd = _as_frame(_pick("SALES", "$"), "sales_usd")
    area_planted = _as_frame(_pick("AREA PLANTED", "ACRES"), "area_planted_acres")
    area_harvested = _as_frame(_pick("AREA HARVESTED", "ACRES"), "area_harvested_acres")
    inventory_head = _as_frame(_pick("INVENTORY", "HEAD"), "inventory_head")

    # PRODUCTION: keep both value and unit so the frontend can pick the most
    # informative unit (bushels for grains, tons for hay, head for livestock
    # slaughter, etc.). Pick the row with the largest value per key as a
    # stable single-unit pick — for crops this corresponds to bushels, for
    # HAY to tons, etc.
    def _pick_max_value_row(stat: str, value_col: str, unit_col: str,
                            unit_filter: str | None = None) -> pd.DataFrame:
        sel = canon[canon["statisticcat_desc"] == stat]
        if unit_filter is not None:
            sel = sel[sel["unit_desc"] != unit_filter]
        sel = sel[sel["value_num"].notna()]  # idxmax NaN-guard
        if sel.empty:
            return pd.DataFrame(columns=base_keys + [value_col, unit_col])
        idx = sel.groupby(base_keys)["value_num"].idxmax().dropna().astype(int)
        return sel.loc[idx, base_keys + ["value_num", "unit_desc"]].rename(
            columns={"value_num": value_col, "unit_desc": unit_col}
        )

    prod_rows = _pick_max_value_row("PRODUCTION", "production", "production_unit", unit_filter="$")
    yld_rows = _pick_max_value_row("YIELD", "yield_value", "yield_unit")

    meta_cols = [c for c in ("group_desc", "sector_desc") if c in canon.columns]
    if meta_cols:
        meta = (
            canon.groupby(base_keys)[meta_cols]
            .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "")
            .reset_index()
        )
    else:
        meta = pd.DataFrame(columns=base_keys)

    # Outer-merge all metric frames on base_keys.
    out = sales_usd
    for frame in (area_planted, area_harvested, inventory_head,
                  prod_rows, yld_rows, meta):
        out = out.merge(frame, on=base_keys, how="outer")

    # Dedupe commodity aliases (e.g. keep HAY & HAYLAGE when both present)
    # Drop rows with the obsolete name if the umbrella name exists for the
    # same (year, state_alpha).
    for old_name, new_name in COMMODITY_ALIASES.items():
        has_new = out[out["commodity_desc"] == new_name][["year", "state_alpha"]]
        if not has_new.empty:
            drop_mask = (
                (out["commodity_desc"] == old_name)
                & out.set_index(["year", "state_alpha"]).index.isin(
                    has_new.set_index(["year", "state_alpha"]).index
                )
            )
            out = out[~drop_mask].reset_index(drop=True)

    # Type hygiene
    for col in ("sales_usd", "area_planted_acres", "area_harvested_acres",
                "inventory_head", "production", "yield_value"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in ("group_desc", "sector_desc", "production_unit", "yield_unit"):
        if col in out.columns:
            out[col] = out[col].fillna("").astype(str)

    out = out[out["year"].notna()]
    out["year"] = out["year"].astype(int)
    return out.sort_values(["year", "state_alpha", "commodity_desc"]).reset_index(drop=True)


def _build_state_totals(commodity_totals: pd.DataFrame) -> pd.DataFrame:
    """One row per (year, state_alpha) with rank-by-sales."""
    if commodity_totals.empty:
        return pd.DataFrame()

    grp = commodity_totals.groupby(["year", "state_alpha"])

    def _top_crop(sub: pd.DataFrame) -> pd.Series:
        if sub["sales_usd"].notna().any():
            top = sub.loc[sub["sales_usd"].idxmax()]
            return pd.Series({
                "top_commodity": top["commodity_desc"],
                "top_commodity_sales_usd": float(top["sales_usd"]),
            })
        return pd.Series({"top_commodity": "", "top_commodity_sales_usd": np.nan})

    totals = grp.agg(
        total_sales_usd=("sales_usd", "sum"),
        total_area_planted_acres=("area_planted_acres", "sum"),
        commodity_count=("commodity_desc", "nunique"),
    ).reset_index()

    top = grp.apply(_top_crop, include_groups=False).reset_index()
    totals = totals.merge(top, on=["year", "state_alpha"], how="left")

    # Rank within each year, descending by total_sales_usd.
    totals["rank_by_sales"] = (
        totals.groupby("year")["total_sales_usd"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )

    return totals.sort_values(["year", "rank_by_sales", "state_alpha"]).reset_index(drop=True)


def _read_state_parquet(state: str, from_s3: bool, s3) -> pd.DataFrame:
    if not from_s3:
        path = REBUILT_DIR / f"{state}.parquet"
        if not path.exists():
            logger.warning(f"[{state}] missing local rebuilt parquet at {path}")
            return pd.DataFrame()
        return pd.read_parquet(path)
    key = f"{REBUILT_PREFIX}/{state}.parquet"
    dest = REBUILT_DIR / f"{state}.parquet"
    REBUILT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        s3.download_file(S3_BUCKET, key, str(dest))
    except Exception as e:
        logger.warning(f"[{state}] S3 download failed: {e}")
        return pd.DataFrame()
    return pd.read_parquet(dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", help="Comma-separated state codes (default: all 48 + DC)")
    ap.add_argument("--from-s3", action="store_true", help="Download rebuilt parquets from S3")
    ap.add_argument("--upload", action="store_true", help="Upload aggregates back to S3")
    ap.add_argument("--year-start", type=int, default=2001)
    ap.add_argument("--year-end", type=int, default=2025)
    args = ap.parse_args()

    target_states = [s.strip().upper() for s in args.states.split(",")] if args.states else STATES

    s3 = None
    if args.from_s3 or args.upload:
        import boto3
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-2"))
        try:
            s3.head_bucket(Bucket=S3_BUCKET)
        except Exception as e:
            logger.error(f"S3 access failed: {e}. Re-authenticate and retry.")
            sys.exit(2)

    all_rows: list[pd.DataFrame] = []
    for state in target_states:
        df = _read_state_parquet(state, args.from_s3, s3)
        if df.empty:
            continue
        df = df[(df["year"] >= args.year_start) & (df["year"] <= args.year_end)]
        # State/national agg level only — county rows belong in a separate aggregate.
        if "agg_level_desc" in df.columns:
            df = df[df["agg_level_desc"] != "COUNTY"]
        canon = _canonical_frame(df)
        if canon.empty:
            logger.warning(f"[{state}] no canonical rows after filtering")
            continue
        all_rows.append(canon)
        logger.info(f"[{state}] canonical rows: {len(canon):,}")

    if not all_rows:
        logger.error("no data to aggregate")
        sys.exit(1)

    long_df = pd.concat(all_rows, ignore_index=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    commodity_totals = _build_state_commodity_totals(long_df)
    commodity_path = OUT_DIR / "state_commodity_totals.parquet"
    commodity_totals.to_parquet(commodity_path, index=False, compression="snappy")
    logger.info(f"wrote {commodity_path} rows={len(commodity_totals):,} size={commodity_path.stat().st_size:,} bytes")

    state_totals = _build_state_totals(commodity_totals)
    totals_path = OUT_DIR / "state_totals.parquet"
    state_totals.to_parquet(totals_path, index=False, compression="snappy")
    logger.info(f"wrote {totals_path} rows={len(state_totals):,} size={totals_path.stat().st_size:,} bytes")

    if args.upload:
        for local in (commodity_path, totals_path):
            key = f"{OVERVIEW_PREFIX}/{local.name}"
            s3.upload_file(str(local), S3_BUCKET, key)
            logger.info(f"uploaded s3://{S3_BUCKET}/{key}")

    # Spot-check output
    print("\n— state_totals sample —")
    print(state_totals[state_totals["year"] == args.year_end].head(10).to_string(index=False))
    print("\n— state_commodity_totals sample (IN 2024) —")
    sub = commodity_totals[(commodity_totals["year"] == args.year_end) & (commodity_totals["state_alpha"] == "IN")]
    print(sub.sort_values("sales_usd", ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()
