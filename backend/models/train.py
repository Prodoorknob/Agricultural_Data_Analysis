"""Walk-forward training script for commodity price ensemble models.

Trains 18 model sets (3 commodities x 6 horizons) using features from RDS,
evaluates against a futures-curve baseline, and uploads artifacts to S3.

Usage:
    python -m backend.models.train                      # Train all
    python -m backend.models.train --commodity corn      # Train one commodity
    python -m backend.models.train --horizon 3           # Train one horizon
    python -m backend.models.train --local-only          # Skip S3 upload
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

from backend.etl.common import get_env, get_sync_session, setup_logging
from backend.features.price_features import build_training_features
from backend.models.db_tables import FuturesDaily
from backend.models.price_model import (
    LGBM_FEATURE_COLS,
    PriceEnsemble,
    _mape,
)

logger = setup_logging("train")

# Walk-forward configuration (from tech spec §5.4)
TRAIN_START = date(2010, 1, 1)
TRAIN_END = date(2019, 12, 31)
VAL_START = date(2020, 1, 1)
VAL_END = date(2022, 12, 31)
TEST_START = date(2023, 1, 1)
TEST_END = date(2024, 12, 31)

HORIZONS = [1, 2, 3, 4, 5, 6]
COMMODITIES = ["corn", "soybean", "wheat"]

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
S3_BUCKET = "usda-analysis-datasets"
S3_PREFIX = "models/price"

# Deployment gate: if model MAPE > futures MAPE + this, demote to signal-only mode
BASELINE_GATE_PP = 1.5


# ---------------------------------------------------------------------------
# Futures data loader (for target variable construction)
# ---------------------------------------------------------------------------


def _load_futures_df(commodity: str) -> pd.DataFrame:
    """Load all futures_daily rows for a commodity from RDS."""
    session = get_sync_session()
    try:
        rows = session.execute(
            select(
                FuturesDaily.trade_date,
                FuturesDaily.commodity,
                FuturesDaily.settlement,
            )
            .where(FuturesDaily.commodity == commodity)
            .order_by(FuturesDaily.trade_date)
        ).all()
    finally:
        session.close()

    if not rows:
        raise ValueError(f"No futures data found for {commodity}")

    df = pd.DataFrame(rows, columns=["trade_date", "commodity", "settlement"])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    # CME settlements are stored in cents/bu; convert to $/bu so targets match
    # the dollar-scale features produced by price_features.build_price_features.
    df["settlement"] = df["settlement"].astype(float) / 100.0
    return df


def _build_target(
    features_df: pd.DataFrame, futures_df: pd.DataFrame, horizon_months: int
) -> pd.Series:
    """Map each feature row to the realized price `horizon_months` later."""
    targets = []
    for _, row in features_df.iterrows():
        target_date = row["as_of_date"] + pd.DateOffset(months=horizon_months)
        mask = (
            (futures_df["commodity"] == row["commodity"])
            & (futures_df["trade_date"] >= target_date - pd.Timedelta(days=7))
            & (futures_df["trade_date"] <= target_date + pd.Timedelta(days=7))
        )
        matched = futures_df.loc[mask]
        if not matched.empty:
            idx = (matched["trade_date"] - target_date).abs().idxmin()
            targets.append(float(matched.loc[idx, "settlement"]))
        else:
            targets.append(np.nan)
    return pd.Series(targets, index=features_df.index, name="target_price")


def _futures_baseline_mape(
    features_df: pd.DataFrame, actuals: pd.Series
) -> float:
    """MAPE of using the current futures_spot as the forecast (naive baseline)."""
    preds = features_df["futures_spot"].astype(float).values
    valid = (~np.isnan(preds)) & (~np.isnan(actuals.values)) & (actuals.values != 0)
    if not valid.any():
        return 100.0
    return _mape(actuals.values[valid], preds[valid])


# ---------------------------------------------------------------------------
# Single model training
# ---------------------------------------------------------------------------


def train_single(
    commodity: str, horizon: int, local_only: bool = False,
    allow_failed_gate: bool = False,
) -> dict:
    """Train one PriceEnsemble for (commodity, horizon).

    Returns a summary dict with metrics and artifact path.

    Gate: if val MAPE > futures_baseline + BASELINE_GATE_PP, the artifact is
    written locally (for post-mortem analysis) but NOT uploaded to S3, and the
    returned dict has status='gate_failed'. Pass allow_failed_gate=True to
    override (e.g., deliberate benchmark runs).
    """
    logger.info("=== Training %s horizon=%d ===", commodity, horizon)

    # 1. Build features for train / val / test windows
    logger.info("Building training features (train window)...")
    X_train = build_training_features(
        commodity, TRAIN_START, TRAIN_END, horizon, freq_days=30
    )

    logger.info("Building validation features...")
    X_val = build_training_features(
        commodity, VAL_START, VAL_END, horizon, freq_days=30
    )

    logger.info("Building test features...")
    try:
        X_test = build_training_features(
            commodity, TEST_START, TEST_END, horizon, freq_days=30
        )
    except Exception as e:
        logger.warning("No test features built for %s h=%d: %s", commodity, horizon, e)
        X_test = None

    # 2. Load futures for target construction
    logger.info("Loading futures data for target construction...")
    futures_df = _load_futures_df(commodity)

    # 3. Build targets
    y_train = _build_target(X_train, futures_df, horizon)
    y_val = _build_target(X_val, futures_df, horizon)
    y_test = _build_target(X_test, futures_df, horizon) if X_test is not None else None

    # Drop rows where target is NaN (future data not yet available)
    train_valid = y_train.notna()
    val_valid = y_val.notna()

    X_train = X_train.loc[train_valid].reset_index(drop=True)
    y_train = y_train.loc[train_valid].reset_index(drop=True)
    X_val = X_val.loc[val_valid].reset_index(drop=True)
    y_val = y_val.loc[val_valid].reset_index(drop=True)

    if X_test is not None and y_test is not None:
        test_valid = y_test.notna()
        X_test = X_test.loc[test_valid].reset_index(drop=True)
        y_test = y_test.loc[test_valid].reset_index(drop=True)
        if len(X_test) == 0:
            X_test, y_test = None, None

    if len(X_train) < 10:
        logger.error(
            "Insufficient training data for %s h=%d: %d rows. Skipping.",
            commodity, horizon, len(X_train),
        )
        return {"commodity": commodity, "horizon": horizon, "status": "skipped", "reason": "insufficient_data"}

    if len(X_val) < 3:
        logger.warning(
            "Very small validation set for %s h=%d: %d rows.",
            commodity, horizon, len(X_val),
        )

    # 4. Fit ensemble
    ensemble = PriceEnsemble(commodity=commodity, horizon=horizon)
    metrics = ensemble.fit(X_train, y_train, X_val, y_val, X_test, y_test)

    # 5. Futures baseline comparison
    baseline_mape = _futures_baseline_mape(X_val, y_val)
    metrics.futures_baseline_mape = baseline_mape

    # Deployment gate check
    gate_passed = metrics.mape_val <= baseline_mape + BASELINE_GATE_PP
    if not gate_passed:
        logger.warning(
            "BASELINE GATE FAILED: %s h=%d model MAPE=%.2f%% > futures MAPE=%.2f%% + %.1fpp. "
            "Artifact will be written locally for analysis but NOT uploaded to S3 "
            "(pass --allow-failed-gate to override).",
            commodity, horizon, metrics.mape_val, baseline_mape, BASELINE_GATE_PP,
        )

    # 6. Save artifact locally (always — we want the post-mortem even on failure)
    artifact_dir = ARTIFACTS_DIR / commodity / f"horizon_{horizon}"
    artifact_path = artifact_dir / "ensemble.pkl"
    ensemble.save(artifact_path)

    metrics_dict = {
        "commodity": commodity,
        "horizon": horizon,
        "model_ver": ensemble.model_ver,
        "mape_train": round(metrics.mape_train, 4),
        "mape_val": round(metrics.mape_val, 4),
        "rmse_val": round(metrics.rmse_val, 4),
        "futures_baseline_mape": round(baseline_mape, 4),
        "gate_passed": gate_passed,
        "beats_baseline": gate_passed,  # kept for backward compat
        "coverage_90": round(metrics.coverage_90, 4),
        "conformity_offset": round(ensemble.conformity_offset, 4),
        "mape_test": round(metrics.mape_test, 4),
        "rmse_test": round(metrics.rmse_test, 4),
        "coverage_90_test": round(metrics.coverage_90_test, 4),
        "n_train": metrics.n_train,
        "n_val": metrics.n_val,
        "n_test": metrics.n_test,
    }
    metrics_path = artifact_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics_dict, f, indent=2)

    # 7. Upload to S3 only if the gate passed (or override)
    upload_blocked_by_gate = (not gate_passed) and (not allow_failed_gate)
    if upload_blocked_by_gate:
        logger.warning(
            "S3 upload BLOCKED for %s h=%d — gate failed. Artifact retained at %s",
            commodity, horizon, artifact_path,
        )
        status = "gate_failed"
    elif local_only:
        status = "trained"
    else:
        _upload_to_s3(artifact_path, commodity, horizon)
        _upload_to_s3(metrics_path, commodity, horizon)
        status = "trained"

    logger.info(
        "Completed %s h=%d — MAPE_val=%.2f%%, baseline=%.2f%%, gate_passed=%s, status=%s",
        commodity, horizon, metrics.mape_val, baseline_mape, gate_passed, status,
    )
    return {**metrics_dict, "status": status, "artifact_path": str(artifact_path)}


# ---------------------------------------------------------------------------
# S3 upload
# ---------------------------------------------------------------------------


def _upload_to_s3(local_path: Path, commodity: str, horizon: int) -> None:
    """Upload a single artifact file to S3, plus its .sig sidecar if present."""
    try:
        import boto3

        s3 = boto3.client("s3", region_name="us-east-2")
        s3_key = f"{S3_PREFIX}/{commodity}/horizon_{horizon}/{local_path.name}"

        sig_path = local_path.with_suffix(local_path.suffix + ".sig")
        if sig_path.exists():
            try:
                s3.upload_file(str(sig_path), S3_BUCKET, s3_key + ".sig")
            except Exception as sig_exc:
                logger.warning("Signature upload failed for %s: %s", sig_path, sig_exc)
        s3.upload_file(str(local_path), S3_BUCKET, s3_key)
        logger.info("Uploaded %s -> s3://%s/%s", local_path.name, S3_BUCKET, s3_key)
    except Exception as e:
        logger.warning("S3 upload failed for %s: %s", local_path, e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def train_all(
    commodities: list[str] | None = None,
    horizons: list[int] | None = None,
    local_only: bool = False,
    allow_failed_gate: bool = False,
) -> list[dict]:
    """Train all requested (commodity, horizon) combinations.

    Returns list of summary dicts.
    """
    commodities = commodities or COMMODITIES
    horizons = horizons or HORIZONS

    results = []
    total = len(commodities) * len(horizons)
    for i, commodity in enumerate(commodities):
        for j, horizon in enumerate(horizons):
            n = i * len(horizons) + j + 1
            logger.info("--- [%d/%d] %s horizon=%d ---", n, total, commodity, horizon)
            try:
                result = train_single(
                    commodity, horizon,
                    local_only=local_only,
                    allow_failed_gate=allow_failed_gate,
                )
                results.append(result)
            except Exception as e:
                logger.error(
                    "Failed to train %s h=%d: %s", commodity, horizon, e,
                    exc_info=True,
                )
                results.append({
                    "commodity": commodity,
                    "horizon": horizon,
                    "status": "error",
                    "error": str(e),
                })

    # Summary
    trained = sum(1 for r in results if r.get("status") == "trained")
    gate_failed = sum(1 for r in results if r.get("status") == "gate_failed")
    failed = sum(1 for r in results if r.get("status") == "error")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    logger.info(
        "Training complete: %d trained, %d gate-failed (not uploaded), %d skipped, %d errored out of %d total",
        trained, gate_failed, skipped, failed, total,
    )

    # Save overall summary
    summary_path = ARTIFACTS_DIR / "training_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("Summary saved to %s", summary_path)

    return results


def main():
    parser = argparse.ArgumentParser(description="Train commodity price ensemble models")
    parser.add_argument("--commodity", type=str, choices=COMMODITIES, help="Train single commodity")
    parser.add_argument("--horizon", type=int, choices=HORIZONS, help="Train single horizon")
    parser.add_argument("--local-only", action="store_true", help="Skip S3 upload")
    parser.add_argument(
        "--allow-failed-gate",
        action="store_true",
        help="Upload artifacts to S3 even if the baseline gate fails (default: block upload)",
    )
    args = parser.parse_args()

    commodities = [args.commodity] if args.commodity else None
    horizons = [args.horizon] if args.horizon else None

    results = train_all(
        commodities=commodities,
        horizons=horizons,
        local_only=args.local_only,
        allow_failed_gate=args.allow_failed_gate,
    )

    # Exit with error code if any failures
    if any(r.get("status") == "error" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
