"""Training script for crop yield prediction models — with weather features.

Trains 60 LightGBM quantile models (3 crops × 20 weeks).
Integrates GHCN daily weather data to compute week-specific GDD and precip deficit,
combined with NASS historical yield features.

Features per (fips, year, week):
  - county_mean_yield   (NASS historical)
  - county_yield_trend  (NASS historical)
  - prior_year_yield    (NASS prior year)
  - county_yield_std    (NASS variability)
  - year                (trend capture)
  - gdd_ytd             (weather: accumulated growing degree days through week W)
  - precip_season_in    (weather: total precip from planting through week W)
  - precip_deficit_in   (weather: actual - normal precip)
  - tmax_avg            (weather: avg daily max temp during growing season)
  - hot_days            (weather: days with tmax > 95°F, heat stress proxy)

Usage:
    python -m backend.models.train_yield
    python -m backend.models.train_yield --commodity corn --week 15 --skip-cv
    python -m backend.models.train_yield --upload-s3
"""

import argparse
import csv
import json
import os
import time as _time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from backend.etl.common import setup_logging
from backend.models.yield_model import YieldModel, compute_baselines, compute_rrmse

logger = setup_logging("train_yield")

ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts" / "yield"
LOCAL_DATA_DIR = Path(__file__).parent.parent / "etl" / "data"
NASS_CACHE_DIR = LOCAL_DATA_DIR / "nass_cache"
GHCN_PATH = LOCAL_DATA_DIR / "ghcn_processed" / "county_weather_2000_2025.parquet"
PRISM_PATH = LOCAL_DATA_DIR / "prism_normals.csv"

COMMODITIES = {"corn": "CORN", "soybean": "SOYBEANS", "wheat": "WHEAT"}
WEEKS = range(1, 21)  # 20 weeks of growing season

# Planting day-of-year by crop (from yield_features.py)
PLANTING_DOY = {"corn": 110, "soybean": 125, "wheat": 60}

# Training periods
TRAIN_END = 2019
VAL_START, VAL_END = 2020, 2022
TEST_START, TEST_END = 2023, 2024

# Baseline gate: model must beat county historical mean by >=10% relative improvement
BASELINE_GATE_PCT = 10.0


# ---- Data loaders ----

def load_nass_county_yields(
    commodity_nass: str,
    local_only: bool = False,
) -> pd.DataFrame:
    """Load county-level NASS yield data from parquet files."""
    cache_path = NASS_CACHE_DIR / f"{commodity_nass.lower()}_county_yields.csv"
    if cache_path.exists():
        logger.info("Loading cached county yields from %s", cache_path)
        df = pd.read_csv(cache_path, dtype={"fips": str, "state_fips": str})
        return df

    if not local_only:
        _download_county_parquets()

    all_rows = []
    parquet_dir = LOCAL_DATA_DIR / "county_parquets"

    if not parquet_dir.exists():
        logger.error("County parquet directory not found at %s", parquet_dir)
        return pd.DataFrame()

    for pq_file in sorted(parquet_dir.glob("*.parquet")):
        if pq_file.name.startswith("_"):
            continue
        try:
            df = pd.read_parquet(pq_file)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", pq_file, exc)
            continue

        # Wheat uses class_desc='WINTER'/'SPRING', others use 'ALL CLASSES'
        class_filter = (
            df["class_desc"].isin(["ALL CLASSES", "WINTER", "SPRING, (EXCL DURUM)"])
            if commodity_nass == "WHEAT"
            else (df["class_desc"] == "ALL CLASSES")
        )
        yield_df = df[
            (df["agg_level_desc"] == "COUNTY") &
            (df["statisticcat_desc"] == "YIELD") &
            (df["commodity_desc"] == commodity_nass) &
            class_filter &
            (df["unit_desc"].str.contains("BU / ACRE", case=False, na=False)) &
            (df["domain_desc"] == "TOTAL") &
            (df["freq_desc"] == "ANNUAL")
        ].copy()

        if yield_df.empty:
            continue

        yield_df["fips"] = (
            yield_df["state_fips_code"].astype(str).str.zfill(2) +
            yield_df["county_code"].astype(str).str.zfill(3)
        )

        for _, row in yield_df.iterrows():
            try:
                val = float(str(row.get("value_num", row.get("Value", ""))).replace(",", ""))
            except (ValueError, TypeError):
                continue
            if val <= 0 or np.isnan(val):
                continue
            all_rows.append({
                "fips": row["fips"],
                "year": int(row["year"]),
                "yield_bu": val,
                "state_fips": row["fips"][:2],
            })

    result = pd.DataFrame(all_rows).drop_duplicates(subset=["fips", "year"], keep="last")
    logger.info("Loaded %d county yield records for %s", len(result), commodity_nass)

    NASS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(cache_path, index=False)
    return result


