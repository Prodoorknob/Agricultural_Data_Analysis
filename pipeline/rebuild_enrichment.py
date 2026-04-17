"""
rebuild_enrichment.py — Re-derive DERIVED rows on existing state parquets.

The earlier enrich_dataframe summed across class_desc variants and produced
inflated DERIVED rows (e.g. Indiana HAY $338 B when reality is ~$296 M). The
fix in quickstats_ingest.py uses tier-aware canonical aggregation instead.

This script patches existing S3 parquets in place without a USDA re-fetch:
  1. Download partitioned_states/{STATE}.parquet from S3.
  2. Strip source_desc='DERIVED' rows (they are all bad).
  3. Re-run the corrected enrich_dataframe.
  4. Write locally to pipeline/output_rebuilt/{STATE}.parquet.
  5. Optionally back up the existing S3 copy, then upload the rebuilt one.

Usage:
    python -m pipeline.rebuild_enrichment                   # all states, dry-run
    python -m pipeline.rebuild_enrichment --upload          # actually upload
    python -m pipeline.rebuild_enrichment --states IN,IA    # subset
    python -m pipeline.rebuild_enrichment --upload --backup # upload + backup old

Environment:
    AWS credentials via the usual boto3 chain (env / ~/.aws / SSO).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Ensure package-style import works whether run as module or script.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR.parent))

from pipeline.quickstats_ingest import enrich_dataframe  # type: ignore  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("rebuild")

S3_BUCKET = "usda-analysis-datasets"
BROWSER_PREFIX = "survey_datasets/partitioned_states"
ATHENA_PREFIX = "survey_datasets/athena_optimized"
BACKUP_PREFIX = "survey_datasets/backups"

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "NATIONAL",
]

REBUILD_DIR = _THIS_DIR / "output_rebuilt"
DOWNLOAD_DIR = _THIS_DIR / "output_s3_cached"


def get_s3():
    import boto3
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-2"))


def download_parquet(state: str, s3) -> Path | None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{BROWSER_PREFIX}/{state}.parquet"
    dest = DOWNLOAD_DIR / f"{state}.parquet"
    if dest.exists() and dest.stat().st_size > 0:
        logger.info(f"[{state}] using cached local copy ({dest.stat().st_size:,} bytes)")
        return dest
    try:
        s3.download_file(S3_BUCKET, key, str(dest))
        logger.info(f"[{state}] downloaded from S3 ({dest.stat().st_size:,} bytes)")
        return dest
    except Exception as e:
        logger.warning(f"[{state}] download failed: {e}")
        return None


def rebuild_one(state: str, src: Path) -> dict:
    """Strip bad DERIVED rows and re-enrich. Returns stats dict."""
    df = pd.read_parquet(src)
    n_in = len(df)
    n_derived_old = int((df["source_desc"] == "DERIVED").sum()) if "source_desc" in df.columns else 0

    clean = df[df["source_desc"] != "DERIVED"].copy() if "source_desc" in df.columns else df.copy()

    # enrich_dataframe expects agg_level_desc — older files may not have it.
    if "agg_level_desc" not in clean.columns:
        clean["agg_level_desc"] = "STATE"

    rebuilt = enrich_dataframe(clean)
    n_derived_new = int((rebuilt["source_desc"] == "DERIVED").sum()) if "source_desc" in rebuilt.columns else 0

    REBUILD_DIR.mkdir(parents=True, exist_ok=True)
    dest = REBUILD_DIR / f"{state}.parquet"
    rebuilt.to_parquet(dest, index=False, compression="snappy")

    return {
        "state": state,
        "rows_in": n_in,
        "rows_out": len(rebuilt),
        "derived_old": n_derived_old,
        "derived_new": n_derived_new,
        "bytes_out": dest.stat().st_size,
    }


def backup_current(state: str, s3) -> bool:
    """Copy the current partitioned_states/{STATE}.parquet to backups/<timestamp>/."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    src_key = f"{BROWSER_PREFIX}/{state}.parquet"
    dst_key = f"{BACKUP_PREFIX}/{ts}_pre_rebuild/{state}.parquet"
    try:
        s3.copy_object(
            Bucket=S3_BUCKET,
            CopySource={"Bucket": S3_BUCKET, "Key": src_key},
            Key=dst_key,
        )
        logger.info(f"[{state}] backed up to s3://{S3_BUCKET}/{dst_key}")
        return True
    except Exception as e:
        logger.warning(f"[{state}] backup failed: {e}")
        return False


def upload_one(state: str, local_path: Path, s3) -> bool:
    """Upload the rebuilt parquet to both partitioned_states and athena_optimized layouts."""
    ok = True

    # 1. Browser-friendly single-file layout
    browser_key = f"{BROWSER_PREFIX}/{state}.parquet"
    try:
        s3.upload_file(str(local_path), S3_BUCKET, browser_key)
        logger.info(f"[{state}] uploaded to s3://{S3_BUCKET}/{browser_key}")
    except Exception as e:
        logger.error(f"[{state}] browser upload failed: {e}")
        ok = False

    # 2. Athena-partitioned layout (skip NATIONAL — that's an aggregate, not a state)
    if state != "NATIONAL":
        athena_key = f"{ATHENA_PREFIX}/state_alpha={state}/data.parquet"
        try:
            s3.upload_file(str(local_path), S3_BUCKET, athena_key)
            logger.info(f"[{state}] uploaded to s3://{S3_BUCKET}/{athena_key}")
        except Exception as e:
            logger.error(f"[{state}] athena upload failed: {e}")
            ok = False

    return ok


def process_state(state: str, s3, upload: bool, backup: bool) -> dict:
    src = download_parquet(state, s3)
    if src is None:
        return {"state": state, "error": "download_failed"}

    stats = rebuild_one(state, src)

    if upload:
        if backup:
            backup_current(state, s3)
        ok = upload_one(state, REBUILD_DIR / f"{state}.parquet", s3)
        stats["uploaded"] = ok

    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", help="Comma-separated state codes (default: all 48 + DC + NATIONAL)")
    ap.add_argument("--upload", action="store_true", help="Upload rebuilt files to S3")
    ap.add_argument("--backup", action="store_true", help="Back up current S3 copies before upload")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    target_states = [s.strip().upper() for s in args.states.split(",")] if args.states else STATES

    if args.upload:
        try:
            s3 = get_s3()
            s3.head_bucket(Bucket=S3_BUCKET)
        except Exception as e:
            logger.error(f"S3 access check failed: {e}")
            logger.error("Re-authenticate (e.g. 'aws login') and retry with --upload.")
            sys.exit(2)
    else:
        # Download-only needs read access; still construct client via the same chain
        s3 = get_s3()

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(process_state, st, s3, args.upload, args.backup): st for st in target_states}
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"state": futs[fut], "error": str(e)})

    # Summary table
    logger.info("=" * 70)
    logger.info(f"{'state':<10}{'rows_in':>10}{'rows_out':>10}{'derived_old':>13}{'derived_new':>13}{'upload':>10}")
    for r in sorted(results, key=lambda x: x.get("state", "")):
        if r.get("error"):
            logger.info(f"{r['state']:<10} ERROR: {r['error']}")
            continue
        up = "yes" if r.get("uploaded") else ("skip" if not args.upload else "FAIL")
        logger.info(
            f"{r['state']:<10}"
            f"{r['rows_in']:>10,}{r['rows_out']:>10,}"
            f"{r['derived_old']:>13,}{r['derived_new']:>13,}"
            f"{up:>10}"
        )

    errs = [r for r in results if r.get("error") or r.get("uploaded") is False]
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
