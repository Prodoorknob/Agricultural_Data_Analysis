"""
upload_to_s3.py - Upload parquet files to S3 with backup and dual-layout support

Uploads the ingested parquet files to both:
1. partitioned_states/{STATE}.parquet  (for browser-side hyparquet fetches)
2. athena_optimized/state_alpha={STATE}/data.parquet  (for Athena queries)

Also backs up existing files before overwriting.

Usage:
    python upload_to_s3.py
    python upload_to_s3.py --source-dir ./pipeline/output
    python upload_to_s3.py --backup  (backup existing before upload)
    python upload_to_s3.py --dry-run (show what would be uploaded)

Environment Variables:
    AWS_REGION - AWS region (default: us-east-2)
"""

import os
import sys
import json
import base64
import hashlib
import logging
import argparse
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# S3 Configuration.
# State- and county-aggregated data share the bucket but live under distinct
# prefixes so they can't accidentally overwrite each other. Caller picks the
# layout via --layout {state,county}; the `*_counties/` prefixes hold the
# COUNTY-agg_level NASS rows produced by --county-only ingests, separate
# from the STATE-agg_level rows served to the main dashboard tabs.
S3_BUCKET = "usda-analysis-datasets"
S3_BACKUP_PREFIX = "survey_datasets/backups"

LAYOUT_PREFIXES = {
    "state": {
        "browser": "survey_datasets/partitioned_states",
        "athena":  "survey_datasets/athena_optimized",
    },
    "county": {
        "browser": "survey_datasets/partitioned_states_counties",
        "athena":  "survey_datasets/athena_optimized_counties",
    },
}

DEFAULT_SOURCE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-east-2")


def get_s3_client(region: str = DEFAULT_REGION):
    """Create an S3 client."""
    return boto3.client("s3", region_name=region)


def file_md5(filepath: str) -> str:
    """Compute MD5 hash of a local file."""
    md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    return md5.hexdigest()