def _download_county_parquets():
    """Download county parquets from S3."""
    import subprocess
    dest = LOCAL_DATA_DIR / "county_parquets"
    dest.mkdir(parents=True, exist_ok=True)
    s3_prefix = "s3://usda-analysis-datasets/survey_datasets/partitioned_states_counties/"
    logger.info("Syncing county parquets from S3...")
    try:
        subprocess.run(["aws", "s3", "sync", s3_prefix, str(dest), "--quiet"],
                       check=True, timeout=300)
        logger.info("S3 sync complete to %s", dest)
    except Exception as exc:
        logger.warning("S3 sync failed: %s", exc)


def load_weather_data() -> pd.DataFrame:
    """Load GHCN daily weather data (16M rows, ~1s)."""
    if not GHCN_PATH.exists():
        logger.warning("GHCN weather data not found at %s", GHCN_PATH)
        return pd.DataFrame()
    t0 = _time.time()
    df = pd.read_parquet(GHCN_PATH)
    logger.info("Loaded GHCN weather: %d rows in %.1fs", len(df), _time.time() - t0)
    return df


def load_prism_normals() -> dict[tuple[str, int], float]:
    """Load PRISM monthly precipitation normals. Returns {(fips, month): precip_in}."""
    if not PRISM_PATH.exists():
        logger.warning("PRISM normals not found at %s", PRISM_PATH)
        return {}
    result = {}
    with open(PRISM_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[(row["fips"], int(row["month"]))] = float(row["precip_normal_in"])
    logger.info("Loaded PRISM normals: %d entries", len(result))
    return result


# ---- Weather feature computation ----

def compute_weather_features(
    weather_df: pd.DataFrame,
    prism_normals: dict,
    crop: str,
    fips_list: list[str],
    year_range: range,
    week: int,
) -> pd.DataFrame:
    """Compute weather features for all (fips, year) at a given week.

    Returns DataFrame with columns: fips, year, gdd_ytd, precip_season_in,
    precip_deficit_in, tmax_avg, hot_days.
    """
    if weather_df.empty:
        return pd.DataFrame()

    planting_doy = PLANTING_DOY.get(crop, 110)

    # Filter weather to only needed counties
    wx = weather_df[weather_df["fips"].isin(fips_list)].copy()
    if wx.empty:
        return pd.DataFrame()

    # Parse date once
    wx["date_parsed"] = pd.to_datetime(wx["date"], format="%Y-%m-%d", errors="coerce")
    wx["year_val"] = wx["date_parsed"].dt.year
    wx["doy"] = wx["date_parsed"].dt.dayofyear
    wx["month"] = wx["date_parsed"].dt.month

    results = []
    for year in year_range:
        # Growing season window: planting_doy to planting_doy + week*7
        season_start_doy = planting_doy
        season_end_doy = planting_doy + week * 7

        # Handle year boundary for wheat (planting DOY 60, early in year)
        wx_year = wx[wx["year_val"] == year]
        season = wx_year[
            (wx_year["doy"] >= season_start_doy) &
            (wx_year["doy"] <= season_end_doy)
        ]

        if season.empty:
            continue

        # Group by FIPS for vectorized computation
        for fips, grp in season.groupby("fips"):
            # Only use rows where both tmax and tmin are present (for GDD)
            temp_valid = grp.dropna(subset=["tmax_f", "tmin_f"])
            prcp = grp["prcp_in"].dropna()

            if len(temp_valid) < 5:  # Need at least 5 days of data
                continue

            tmax_vals = temp_valid["tmax_f"].values
            tmin_vals = temp_valid["tmin_f"].values

            # GDD: Σ max(0, (tmax+tmin)/2 - 50)
            gdd_daily = ((tmax_vals + tmin_vals) / 2 - 50).clip(min=0)
            gdd_ytd = float(np.sum(gdd_daily))

            # Precipitation total (inches)
            precip_total = float(prcp.sum())

            # Precipitation deficit vs normal
            normal_total = 0.0
            start_date = date(year, 1, 1) + timedelta(days=season_start_doy - 1)
            end_date = date(year, 1, 1) + timedelta(days=min(season_end_doy, 365) - 1)
            current = start_date
            while current <= end_date:
                monthly_normal = prism_normals.get((fips, current.month), 0.25)
                normal_total += monthly_normal / 30.0
                current += timedelta(days=1)

            precip_deficit = precip_total - normal_total

            # Average daily max temp
            tmax_avg = float(tmax_vals.mean())

            # Hot days: tmax > 95°F (heat stress)
            hot_days = int((tmax_vals > 95).sum())

            results.append({
                "fips": fips,
                "year": year,
                "gdd_ytd": round(gdd_ytd, 1),
                "precip_season_in": round(precip_total, 2),
                "precip_deficit_in": round(precip_deficit, 2),
                "tmax_avg": round(tmax_avg, 1),
                "hot_days": hot_days,
            })

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results)


