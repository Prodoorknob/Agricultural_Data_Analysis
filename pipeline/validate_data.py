"""
validate_data.py - Data integrity checks for USDA QuickStats parquet files

Validates:
  - All 50 states + DC + US (NATIONAL) present
  - Row counts per state within expected range
  - Year coverage (2001-2025)
  - Null rates per critical column
  - value_num distribution (no extreme outliers)
  - Required columns present

Usage:
    python validate_data.py                    # Check local pipeline/output/
    python validate_data.py --s3               # Check S3 bucket directly
    python validate_data.py --dir /path/to/dir # Check custom directory
"""

import os
import sys
import argparse
import logging
from pathlib import Path

import pandas as pd
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Expected states: 50 states + DC
EXPECTED_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC',
}

REQUIRED_COLUMNS = [
    'state_alpha', 'year', 'commodity_desc', 'statisticcat_desc',
    'unit_desc', 'value_num', 'sector_desc',
]

MIN_ROWS_PER_STATE = 100
MAX_NULL_RATE_CRITICAL = 0.05  # 5% max null rate for critical columns
YEAR_RANGE = (2001, 2025)


def load_parquet_files(directory: str) -> dict[str, pd.DataFrame]:
    """Load all parquet files from a directory."""
    files = {}
    dir_path = Path(directory)
    if not dir_path.exists():
        logger.error(f"Directory not found: {directory}")
        return files

    for f in sorted(dir_path.glob("*.parquet")):
        try:
            df = pd.read_parquet(f)
            state_code = f.stem  # e.g., "IN" from "IN.parquet"
            files[state_code] = df
            logger.info(f"  Loaded {f.name}: {len(df):,} rows, {len(df.columns)} cols")
        except Exception as e:
            logger.error(f"  FAILED to load {f.name}: {e}")

    return files


def load_from_s3(bucket: str = "usda-analysis-datasets",
                 prefix: str = "survey_datasets/partitioned_states/") -> dict[str, pd.DataFrame]:
    """Load parquet files directly from S3."""
    try:
        import boto3
    except ImportError:
        logger.error("boto3 not installed. Run: pip install boto3")
        return {}

    s3 = boto3.client("s3")
    files = {}

    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        objects = response.get("Contents", [])

        for obj in objects:
            key = obj["Key"]
            if not key.endswith(".parquet"):
                continue
            filename = key.split("/")[-1]
            state_code = filename.replace(".parquet", "")

            try:
                import io
                response = s3.get_object(Bucket=bucket, Key=key)
                data = response["Body"].read()
                df = pd.read_parquet(io.BytesIO(data))
                files[state_code] = df
                logger.info(f"  S3: {filename}: {len(df):,} rows")
            except Exception as e:
                logger.error(f"  S3 FAILED: {filename}: {e}")

    except Exception as e:
        logger.error(f"Failed to list S3 objects: {e}")

    return files


class ValidationResult:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name: str, status: str, detail: str = ""):
        self.checks.append({"name": name, "status": status, "detail": detail})
        icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
        msg = f"  {icon} {name}"
        if detail:
            msg += f" — {detail}"
        if status == "FAIL":
            logger.error(msg)
        elif status == "WARN":
            logger.warning(msg)
        else:
            logger.info(msg)

    def summary(self):
        passes = sum(1 for c in self.checks if c["status"] == "PASS")
        warns = sum(1 for c in self.checks if c["status"] == "WARN")
        fails = sum(1 for c in self.checks if c["status"] == "FAIL")
        return passes, warns, fails


