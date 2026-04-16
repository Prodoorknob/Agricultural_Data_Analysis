"""Training script for planted acreage prediction models (Module 03).

Downloads state-level NASS data from S3, merges with historical 1990-2000
data, and trains state-panel AcreageEnsemble models for corn, soybean, wheat.

Usage:
    python -m backend.models.train_acreage
    python -m backend.models.train_acreage --commodity corn --skip-cv
    python -m backend.models.train_acreage --fetch-historical
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from backend.etl.common import setup_logging
from backend.features.acreage_features import COMMODITY_NASS_MAP, TOP_STATES
from backend.models.acreage_model import train_and_save

logger = setup_logging("train_acreage")

S3_BUCKET = "usda-analysis-datasets"
S3_PREFIX = "survey_datasets/partitioned_states"

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "acreage"
CACHE_DIR = Path(__file__).resolve().parent.parent / "etl" / "data" / "nass_cache"
HISTORICAL_CSV = CACHE_DIR / "nass_historical_1990_2000.csv"

# State alpha to FIPS mapping
STATE_ALPHA_TO_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13",
    "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24",
    "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29",
    "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34",
    "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45",
    "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50",
    "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56",
}


def download_state_parquets(cache_dir: Path) -> Path:
    """Sync state parquets from S3 to local cache."""
    local_dir = cache_dir / "state_parquets"
    local_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Syncing state parquets from s3://{S3_BUCKET}/{S3_PREFIX}/ ...")
    subprocess.run(
        [
            "aws", "s3", "sync",
            f"s3://{S3_BUCKET}/{S3_PREFIX}/",
            str(local_dir),
            "--region", "us-east-2",
            "--exclude", "*",
            "--include", "*.parquet",
        ],
        check=True,
    )
    logger.info(f"Downloaded to {local_dir}")
    return local_dir


def build_nass_dataframe(parquet_dir: Path) -> pd.DataFrame:
    """Extract NASS acreage + yield data from state parquets.

    Returns DataFrame with columns:
        state_fips, commodity, year, acres_planted, yield_bu
    Including national totals (state_fips='00').
    """
    all_dfs = []
    for f in sorted(parquet_dir.glob("*.parquet")):
        state_alpha = f.stem
        if state_alpha not in STATE_ALPHA_TO_FIPS:
            continue
        df = pd.read_parquet(f)
        df["_state_fips"] = STATE_ALPHA_TO_FIPS[state_alpha]
        all_dfs.append(df)

    if not all_dfs:
        raise FileNotFoundError(f"No valid parquets found in {parquet_dir}")

    raw = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"Loaded {len(raw):,} raw NASS records from {len(all_dfs)} states")

    records = []
    nass_to_our = {v: k for k, v in COMMODITY_NASS_MAP.items()}

    for nass_name, our_name in nass_to_our.items():
        # --- Area planted (ALL CLASSES only to avoid double-counting) ---
        planted = raw[
            (raw["commodity_desc"] == nass_name)
            & (raw["class_desc"] == "ALL CLASSES")
            & (raw["statisticcat_desc"] == "AREA PLANTED")
            & (raw["unit_desc"] == "ACRES")
            & (raw["domain_desc"] == "TOTAL")
            & (raw["prodn_practice_desc"] == "ALL PRODUCTION PRACTICES")
            & (raw["reference_period_desc"] == "YEAR")
        ][["_state_fips", "year", "value_num"]].rename(
            columns={"value_num": "acres_planted"}
        )

        # --- Yield (grain, BU / ACRE, ALL CLASSES) ---
        yields = raw[
            (raw["commodity_desc"] == nass_name)
            & (raw["class_desc"] == "ALL CLASSES")
            & (raw["statisticcat_desc"] == "YIELD")
            & (raw["unit_desc"] == "BU / ACRE")
            & (raw["domain_desc"] == "TOTAL")
            & (raw["prodn_practice_desc"] == "ALL PRODUCTION PRACTICES")
            & (raw["reference_period_desc"] == "YEAR")
        ][["_state_fips", "year", "value_num"]].rename(
            columns={"value_num": "yield_bu"}
        )

        # Merge planted + yield
        merged = planted.merge(yields, on=["_state_fips", "year"], how="left")
        merged["commodity"] = our_name
        merged.rename(columns={"_state_fips": "state_fips"}, inplace=True)
        records.append(merged)

        logger.info(
            f"  {our_name}: {len(planted)} planted records, "
            f"{len(yields)} yield records, {len(merged)} merged"
        )

    df = pd.concat(records, ignore_index=True)

    # Add national totals
    df = _add_national_totals(df)

    # Validate
    df = df.dropna(subset=["acres_planted"])
    df = df[df["acres_planted"] > 0]

    logger.info(
        f"Final NASS dataset: {len(df)} rows, "
        f"years {df['year'].min()}-{df['year'].max()}, "
        f"commodities: {sorted(df['commodity'].unique())}"
    )
    return df[["state_fips", "commodity", "year", "acres_planted", "yield_bu"]]


def _add_national_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute national totals (state_fips='00') by summing state values."""
    state_only = df[df["state_fips"] != "00"]
    national = (
        state_only.groupby(["commodity", "year"])
        .agg(acres_planted=("acres_planted", "sum"), yield_bu=("yield_bu", "mean"))
        .reset_index()
    )
    national["state_fips"] = "00"
    return pd.concat([df[df["state_fips"] != "00"], national], ignore_index=True)


