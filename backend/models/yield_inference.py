"""Weekly yield inference — loads trained models, predicts for all counties, upserts to DB.

Usage:
    python -m backend.models.yield_inference
    python -m backend.models.yield_inference --crop corn --week 15 --year 2026
"""

import argparse
import time as _time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary
from backend.features.yield_features import PLANTING_DOY
from backend.models.db_tables import YieldForecast
from backend.models.yield_model import YieldModel

logger = setup_logging("yield_inference")

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts" / "yield"
COMMODITIES = ["corn", "soybean", "wheat"]


def _py(val) -> float:
    """Convert numpy types to Python float, rounded to 1 decimal."""
    if val is None:
        return 0.0
    return round(float(val), 1)


def current_week_of_season(crop: str, ref_date: date | None = None) -> int:
    """Compute current week of growing season for a given crop."""
    if ref_date is None:
        ref_date = date.today()

    planting_doy = PLANTING_DOY.get(crop, 110)
    planting_date = date(ref_date.year, 1, 1) + timedelta(days=planting_doy - 1)
    days_since = (ref_date - planting_date).days

    if days_since < 0:
        return 0
    return min(days_since // 7 + 1, 20)


def load_model(crop: str, week: int) -> YieldModel | None:
    """Load a trained YieldModel from local artifacts or S3."""
    pkl_path = ARTIFACTS_DIR / crop / f"week_{week}" / "model.pkl"

    # Try local first
    if pkl_path.exists():
        try:
            return YieldModel.load(pkl_path)
        except Exception as exc:
            logger.warning("Failed to load local model %s: %s", pkl_path, exc)

    # Fallback to S3
    try:
        import boto3
        from backend.config import get_settings
        settings = get_settings()

        s3 = boto3.client("s3", region_name=settings.AWS_REGION)
        s3_key = f"models/yield/{crop}/week_{week}/model.pkl"
        pkl_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(settings.S3_BUCKET, s3_key, str(pkl_path))
        logger.info("Downloaded model from s3://%s/%s", settings.S3_BUCKET, s3_key)
        return YieldModel.load(pkl_path)
    except Exception as exc:
        logger.warning("No model available for %s week %d: %s", crop, week, exc)
        return None


def run_inference(
    crop: str,
    week: int,
    crop_year: int,
    nass_yields: pd.DataFrame | None = None,
) -> int:
    """Run yield inference for a given crop/week, upsert results to DB."""
    model = load_model(crop, week)
    if model is None:
        logger.warning("No model for %s week %d. Skipping.", crop, week)
        return 0

    logger.info("Running inference for %s week %d year %d (model ver: %s)",
                crop, week, crop_year, model.model_ver)

    # Build features for all counties
    # For now, use the same NASS-derived features used in training
    if nass_yields is None:
        from backend.models.train_yield import load_nass_county_yields
        commodity_nass = {"corn": "CORN", "soybean": "SOYBEANS", "wheat": "WHEAT"}[crop]
        nass_yields = load_nass_county_yields(commodity_nass, local_only=True)

    if nass_yields.empty:
        logger.warning("No NASS data available for inference")
        return 0

    # Get unique counties that have data
    county_fips = nass_yields["fips"].unique()
    confidence = YieldModel.confidence_tier(week)

    forecasts = []
    for fips in county_fips:
        county_hist = nass_yields[
            (nass_yields["fips"] == fips) & (nass_yields["year"] < crop_year)
        ]["yield_bu"]

        if len(county_hist) < 3:
            continue

        # Build feature row matching training features
        feature_row = pd.DataFrame([{
            "county_mean_yield": county_hist.mean(),
            "county_yield_trend": _compute_trend(county_hist),
            "prior_year_yield": county_hist.iloc[-1],
            "county_yield_std": county_hist.std(),
            "year": crop_year,
        }])

        # Only use features the model was trained on
        available = [c for c in model.feature_cols if c in feature_row.columns]
        if not available:
            continue

        feature_row = feature_row[available]

        try:
            pred = model.predict(feature_row)
        except Exception as exc:
            logger.debug("Prediction failed for FIPS %s: %s", fips, exc)
            continue

        forecasts.append({
            "fips": fips,
            "crop": crop,
            "crop_year": crop_year,
            "week": week,
            "p10": _py(pred["p10"]),
            "p50": _py(pred["p50"]),
            "p90": _py(pred["p90"]),
            "confidence": confidence,
            "model_ver": model.model_ver,
        })

    # Upsert to DB
    if not forecasts:
        logger.warning("No forecasts generated for %s week %d", crop, week)
        return 0

    session = get_sync_session()
    count = 0
    try:
        for fc in forecasts:
            stmt = pg_insert(YieldForecast).values(**fc)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_yield_forecasts",
                set_={
                    "p10": fc["p10"],
                    "p50": fc["p50"],
                    "p90": fc["p90"],
                    "confidence": fc["confidence"],
                },
            )
            session.execute(stmt)
            count += 1

        session.commit()
        logger.info("Upserted %d yield forecasts for %s week %d", count, crop, week)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return count


def _compute_trend(series: pd.Series) -> float:
    """Compute simple linear trend (slope)."""
    if len(series) < 3:
        return 0.0
    x = np.arange(len(series))
    try:
        return round(float(np.polyfit(x, series.values, 1)[0]), 2)
    except (np.linalg.LinAlgError, ValueError):
        return 0.0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run yield inference")
    parser.add_argument("--crop", default="all", help="corn|soybean|wheat|all")
    parser.add_argument("--week", type=int, help="Week of season (auto-detected if omitted)")
    parser.add_argument("--year", type=int, default=date.today().year, help="Crop year")
    args = parser.parse_args()

    t0 = _time.time()
    total = 0

    crops = COMMODITIES if args.crop == "all" else [args.crop]

    for crop in crops:
        week = args.week or current_week_of_season(crop)
        if week <= 0:
            logger.info("Growing season not started for %s. Skipping.", crop)
            continue

        n = run_inference(crop, week, args.year)
        total += n

    elapsed = _time.time() - t0
    logger.info("Yield inference complete: %d rows in %.1f seconds", total, elapsed)
