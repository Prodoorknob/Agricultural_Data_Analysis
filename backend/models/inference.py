"""Run inference for all commodity/horizon combos and persist forecasts to RDS.

Called by cron_runner.sh after WASDE ingest to refresh predictions.

Usage:
    python -m backend.models.inference
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from backend.etl.common import get_sync_session, setup_logging
from backend.features.price_features import build_price_features
from backend.models.price_model import PriceEnsemble

logger = setup_logging("inference")

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
COMMODITIES = ["corn", "soybean", "wheat"]
HORIZONS = [1, 2, 3, 4, 5, 6]


def _load_ensemble(commodity: str, horizon: int) -> PriceEnsemble | None:
    """Load ensemble from local artifacts (S3 download handled by main.py at serve time)."""
    pkl_path = ARTIFACTS_DIR / commodity / f"horizon_{horizon}" / "ensemble.pkl"
    if not pkl_path.exists():
        # Try S3 fallback
        try:
            import boto3
            from botocore.exceptions import ClientError

            s3 = boto3.client("s3", region_name="us-east-2")
            s3_key = f"models/price/{commodity}/horizon_{horizon}/ensemble.pkl"
            pkl_path.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file("usda-analysis-datasets", s3_key, str(pkl_path))
            logger.info("Downloaded from S3: %s", s3_key)
        except Exception as exc:
            logger.warning("No model for %s h=%d (local or S3): %s", commodity, horizon, exc)
            return None

    try:
        return PriceEnsemble.load(pkl_path)
    except Exception as exc:
        logger.warning("Failed to load %s: %s", pkl_path, exc)
        return None


def run_inference() -> int:
    """Run predictions for all combos and upsert to price_forecasts table."""
    today = date.today()
    success_count = 0
    error_count = 0

    with get_sync_session() as session:
        for commodity in COMMODITIES:
            for horizon in HORIZONS:
                ensemble = _load_ensemble(commodity, horizon)
                if ensemble is None:
                    continue

                try:
                    features = build_price_features(commodity, today, horizon)
                    result = ensemble.predict(features)

                    target_date = pd.Timestamp.today() + pd.DateOffset(months=horizon)
                    horizon_month = target_date.strftime("%Y-%m")

                    # Upsert forecast
                    session.execute(
                        text("""
                            INSERT INTO price_forecasts
                                (commodity, run_date, horizon_month, p10, p50, p90,
                                 key_driver, divergence_flag, regime_anomaly, model_ver)
                            VALUES
                                (:commodity, :run_date, :horizon_month, :p10, :p50, :p90,
                                 :key_driver, :divergence_flag, :regime_anomaly, :model_ver)
                            ON CONFLICT (commodity, run_date, horizon_month)
                            DO UPDATE SET
                                p10 = EXCLUDED.p10, p50 = EXCLUDED.p50, p90 = EXCLUDED.p90,
                                key_driver = EXCLUDED.key_driver,
                                divergence_flag = EXCLUDED.divergence_flag,
                                regime_anomaly = EXCLUDED.regime_anomaly,
                                model_ver = EXCLUDED.model_ver
                        """),
                        {
                            "commodity": commodity,
                            "run_date": today,
                            "horizon_month": horizon_month,
                            "p10": round(result["p10"], 4),
                            "p50": round(result["p50"], 4),
                            "p90": round(result["p90"], 4),
                            "key_driver": result.get("key_driver"),
                            "divergence_flag": result.get("divergence_flag", False),
                            "regime_anomaly": result.get("regime_anomaly", False),
                            "model_ver": ensemble.model_ver,
                        },
                    )
                    session.commit()
                    success_count += 1
                    logger.info(
                        "Forecast: %s h=%d -> p50=%.2f [%s]",
                        commodity, horizon, result["p50"], horizon_month,
                    )
                except Exception as exc:
                    error_count += 1
                    logger.error("Inference failed for %s h=%d: %s", commodity, horizon, exc)

    logger.info("Inference complete: %d succeeded, %d failed", success_count, error_count)
    return 1 if error_count > 0 and success_count == 0 else 0


if __name__ == "__main__":
    sys.exit(run_inference())