def _merge_historical(nass_data: pd.DataFrame) -> pd.DataFrame:
    """Merge historical 1990-2000 data with existing 2001-2025 data."""
    if not HISTORICAL_CSV.exists():
        logger.info("No historical CSV found — skipping merge")
        return nass_data

    hist = pd.read_csv(HISTORICAL_CSV, dtype={"state_fips": str})
    logger.info(f"Loaded {len(hist)} historical records ({hist['year'].min()}-{hist['year'].max()})")

    # Concat and deduplicate
    combined = pd.concat([hist, nass_data], ignore_index=True)
    combined = combined.drop_duplicates(subset=["state_fips", "commodity", "year"], keep="last")

    # Recompute national totals for the full range
    combined = combined[combined["state_fips"] != "00"]
    combined = _add_national_totals(combined)

    combined = combined.dropna(subset=["acres_planted"])
    combined = combined[combined["acres_planted"] > 0]

    logger.info(
        f"Merged dataset: {len(combined)} rows, "
        f"years {combined['year'].min()}-{combined['year'].max()}"
    )
    return combined[["state_fips", "commodity", "year", "acres_planted", "yield_bu"]]


# Per-commodity residual configuration
# Absolute targets for corn; 3yr avg residual for soybean and wheat splits
RESIDUAL_CONFIG = {
    "corn":         {"use_residual": False, "residual_col": "prior_year_acres"},
    "soybean":      {"use_residual": True,  "residual_col": "prior_3yr_avg_acres"},
    "wheat":        {"use_residual": True,  "residual_col": "prior_3yr_avg_acres"},
    "wheat_winter": {"use_residual": True,  "residual_col": "prior_3yr_avg_acres"},
    "wheat_spring": {"use_residual": True,  "residual_col": "prior_3yr_avg_acres"},
}