def validate(files: dict[str, pd.DataFrame]) -> ValidationResult:
    """Run all validation checks."""
    result = ValidationResult()

    if not files:
        result.add("Files loaded", "FAIL", "No parquet files found")
        return result

    result.add("Files loaded", "PASS", f"{len(files)} files")

    # --- Check 1: Expected states present ---
    found_states = {k for k in files.keys() if k != "NATIONAL" and k != "US"}
    missing = EXPECTED_STATES - found_states
    extra = found_states - EXPECTED_STATES

    if not missing:
        result.add("All states present", "PASS", f"{len(found_states)} states")
    elif len(missing) <= 5:
        result.add("States coverage", "WARN", f"Missing {len(missing)}: {', '.join(sorted(missing))}")
    else:
        result.add("States coverage", "FAIL", f"Missing {len(missing)} states: {', '.join(sorted(missing))}")

    if extra:
        result.add("Extra state codes", "WARN", f"Unexpected: {', '.join(sorted(extra))}")

    # --- Check 2: NATIONAL file ---
    has_national = "NATIONAL" in files or "US" in files
    if has_national:
        nat_key = "NATIONAL" if "NATIONAL" in files else "US"
        result.add("National file", "PASS", f"{len(files[nat_key]):,} rows")
    else:
        result.add("National file", "WARN", "No NATIONAL.parquet found")

    # --- Check 3: Row counts ---
    low_count_states = []
    total_rows = 0
    for state, df in files.items():
        total_rows += len(df)
        if state not in ("NATIONAL", "US") and len(df) < MIN_ROWS_PER_STATE:
            low_count_states.append(f"{state}({len(df)})")

    result.add("Total rows", "PASS", f"{total_rows:,} across all files")

    if not low_count_states:
        result.add("Row counts", "PASS", f"All states >= {MIN_ROWS_PER_STATE} rows")
    else:
        result.add("Row counts", "WARN", f"Low: {', '.join(low_count_states)}")

    # --- Checks 4-10 run across the top-N states by row count ---
    # Sampling one arbitrary state missed corruption in high-value states like
    # TX/CA. Iterate over the largest N so a bad file for any commercially
    # important state surfaces as FAIL instead of silently passing.
    SAMPLE_SIZE = 10
    candidate = [(k, len(v)) for k, v in files.items() if k not in ("NATIONAL", "US")]
    candidate.sort(key=lambda x: x[1], reverse=True)
    sample_states = [k for k, _ in candidate[:SAMPLE_SIZE]]

    if sample_states:
        logger.info(f"Sampling {len(sample_states)} states for content checks: {', '.join(sample_states)}")

        # --- Check 4: Required columns (across all sampled states) ---
        missing_by_state: dict[str, list[str]] = {}
        for st in sample_states:
            missing_cols = [c for c in REQUIRED_COLUMNS if c not in files[st].columns]
            if missing_cols:
                missing_by_state[st] = missing_cols
        if not missing_by_state:
            result.add("Required columns", "PASS", f"All {len(REQUIRED_COLUMNS)} present in {len(sample_states)} sampled states")
        else:
            result.add("Required columns", "FAIL",
                       f"Missing in: {', '.join(f'{s}({",".join(c)})' for s, c in missing_by_state.items())}")

        # --- Check 5: Null rates ---
        critical_cols = ['state_alpha', 'year', 'commodity_desc', 'statisticcat_desc', 'value_num']
        high_null_by_state: dict[str, list[str]] = {}
        for st in sample_states:
            sample_df = files[st]
            high_null = []
            for col in critical_cols:
                if col in sample_df.columns:
                    null_rate = sample_df[col].isna().mean()
                    if null_rate > MAX_NULL_RATE_CRITICAL:
                        high_null.append(f"{col}({null_rate:.1%})")
            if high_null:
                high_null_by_state[st] = high_null
        if not high_null_by_state:
            result.add("Null rates", "PASS", f"All critical cols < {MAX_NULL_RATE_CRITICAL:.0%} nulls across {len(sample_states)} states")
        else:
            result.add("Null rates", "WARN", f"High null in: {', '.join(f'{s}[{",".join(v)}]' for s, v in high_null_by_state.items())}")

        # --- Check 6: Year coverage ---
        bad_year_states: list[str] = []
        for st in sample_states:
            sample_df = files[st]
            if 'year' in sample_df.columns:
                years = sample_df['year'].dropna().unique()
                if len(years) == 0:
                    bad_year_states.append(f"{st}(0)")
                    continue
                min_year = int(min(years))
                max_year = int(max(years))
                if not (min_year <= YEAR_RANGE[0] + 2 and max_year >= YEAR_RANGE[1] - 2):
                    bad_year_states.append(f"{st}({min_year}-{max_year})")
        if not bad_year_states:
            result.add("Year coverage", "PASS", f"All {len(sample_states)} states cover ~{YEAR_RANGE[0]}-{YEAR_RANGE[1]}")
        else:
            result.add("Year coverage", "WARN", f"Gaps: {', '.join(bad_year_states)}")

        # --- Check 7: value_num distribution (most-populous state only — high volume, representative) ---
        primary_state = sample_states[0]
        sample_df = files[primary_state]
        if 'value_num' in sample_df.columns:
            vals = sample_df['value_num'].dropna()
            if len(vals) > 0:
                negative_pct = (vals < 0).mean()
                zero_pct = (vals == 0).mean()
                median_val = vals.median()
                if negative_pct > 0.1:
                    result.add("value_num distribution", "WARN", f"[{primary_state}] {negative_pct:.1%} negative values")
                elif zero_pct > 0.5:
                    result.add("value_num distribution", "WARN", f"[{primary_state}] {zero_pct:.1%} zero values")
                else:
                    result.add("value_num distribution", "PASS",
                               f"[{primary_state}] median={median_val:,.0f}, {zero_pct:.1%} zeros, {negative_pct:.1%} negatives")

        # --- Check 8: Sector coverage (union across sampled states) ---
        expected_sectors = {'CROPS', 'ANIMALS & PRODUCTS'}
        all_sectors: set[str] = set()
        for st in sample_states:
            if 'sector_desc' in files[st].columns:
                all_sectors.update(s.upper() for s in files[st]['sector_desc'].dropna().unique())
        missing_sectors = expected_sectors - all_sectors
        if not missing_sectors:
            result.add("Sector coverage", "PASS", f"Found across sample: {', '.join(sorted(all_sectors))}")
        else:
            result.add("Sector coverage", "WARN", f"Missing from entire sample: {', '.join(sorted(missing_sectors))}")

        # --- Check 9: Stat category coverage (union across sample) ---
        core_cats = {'AREA HARVESTED', 'PRODUCTION', 'YIELD'}
        all_cats: set[str] = set()
        for st in sample_states:
            if 'statisticcat_desc' in files[st].columns:
                all_cats.update(c.upper() for c in files[st]['statisticcat_desc'].dropna().unique())
        missing_cats = core_cats - all_cats
        if not missing_cats:
            result.add("Core stat categories", "PASS", f"All 3 core present across sample ({len(all_cats)} total)")
        else:
            result.add("Core stat categories", "WARN", f"Missing from entire sample: {', '.join(sorted(missing_cats))}")

        # --- Check 10: County data + FIPS (aggregate across sample) ---
        total_county_rows = 0
        bad_fips_by_state: dict[str, int] = {}
        for st in sample_states:
            sample_df = files[st]
            if 'agg_level_desc' in sample_df.columns:
                county_rows = sample_df[sample_df['agg_level_desc'] == 'COUNTY']
                total_county_rows += len(county_rows)
                if 'fips' in county_rows.columns and len(county_rows) > 0:
                    fips = county_rows['fips'].dropna()
                    bad = fips[~fips.str.match(r'^\d{5}$', na=False)]
                    if len(bad) > 0:
                        bad_fips_by_state[st] = len(bad)
        if total_county_rows == 0:
            result.add("County data", "WARN", "No COUNTY rows across sample — run with --include-county")
        else:
            result.add("County data", "PASS", f"{total_county_rows:,} county rows across sample")
            if not bad_fips_by_state:
                result.add("County FIPS format", "PASS", "All FIPS codes are 5-digit numeric")
            else:
                result.add("County FIPS format", "WARN",
                           f"Malformed FIPS in: {', '.join(f'{s}({n})' for s, n in bad_fips_by_state.items())}")
    # --- Check 10: Cross-state year consistency ---
    state_year_counts: dict[str, int] = {}
    for state, df in files.items():
        if state in ("NATIONAL", "US"):
            continue
        if 'year' in df.columns:
            state_year_counts[state] = df['year'].nunique()

    if state_year_counts:
        median_years = int(np.median(list(state_year_counts.values())))
        low_year_states = [f"{s}({c})" for s, c in state_year_counts.items()
                          if c < median_years * 0.5]

        if not low_year_states:
            result.add("Cross-state consistency", "PASS",
                       f"Median {median_years} years per state")
        else:
            result.add("Cross-state consistency", "WARN",
                       f"Low coverage: {', '.join(low_year_states[:10])}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate USDA parquet data integrity")
    parser.add_argument("--dir", default=None,
                       help="Directory containing parquet files (default: pipeline/output/)")
    parser.add_argument("--s3", action="store_true",
                       help="Validate directly from S3 bucket")
    parser.add_argument("--bucket", default="usda-analysis-datasets",
                       help="S3 bucket name")
    parser.add_argument("--prefix", default="survey_datasets/partitioned_states/",
                       help="S3 prefix for parquet files")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("USDA QuickStats Data Validation")
    logger.info("=" * 60)

    if args.s3:
        logger.info(f"Source: s3://{args.bucket}/{args.prefix}")
        logger.info("Loading files from S3...")
        files = load_from_s3(args.bucket, args.prefix)
    else:
        directory = args.dir or os.path.join(os.path.dirname(__file__), "output")
        logger.info(f"Source: {directory}")
        logger.info("Loading parquet files...")
        files = load_parquet_files(directory)

    logger.info("")
    logger.info("Running validation checks...")
    logger.info("-" * 40)

    result = validate(files)

    logger.info("")
    logger.info("=" * 60)
    passes, warns, fails = result.summary()
    logger.info(f"RESULTS: {passes} passed, {warns} warnings, {fails} failures")

    if fails > 0:
        logger.error("OVERALL: FAIL — Data integrity issues detected")
        sys.exit(1)
    elif warns > 0:
        logger.warning("OVERALL: PASS with warnings")
        sys.exit(0)
    else:
        logger.info("OVERALL: PASS — All checks passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