# ---- Training ----

def train_single_model(
    crop: str,
    week: int,
    nass_yields: pd.DataFrame,
    weather_df: pd.DataFrame,
    prism_normals: dict,
    skip_cv: bool = False,
    capture_predictions: bool = False,
) -> dict:
    """Train a single YieldModel for (crop, week) with weather features.

    If capture_predictions is True, returned dict includes a 'predictions'
    key holding a list of per-row val+test predictions. Each item:
        {forecast_year, fips, model_p50, model_p10, model_p90,
         actual_yield, county_5yr_mean, split}
    Used by the --persist-accuracy flag to populate yield_accuracy (§7.4 WI-3).
    """
    logger.info("=== Training %s week %d ===", crop, week)

    # Get list of counties with yield data
    fips_list = nass_yields["fips"].unique().tolist()
    year_range = range(
        max(int(nass_yields["year"].min()), 2000),
        int(nass_yields["year"].max()) + 1,
    )

    # Compute weather features for this crop/week
    wx_features = compute_weather_features(
        weather_df, prism_normals, crop, fips_list, year_range, week,
    )
    has_weather = not wx_features.empty
    if has_weather:
        wx_lookup = wx_features.set_index(["fips", "year"])
        logger.info("  Weather features: %d (fips,year) pairs", len(wx_features))
    else:
        wx_lookup = None
        logger.info("  No weather features available — using NASS-only features")

    # Build feature rows
    features_rows = []
    for _, row in nass_yields.iterrows():
        fips = row["fips"]
        year = row["year"]
        yield_val = row["yield_bu"]

        # NASS historical features
        county_hist = nass_yields[
            (nass_yields["fips"] == fips) & (nass_yields["year"] < year)
        ]["yield_bu"]

        if len(county_hist) < 3:
            continue

        feat = {
            "county_mean_yield": county_hist.mean(),
            "county_yield_trend": _compute_trend(county_hist),
            "prior_year_yield": county_hist.iloc[-1],
            "county_yield_std": county_hist.std(),
            "year": year,
            "_fips": fips,
            "_year": year,
            "_yield": yield_val,
        }

        # Add weather features if available
        if has_weather and (fips, year) in wx_lookup.index:
            wx_row = wx_lookup.loc[(fips, year)]
            feat["gdd_ytd"] = wx_row["gdd_ytd"]
            feat["precip_season_in"] = wx_row["precip_season_in"]
            feat["precip_deficit_in"] = wx_row["precip_deficit_in"]
            feat["tmax_avg"] = wx_row["tmax_avg"]
            feat["hot_days"] = wx_row["hot_days"]

        features_rows.append(feat)

    if not features_rows:
        logger.warning("No training data for %s week %d", crop, week)
        return {}

    df = pd.DataFrame(features_rows)

    # Use available features (drop all-null columns)
    available_features = [
        c for c in df.columns
        if not c.startswith("_") and df[c].notna().any()
    ]

    if len(available_features) < 2:
        logger.warning("Too few features for %s week %d", crop, week)
        return {}

    # Split train/val/test
    train_mask = df["_year"] <= TRAIN_END
    val_mask = (df["_year"] >= VAL_START) & (df["_year"] <= VAL_END)
    test_mask = (df["_year"] >= TEST_START) & (df["_year"] <= TEST_END)

    X_train = df.loc[train_mask, available_features]
    y_train = df.loc[train_mask, "_yield"]
    X_val = df.loc[val_mask, available_features]
    y_val = df.loc[val_mask, "_yield"]
    X_test = df.loc[test_mask, available_features]
    y_test = df.loc[test_mask, "_yield"]

    logger.info("  Split: train=%d, val=%d, test=%d, features=%d (%s)",
                len(X_train), len(X_val), len(X_test), len(available_features),
                ", ".join(available_features))

    if len(X_train) < 50 or len(X_val) < 10:
        logger.warning("Insufficient data for %s week %d", crop, week)
        return {}

    # Train model
    model = YieldModel(
        crop=crop,
        week=week,
        model_ver=date.today().isoformat(),
        feature_cols=available_features,
    )
    model.fit(X_train, y_train)

    # Evaluate
    train_preds = model.q50.predict(X_train[model.feature_cols].fillna(0))
    val_preds = model.q50.predict(X_val[model.feature_cols].fillna(0))

    train_rrmse = compute_rrmse(y_train.values, train_preds)
    val_rrmse = compute_rrmse(y_val.values, val_preds)

    # Calibrate conformal intervals
    model.calibrate_conformal(X_val, y_val)

    # Capture per-row walk-forward predictions for yield_accuracy persistence (§7.4 WI-3)
    prediction_rows: list[dict] = []
    if capture_predictions:
        val_df = df.loc[val_mask]
        val_p10, val_p50, val_p90 = model.predict_batch(X_val)
        for i, (_, meta) in enumerate(val_df.iterrows()):
            actual = float(meta["_yield"])
            p50 = float(val_p50[i])
            p10 = float(val_p10[i])
            p90 = float(val_p90[i])
            pct_err = round((p50 - actual) / actual * 100, 2) if actual > 0 else None
            prediction_rows.append({
                "forecast_year": int(meta["_year"]),
                "fips": str(meta["_fips"]),
                "crop": crop,
                "week": week,
                "model_p50": p50,
                "model_p10": p10,
                "model_p90": p90,
                "actual_yield": actual,
                "county_5yr_mean": round(float(meta.get("county_mean_yield", 0)), 1) if pd.notna(meta.get("county_mean_yield")) else None,
                "abs_error": round(abs(p50 - actual), 2),
                "pct_error": pct_err,
                "in_interval": bool(p10 <= actual <= p90),
                "split": "val",
            })

    # Test set
    test_rrmse = None
    if len(X_test) > 0:
        test_preds = model.q50.predict(X_test[model.feature_cols].fillna(0))
        test_rrmse = compute_rrmse(y_test.values, test_preds)

        if capture_predictions:
            test_df = df.loc[test_mask]
            test_p10, test_p50, test_p90 = model.predict_batch(X_test)
            for i, (_, meta) in enumerate(test_df.iterrows()):
                actual = float(meta["_yield"])
                p50 = float(test_p50[i])
                p10 = float(test_p10[i])
                p90 = float(test_p90[i])
                pct_err = round((p50 - actual) / actual * 100, 2) if actual > 0 else None
                prediction_rows.append({
                    "forecast_year": int(meta["_year"]),
                    "fips": str(meta["_fips"]),
                    "crop": crop,
                    "week": week,
                    "model_p50": p50,
                    "model_p10": p10,
                    "model_p90": p90,
                    "actual_yield": actual,
                    "county_5yr_mean": round(float(meta.get("county_mean_yield", 0)), 1) if pd.notna(meta.get("county_mean_yield")) else None,
                    "abs_error": round(abs(p50 - actual), 2),
                    "pct_error": pct_err,
                    "in_interval": bool(p10 <= actual <= p90),
                    "split": "test",
                })

    # Baselines
    baselines = compute_baselines(
        nass_yields,
        list(range(VAL_START, VAL_END + 1)),
    )

    # Gate check
    county_mean_baseline = baselines.get("county_mean_rrmse", 100)
    beats_baseline = val_rrmse < county_mean_baseline * (1 - BASELINE_GATE_PCT / 100)

    logger.info(
        "  %s week %d: train=%.2f%% val=%.2f%% test=%s baseline=%.2f%% beats=%s",
        crop, week, train_rrmse, val_rrmse,
        f"{test_rrmse:.2f}%" if test_rrmse else "N/A",
        county_mean_baseline, beats_baseline,
    )

    # Save artifacts
    artifact_dir = ARTIFACTS_DIR / crop / f"week_{week}"
    model.save(artifact_dir / "model.pkl")

    metrics = {
        "crop": crop,
        "week": week,
        "model_ver": model.model_ver,
        "train_rrmse": train_rrmse,
        "val_rrmse": val_rrmse,
        "test_rrmse": test_rrmse,
        "baselines": baselines,
        "beats_baseline": beats_baseline,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "n_features": len(model.feature_cols),
        "feature_cols": model.feature_cols,
        "has_weather_features": has_weather,
        "top_features": [
            {"name": name, "importance": round(float(imp), 4)}
            for name, imp in model.get_top_features(7)
        ],
        "conformal_q80": model.conformal_q80,
        "confidence_tier": YieldModel.confidence_tier(week),
    }

    with open(artifact_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    if capture_predictions:
        metrics["predictions"] = prediction_rows

    return metrics


def persist_yield_accuracy(predictions: list[dict], model_ver: str) -> int:
    """Upsert walk-forward yield predictions into yield_accuracy table (§7.4 WI-3).

    Args:
        predictions: list of per-row prediction dicts from train_single_model
                     (captured when capture_predictions=True).
        model_ver: model version string for the unique constraint.

    Returns number of rows upserted.
    """
    from sqlalchemy.dialects.postgresql import insert
    from backend.etl.common import get_sync_session
    from backend.models.db_tables import YieldAccuracy

    if not predictions:
        return 0

    rows = []
    for p in predictions:
        rows.append({
            **p,
            "model_ver": model_ver,
        })

    session = get_sync_session()
    try:
        # Upsert in chunks to keep single statements reasonable
        CHUNK = 5000
        total = 0
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i + CHUNK]
            stmt = insert(YieldAccuracy.__table__).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_yield_accuracy",
                set_={
                    "model_p50": stmt.excluded.model_p50,
                    "model_p10": stmt.excluded.model_p10,
                    "model_p90": stmt.excluded.model_p90,
                    "actual_yield": stmt.excluded.actual_yield,
                    "county_5yr_mean": stmt.excluded.county_5yr_mean,
                    "abs_error": stmt.excluded.abs_error,
                    "pct_error": stmt.excluded.pct_error,
                    "in_interval": stmt.excluded.in_interval,
                    "split": stmt.excluded.split,
                },
            )
            result = session.execute(stmt)
            total += result.rowcount
        session.commit()
        return total
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _compute_trend(series: pd.Series) -> float:
    """Compute simple linear trend (slope) of a series."""
    if len(series) < 3:
        return 0.0
    x = np.arange(len(series))
    try:
        slope = np.polyfit(x, series.values, 1)[0]
        return round(float(slope), 2)
    except (np.linalg.LinAlgError, ValueError):
        return 0.0