def file_sha256_b64(filepath: str) -> str:
    """Compute base64-encoded SHA256 of a local file (matches S3 ChecksumSHA256 for single-part uploads)."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode()


def s3_object_exists(s3_client, bucket: str, key: str) -> bool:
    """Check if an S3 object exists."""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def backup_existing(s3_client, bucket: str, key: str, backup_prefix: str):
    """Copy existing S3 object to backup location."""
    if not s3_object_exists(s3_client, bucket, key):
        return

    date_stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_key = f"{backup_prefix}/{date_stamp}/{key.split('/')[-1]}"

    logger.info(f"  Backing up s3://{bucket}/{key} -> s3://{bucket}/{backup_key}")
    s3_client.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": key},
        Key=backup_key,
    )


def upload_file(
    s3_client, local_path: str, bucket: str, s3_key: str, dry_run: bool = False
) -> bool:
    """Upload a local file to S3 with SHA256 integrity verification.

    Uses ChecksumAlgorithm=SHA256 so boto3's managed transfer verifies each
    part's checksum at upload time. S3 rejects the CompleteMultipartUpload
    (or single-part PUT) if any part's checksum mismatches. Also performs a
    redundant ContentLength check against the local file size.
    """
    if dry_run:
        logger.info(f"  [DRY RUN] Would upload: {local_path} -> s3://{bucket}/{s3_key}")
        return True

    local_size = os.path.getsize(local_path)
    logger.info(
        f"  Uploading: {os.path.basename(local_path)} ({local_size:,} bytes) -> s3://{bucket}/{s3_key}"
    )

    s3_client.upload_file(
        local_path,
        bucket,
        s3_key,
        ExtraArgs={"ChecksumAlgorithm": "SHA256"},
    )

    response = s3_client.head_object(Bucket=bucket, Key=s3_key, ChecksumMode="ENABLED")
    s3_size = response["ContentLength"]
    if s3_size != local_size:
        raise RuntimeError(
            f"Upload verification failed for s3://{bucket}/{s3_key}: "
            f"size mismatch (local={local_size}, s3={s3_size})"
        )

    s3_checksum = response.get("ChecksumSHA256")
    if s3_checksum and "-" not in s3_checksum:
        local_sha = file_sha256_b64(local_path)
        if s3_checksum != local_sha:
            raise RuntimeError(
                f"Upload verification failed for s3://{bucket}/{s3_key}: "
                f"SHA256 mismatch (local={local_sha}, s3={s3_checksum})"
            )
        logger.info(f"    Verified: {s3_size:,} bytes, SHA256={s3_checksum}")
    elif s3_checksum:
        logger.info(f"    Verified: {s3_size:,} bytes, multipart-SHA256={s3_checksum}")
    else:
        logger.info(f"    Verified: {s3_size:,} bytes (no checksum returned)")

    return True


def upload_all(
    source_dir: str,
    do_backup: bool = True,
    dry_run: bool = False,
    region: str = DEFAULT_REGION,
    layout: str = "state",
):
    """Upload all parquet files from source directory to S3.

    Uploads to both browser-fetch and Athena-optimized paths for the chosen
    layout. Per-file failures are caught and logged; the function returns
    False if any upload failed so the caller (cron_runner.sh) can suppress
    downstream steps that depend on a clean S3 state (notably the
    `last_success` stamp in quickstats_ingest).
    """
    if layout not in LAYOUT_PREFIXES:
        raise ValueError(f"Unknown layout '{layout}'; expected one of {list(LAYOUT_PREFIXES)}")
    prefixes = LAYOUT_PREFIXES[layout]
    s3_client = get_s3_client(region)

    succeeded = 0
    failed: list[tuple[str, str]] = []

    def _try_upload(local_path: str, s3_key: str) -> None:
        nonlocal succeeded
        try:
            if do_backup:
                backup_existing(s3_client, S3_BUCKET, s3_key, S3_BACKUP_PREFIX)
            upload_file(s3_client, local_path, S3_BUCKET, s3_key, dry_run)
            succeeded += 1
        except (ClientError, RuntimeError, OSError) as e:
            logger.error(f"  FAILED: {local_path} -> s3://{S3_BUCKET}/{s3_key}: {e}")
            failed.append((s3_key, str(e)))

    logger.info("=" * 60)
    logger.info(f"Layout: {layout}")
    logger.info(f"Uploading browser-fetch layout ({prefixes['browser']}/)")
    logger.info("=" * 60)

    parquet_files = [f for f in os.listdir(source_dir) if f.endswith(".parquet")]
    if not parquet_files:
        logger.warning(f"No parquet files found in {source_dir}")
        return False

    logger.info(f"Found {len(parquet_files)} parquet files to upload")

    for filename in sorted(parquet_files):
        local_path = os.path.join(source_dir, filename)
        s3_key = f"{prefixes['browser']}/{filename}"
        _try_upload(local_path, s3_key)

    athena_source = os.path.join(source_dir, "athena_optimized")
    if os.path.exists(athena_source):
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"Uploading Athena-optimized layout ({prefixes['athena']}/)")
        logger.info("=" * 60)

        for partition_dir in sorted(os.listdir(athena_source)):
            partition_path = os.path.join(athena_source, partition_dir)
            if not os.path.isdir(partition_path):
                continue

            data_file = os.path.join(partition_path, "data.parquet")
            if not os.path.exists(data_file):
                continue

            s3_key = f"{prefixes['athena']}/{partition_dir}/data.parquet"
            _try_upload(data_file, s3_key)
    else:
        logger.info("No Athena-optimized directory found, skipping Athena upload")

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"UPLOAD SUMMARY: {succeeded} succeeded, {len(failed)} failed")
    if failed:
        for key, err in failed:
            logger.error(f"  FAILED: {key} — {err}")
    logger.info("=" * 60)

    all_good = len(failed) == 0
    # Only stamp the NASS manifest after a clean STATE-layout upload. County
    # uploads are standalone artifacts; promoting the manifest on a county-
    # only run would cause incremental_check.py to skip the next state-level
    # ingest (it compares against manifest.uploaded_record_counts, which is
    # state-scoped).
    if all_good and not dry_run and layout == "state":
        _promote_manifest_after_upload()

    return all_good


def _promote_manifest_after_upload() -> None:
    """Mark the current ingestion as durably published.

    After a clean S3 upload, copy the local `record_counts` (written by
    quickstats_ingest during the ingest phase) into `uploaded_record_counts`
    and stamp `last_success` + `last_upload_success`. `incremental_check.py`
    compares against `uploaded_record_counts`, so if the upload step crashes
    the next cron run re-ingests instead of silently declaring "no new data".
    """
    if not os.path.exists(MANIFEST_PATH):
        logger.warning("No manifest.json present; skipping upload stamp.")
        return
    try:
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        now = datetime.now(timezone.utc).isoformat()
        manifest["uploaded_record_counts"] = dict(manifest.get("record_counts", {}))
        manifest["last_upload_success"] = now
        manifest["last_success"] = now
        with open(MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=4, default=str)
        logger.info(f"Manifest stamped: last_upload_success={now}")
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not update manifest after upload: {e}")


def main():
    parser = argparse.ArgumentParser(description="Upload parquet files to S3")
    parser.add_argument(
        "--source-dir", default=DEFAULT_SOURCE_DIR, help="Directory containing parquet files"
    )
    parser.add_argument(
        "--layout",
        choices=sorted(LAYOUT_PREFIXES),
        default="state",
        help="S3 path layout: 'state' (default) for STATE-level NASS rows to "
        "partitioned_states/, 'county' for COUNTY-level rows to "
        "partitioned_states_counties/. Pick based on what your pipeline/output "
        "directory actually contains — the tool does not re-inspect row content.",
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Skip backing up existing S3 files"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region")
    args = parser.parse_args()

    if not os.path.exists(args.source_dir):
        logger.error(f"Source directory not found: {args.source_dir}")
        sys.exit(1)

    success = upload_all(
        source_dir=args.source_dir,
        do_backup=not args.no_backup,
        dry_run=args.dry_run,
        region=args.region,
        layout=args.layout,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
