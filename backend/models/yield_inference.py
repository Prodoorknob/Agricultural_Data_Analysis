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
    weather_df: pd.DataFrame | None = None,
    prism_normals: dict | None = None,
) -> int:
    """Run yield inference for a given crop/week, upsert results to DB.

    Builds the full feature set the model was trained on (NASS history +
    weather if the model expects it). If the model's feature_cols include
    weather columns and weather data is missing, inference is skipped for
    that (crop, week) rather than silently zero-filling — a degraded
    prediction is worse than no prediction for a published forecast.
    """
    model = load_model(crop, week)
    if model is None:
        logger.warning("No model for %s week %d. Skipping.", crop, week)
        return 0

    logger.info("Running inference for %s week %d year %d (model ver: %s, features: %s)",
                crop, week, crop_year, model.model_ver, model.feature_cols)

    weather_cols = {"gdd_ytd", "precip_season_in", "precip_deficit_in", "tmax_avg", "hot_days"}
    needs_weather = any(c in weather_cols for c in model.feature_cols)

    if nass_yields is None:
        from backend.models.train_yield import load_nass_county_yields
        commodity_nass = {"corn": "CORN", "soybean": "SOYBEANS", "wheat": "WHEAT"}[crop]
        nass_yields = load_nass_county_yields(commodity_nass, local_only=True)

    if nass_yields.empty:
        logger.warning("No NASS data available for inference")
        return 0

    county_fips = nass_yields["fips"].unique().tolist()

    wx_lookup = None
    if needs_weather:
        from backend.models.train_yield import (
            load_weather_data,
            load_prism_normals as _load_prism_normals,
            compute_weather_features,
        )
        if weather_df is None:
            weather_df = load_weather_data()
        if prism_normals is None:
            prism_normals = _load_prism_normals()

        if weather_df is None or weather_df.empty:
            logger.error(
                "Model %s week %d requires weather features but no weather data is available. "
                "Skipping inference rather than emitting degraded predictions.",
                crop, week,
            )
            return 0

        wx_features = compute_weather_features(
            weather_df, prism_normals or {}, crop, county_fips, range(crop_year, crop_year + 1), week,
        )
        if wx_features.empty:
            logger.error(
                "No weather features computed for %s week %d year %d — skipping inference.",
                crop, week, crop_year,
            )
            return 0
        wx_lookup = wx_features.set_index(["fips", "year"])
        logger.info("  Weather features computed for %d (fips, year) pairs", len(wx_features))

    confidence = YieldModel.confidence_tier(week)

    forecasts = []
    skipped_no_hist = 0
    skipped_no_weather = 0
    for fips in county_fips:
        county_hist = nass_yields[
            (nass_yields["fips"] == fips) & (nass_yields["year"] < crop_year)
        ]["yield_bu"]

        if len(county_hist) < 3:
            skipped_no_hist += 1
            continue

        feat = {
            "county_mean_yield": county_hist.mean(),
            "county_yield_trend": _compute_trend(county_hist),
            "prior_year_yield": county_hist.iloc[-1],
            "county_yield_std": county_hist.std(),
            "year": crop_year,
        }

        if needs_weather and wx_lookup is not None:
            if (fips, crop_year) not in wx_lookup.index:
                skipped_no_weather += 1
                continue
            wx_row = wx_lookup.loc[(fips, crop_year)]
            feat["gdd_ytd"] = wx_row["gdd_ytd"]
            feat["precip_season_in"] = wx_row["precip_season_in"]
            feat["precip_deficit_in"] = wx_row["precip_deficit_in"]
            feat["tmax_avg"] = wx_row["tmax_avg"]
            feat["hot_days"] = wx_row["hot_days"]

        missing = [c for c in model.feature_cols if c not in feat]
        if missing:
            logger.debug("FIPS %s missing features %s — skipping", fips, missing)
            continue

        feature_row = pd.DataFrame([feat])[model.feature_cols]

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

    if skipped_no_hist or skipped_no_weather:
        logger.info(
            "  Skipped: %d counties (insufficient history), %d counties (missing weather)",
            skipped_no_hist, skipped_no_weather,
        )

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

    # Load weather data once and share across (crop, week) inferences.
    # If unavailable, run_inference() will skip weather-dependent models cleanly.
    shared_weather = None
    shared_normals = None
    try:
        from backend.models.train_yield import load_weather_data, load_prism_normals
        shared_weather = load_weather_data()
        shared_normals = load_prism_normals()
    except Exception as exc:
        logger.warning("Could not preload weather data (will retry per-crop): %s", exc)

    for crop in crops:
        week = args.week or current_week_of_season(crop)
        if week <= 0:
            logger.info("Growing season not started for %s. Skipping.", crop)
            continue

        n = run_inference(
            crop, week, args.year,
            weather_df=shared_weather,
            prism_normals=shared_normals,
        )
        total += n

    elapsed = _time.time() - t0
    logger.info("Yield inference complete: %d rows in %.1f seconds", total, elapsed)