def upload_to_s3():
    """Upload all yield model artifacts to S3."""
    import subprocess
    s3_prefix = "s3://usda-analysis-datasets/models/yield/"
    logger.info("Uploading artifacts to S3...")
    try:
        subprocess.run(
            ["aws", "s3", "sync", str(ARTIFACTS_DIR), s3_prefix, "--quiet"],
            check=True, timeout=120,
        )
        logger.info("Artifacts uploaded to %s", s3_prefix)
    except Exception as exc:
        logger.warning("S3 upload failed: %s", exc)


def _write_crop_summaries(all_metrics: list[dict]) -> None:
    """Aggregate per-week metrics into one summary.json per crop.

    The yield forecast is surfaced in the dashboard even when the deployment
    gate fails (this is a class project; performance is annotated in-UI
    rather than gated at the model layer). The summary gives the frontend
    enough structured data to render an honest "Experimental" or "Production"
    badge instead of silently publishing suspect numbers.
    """
    by_crop: dict[str, list[dict]] = {}
    for m in all_metrics:
        by_crop.setdefault(m["crop"], []).append(m)

    for crop, ms in by_crop.items():
        weeks_with_gate = [bool(m.get("beats_baseline")) for m in ms]
        val_rrmses = [m["val_rrmse"] for m in ms if m.get("val_rrmse") is not None]
        test_rrmses = [m["test_rrmse"] for m in ms if m.get("test_rrmse") is not None]
        baselines = [
            m["baselines"].get("county_mean_rrmse")
            for m in ms if m.get("baselines") and m["baselines"].get("county_mean_rrmse") is not None
        ]

        n_pass = sum(1 for g in weeks_with_gate if g)
        gate_status = "pass" if n_pass == len(ms) else ("partial" if n_pass > 0 else "fail")

        summary = {
            "crop": crop,
            "model_ver": ms[0].get("model_ver") if ms else None,
            "n_weeks": len(ms),
            "n_weeks_pass_gate": n_pass,
            "gate_status": gate_status,
            "avg_val_rrmse": round(float(np.mean(val_rrmses)), 2) if val_rrmses else None,
            "avg_test_rrmse": round(float(np.mean(test_rrmses)), 2) if test_rrmses else None,
            "avg_baseline_rrmse": round(float(np.mean(baselines)), 2) if baselines else None,
            "has_weather_features": any(m.get("has_weather_features") for m in ms),
            "gate_threshold_pct": BASELINE_GATE_PCT,
        }

        summary_path = ARTIFACTS_DIR / crop / "summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(
            "  Wrote %s: gate=%s (%d/%d weeks pass)",
            summary_path, gate_status, n_pass, len(ms),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train crop yield prediction models")
    parser.add_argument("--commodity", default="all", help="corn|soybean|wheat|all")
    parser.add_argument("--week", type=int, help="Specific week (1-20), default: all")
    parser.add_argument("--local-only", action="store_true", help="Skip S3 download")
    parser.add_argument("--skip-cv", action="store_true", help="Skip cross-validation")
    parser.add_argument("--upload-s3", action="store_true", help="Upload artifacts to S3")
    parser.add_argument(
        "--persist-accuracy",
        action="store_true",
        help="Upsert walk-forward val+test predictions to yield_accuracy table",
    )
    args = parser.parse_args()

    t0 = _time.time()

    # Load shared data once
    weather_df = load_weather_data()
    prism_normals = load_prism_normals()

    commodities = COMMODITIES if args.commodity == "all" else {args.commodity: COMMODITIES[args.commodity]}
    weeks = [args.week] if args.week else list(WEEKS)

    all_metrics = []

    for crop_key, crop_nass in commodities.items():
        logger.info("=== Commodity: %s ===", crop_key)
        nass_yields = load_nass_county_yields(crop_nass, local_only=args.local_only)

        if nass_yields.empty:
            logger.warning("No yield data for %s. Skipping.", crop_key)
            continue

        logger.info("Loaded %d county yield records for %s (%d-%d)",
                    len(nass_yields), crop_key,
                    nass_yields["year"].min(), nass_yields["year"].max())

        for week in weeks:
            metrics = train_single_model(
                crop_key, week, nass_yields, weather_df, prism_normals, args.skip_cv,
                capture_predictions=args.persist_accuracy,
            )
            if metrics:
                all_metrics.append(metrics)

                # Persist walk-forward predictions per (crop, week) to yield_accuracy
                if args.persist_accuracy and metrics.get("predictions"):
                    try:
                        n = persist_yield_accuracy(
                            metrics["predictions"],
                            model_ver=metrics["model_ver"],
                        )
                        logger.info("  Persisted %d rows to yield_accuracy", n)
                    except Exception as exc:
                        logger.error("  Failed to persist yield accuracy: %s", exc)
                    # Strip predictions from in-memory metrics to keep memory bounded
                    metrics.pop("predictions", None)

    # Summary
    logger.info("=== Training Summary ===")
    for m in all_metrics:
        status = "PASS" if m.get("beats_baseline") else "FAIL"
        wx_tag = "+wx" if m.get("has_weather_features") else "nass-only"
        logger.info(
            "  %s week %2d: val=%.2f%% test=%s baseline=%.2f%% [%s] (%s, %d feats)",
            m["crop"], m["week"], m["val_rrmse"],
            f"{m['test_rrmse']:.2f}%" if m.get("test_rrmse") else "N/A",
            m["baselines"].get("county_mean_rrmse", 0),
            status, wx_tag, m["n_features"],
        )

    # Per-crop aggregate summary (consumed by GET /api/v1/predict/yield/metadata
    # so the frontend can annotate models that fail the deployment gate).
    _write_crop_summaries(all_metrics)

    if args.upload_s3:
        upload_to_s3()

    elapsed = _time.time() - t0
    logger.info("Total training time: %.1f minutes", elapsed / 60)
