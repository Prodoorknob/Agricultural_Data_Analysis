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
import hashlib
import logging
import argparse
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# S3 Configuration
S3_BUCKET = "usda-analysis-datasets"
S3_BROWSER_PREFIX = "survey_datasets/partitioned_states"
S3_ATHENA_PREFIX = "survey_datasets/athena_optimized"
S3_BACKUP_PREFIX = "survey_datasets/backups"

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
    """Upload a local file to S3 with MD5 verification."""
    if dry_run:
        logger.info(f"  [DRY RUN] Would upload: {local_path} -> s3://{bucket}/{s3_key}")
        return True

    local_md5 = file_md5(local_path)
    logger.info(f"  Uploading: {os.path.basename(local_path)} -> s3://{bucket}/{s3_key}")

    s3_client.upload_file(local_path, bucket, s3_key)

    # Verify upload
    response = s3_client.head_object(Bucket=bucket, Key=s3_key)
    s3_etag = response["ETag"].strip('"')

    # Note: ETag for non-multipart uploads equals MD5
    if s3_etag == local_md5:
        logger.info(f"    MD5 verified: {local_md5}")
    else:
        logger.warning(
            f"    MD5 mismatch (local={local_md5}, s3={s3_etag}). "
            "This may be expected for multipart uploads."
        )

    return True


def upload_all(
    source_dir: str,
    do_backup: bool = True,
    dry_run: bool = False,
    region: str = DEFAULT_REGION,
):
    """Upload all parquet files from source directory to S3.

    Uploads to both browser-fetch and Athena-optimized paths.
    """
    s3_client = get_s3_client(region)

    # 1. Upload browser-fetch layout: partitioned_states/{STATE}.parquet
    logger.info("=" * 60)
    logger.info("Uploading browser-fetch layout (partitioned_states/)")
    logger.info("=" * 60)

    parquet_files = [f for f in os.listdir(source_dir) if f.endswith(".parquet")]
    if not parquet_files:
        logger.warning(f"No parquet files found in {source_dir}")
        return False

    logger.info(f"Found {len(parquet_files)} parquet files to upload")

    for filename in sorted(parquet_files):
        local_path = os.path.join(source_dir, filename)
        s3_key = f"{S3_BROWSER_PREFIX}/{filename}"

        if do_backup:
            backup_existing(s3_client, S3_BUCKET, s3_key, S3_BACKUP_PREFIX)

        upload_file(s3_client, local_path, S3_BUCKET, s3_key, dry_run)

    # 2. Upload Athena-optimized layout: athena_optimized/state_alpha={STATE}/data.parquet
    athena_source = os.path.join(source_dir, "athena_optimized")
    if os.path.exists(athena_source):
        logger.info("")
        logger.info("=" * 60)
        logger.info("Uploading Athena-optimized layout (athena_optimized/)")
        logger.info("=" * 60)

        for partition_dir in sorted(os.listdir(athena_source)):
            partition_path = os.path.join(athena_source, partition_dir)
            if not os.path.isdir(partition_path):
                continue

            data_file = os.path.join(partition_path, "data.parquet")
            if not os.path.exists(data_file):
                continue

            s3_key = f"{S3_ATHENA_PREFIX}/{partition_dir}/data.parquet"

            if do_backup:
                backup_existing(s3_client, S3_BUCKET, s3_key, S3_BACKUP_PREFIX)

            upload_file(s3_client, data_file, S3_BUCKET, s3_key, dry_run)
    else:
        logger.info("No Athena-optimized directory found, skipping Athena upload")

    logger.info("")
    logger.info("=" * 60)
    logger.info("UPLOAD COMPLETE")
    logger.info("=" * 60)
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload parquet files to S3")
    parser.add_argument(
        "--source-dir", default=DEFAULT_SOURCE_DIR, help="Directory containing parquet files"
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
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