def train_commodity(
    commodity: str,
    nass_data: pd.DataFrame,
    output_dir: Path,
    run_cv: bool = True,
    persist_accuracy: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Train and save model for one commodity using state-panel data.

    Returns (predictions_df, metrics) — predictions_df has val+test rows for
    acreage_accuracy persistence; metrics carries beats_baseline for the
    caller's gate check on S3 upload.
    """
    logger.info(f"=== Training {commodity} acreage model (state-panel) ===")

    states = TOP_STATES.get(commodity, ["00"])

    # Map wheat_winter/wheat_spring to NASS "wheat" for data filtering
    nass_commodity = commodity.split("_")[0] if "_" in commodity else commodity

    # Per-commodity residual config
    res_cfg = RESIDUAL_CONFIG.get(commodity, {"use_residual": False, "residual_col": "prior_year_acres"})

    # Determine year range from data availability
    commodity_data = nass_data[
        (nass_data["commodity"] == nass_commodity)
        & (nass_data["state_fips"].isin(states))
    ]
    min_year = int(commodity_data["year"].min())
    feature_start = max(min_year + 5, 1995)

    train_years = range(feature_start, 2021)
    val_years = range(2021, 2024)
    test_years = [2024, 2025]

    logger.info(
        f"  States: {len(states)}, Train: {feature_start}-2020, "
        f"Val: 2021-2023, Test: 2024-2025, "
        f"residual={res_cfg['use_residual']} ({res_cfg['residual_col']})"
    )

    ensemble, metrics, predictions_df = train_and_save(
        commodity=commodity,
        nass_data=nass_data,
        output_dir=output_dir,
        states=states,
        train_years=train_years,
        val_years=val_years,
        test_years=test_years,
        run_cv=run_cv,
        use_residual=res_cfg["use_residual"],
        residual_col=res_cfg["residual_col"],
    )

    # Summary
    logger.info(
        f"  Results — Val MAPE: {metrics.get('val_mape', '?')}%, "
        f"Test MAPE: {metrics.get('test_mape', '?')}%, "
        f"Baseline: {metrics.get('best_baseline_mape', '?')}%, "
        f"Beats: {metrics.get('beats_baseline', '?')}, "
        f"Coverage: val={metrics.get('coverage_80_val', '?')}, "
        f"test={metrics.get('coverage_80_test', '?')}"
    )

    # Persist walk-forward predictions to acreage_accuracy (§7.4 WI-1)
    if persist_accuracy and not predictions_df.empty:
        try:
            n = persist_acreage_accuracy(predictions_df, model_ver=metrics["model_ver"])
            logger.info(f"  Persisted {n} rows to acreage_accuracy")
        except Exception as exc:
            logger.error(f"  Failed to persist acreage accuracy: {exc}")

    return predictions_df, metrics


def persist_acreage_accuracy(predictions_df: pd.DataFrame, model_ver: str) -> int:
    """Upsert walk-forward acreage predictions into acreage_accuracy table.

    Computes model_vs_actual_pct for rows where actual is known.
    The usda_prospective column is left null — populated separately by
    backend/etl/ingest_prospective_plantings.py.

    Returns number of rows upserted.
    """
    from sqlalchemy.dialects.postgresql import insert
    from backend.etl.common import get_sync_session
    from backend.models.db_tables import AcreageAccuracy

    if predictions_df.empty:
        return 0

    rows = []
    for _, row in predictions_df.iterrows():
        actual = float(row["actual"])
        forecast = float(row["model_p50"])
        # model_vs_actual_pct: (forecast - actual) / actual * 100
        pct_err = round((forecast - actual) / actual * 100, 2) if actual != 0 else None
        rows.append({
            "forecast_year": int(row["forecast_year"]),
            "state_fips": str(row["state_fips"]),
            "commodity": str(row["commodity"]),
            "model_forecast": forecast,
            "usda_june_actual": actual,
            "model_vs_actual_pct": pct_err,
            # usda_prospective and model_vs_usda_pct filled by Prospective Plantings ETL
        })

    session = get_sync_session()
    try:
        stmt = insert(AcreageAccuracy.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_acreage_accuracy",
            set_={
                "model_forecast": stmt.excluded.model_forecast,
                "usda_june_actual": stmt.excluded.usda_june_actual,
                "model_vs_actual_pct": stmt.excluded.model_vs_actual_pct,
                "updated_at": datetime.utcnow(),
            },
        )
        result = session.execute(stmt)
        session.commit()
        return result.rowcount
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Train acreage prediction models")
    parser.add_argument(
        "--commodity",
        choices=["corn", "soybean", "wheat", "all"],
        default="all",
        help="Commodity to train (default: all)",
    )
    parser.add_argument(
        "--local-only",
        action="store_true",
        help="Skip S3 download, use cached data",
    )
    parser.add_argument(
        "--fetch-historical",
        action="store_true",
        help="Run historical NASS fetch (1990-2000) before training",
    )
    parser.add_argument(
        "--skip-cv",
        action="store_true",
        help="Skip leave-one-year-out CV (faster)",
    )
    parser.add_argument(
        "--upload-s3",
        action="store_true",
        help="Upload artifacts to S3 after training",
    )
    parser.add_argument(
        "--persist-accuracy",
        action="store_true",
        help="Upsert walk-forward val+test predictions to acreage_accuracy table",
    )
    parser.add_argument(
        "--allow-failed-gate",
        action="store_true",
        help="Upload gate-failed commodities to S3 anyway (default: exclude from upload)",
    )
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    nass_csv = CACHE_DIR / "nass_acreage_yield.csv"

    # Optional: fetch historical data
    if args.fetch_historical:
        logger.info("Fetching historical NASS data (1990-2000) ...")
        subprocess.run(
            [sys.executable, "pipeline/fetch_nass_historical.py"],
            check=True,
        )

    # Step 1: Load NASS data
    if args.local_only and nass_csv.exists():
        logger.info(f"Loading cached NASS data from {nass_csv}")
        nass_data = pd.read_csv(nass_csv, dtype={"state_fips": str})
    else:
        parquet_dir = download_state_parquets(CACHE_DIR)
        nass_data = build_nass_dataframe(parquet_dir)

    # Step 2: Merge historical data
    nass_data = _merge_historical(nass_data)
    nass_data.to_csv(nass_csv, index=False)
    logger.info(f"Cached NASS data to {nass_csv}")

    # Step 3: Train
    if args.commodity == "all":
        commodities = ["corn", "soybean", "wheat_winter", "wheat_spring"]
    elif args.commodity == "wheat":
        commodities = ["wheat_winter", "wheat_spring"]
    else:
        commodities = [args.commodity]

    gate_status: dict[str, bool] = {}
    for commodity in commodities:
        _, metrics = train_commodity(
            commodity,
            nass_data,
            ARTIFACT_DIR,
            run_cv=not args.skip_cv,
            persist_accuracy=args.persist_accuracy,
        )
        gate_status[commodity] = bool(metrics.get("beats_baseline", False))

    # Step 4: Optional S3 upload — gate-failed commodities are excluded unless overridden
    if args.upload_s3:
        failed = [c for c, passed in gate_status.items() if not passed]
        if failed and not args.allow_failed_gate:
            logger.warning(
                "S3 upload: excluding gate-failed commodities: %s "
                "(override with --allow-failed-gate)",
                ", ".join(failed),
            )
            exclude_args: list[str] = []
            for c in failed:
                exclude_args += ["--exclude", f"{c}/*"]
        else:
            if failed:
                logger.warning(
                    "S3 upload: uploading gate-failed commodities anyway due to --allow-failed-gate: %s",
                    ", ".join(failed),
                )
            exclude_args = []

        logger.info("Uploading artifacts to S3 ...")
        subprocess.run(
            [
                "aws", "s3", "sync",
                str(ARTIFACT_DIR),
                f"s3://{S3_BUCKET}/models/acreage/",
                "--region", "us-east-2",
                *exclude_args,
            ],
            check=True,
        )
        logger.info("Uploaded to S3")

    logger.info(
        "All done. Gate summary: %s",
        ", ".join(f"{c}={'PASS' if p else 'FAIL'}" for c, p in gate_status.items()),
    )


if __name__ == "__main__":
    main()
