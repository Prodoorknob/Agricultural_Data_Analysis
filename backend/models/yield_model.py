"""Crop yield prediction model — LightGBM quantile ensemble.

Per-crop × per-week model. Each model produces p10/p50/p90 bu/acre predictions.
60 total models: 3 crops × 20 weeks of growing season.

Follows the same dataclass pattern as AcreageEnsemble in acreage_model.py.
"""

import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

FEATURE_COLS = [
    "gdd_ytd",
    "cci_cumul",
    "precip_deficit",
    "vpd_stress_days",
    "drought_d3d4_pct",
    "soil_awc",
    "soil_drain",
]

# Human-readable feature labels for key driver reporting
FEATURE_LABELS = {
    "gdd_ytd": "Heat accumulation (GDD)",
    "cci_cumul": "Crop condition index",
    "precip_deficit": "Precipitation deficit",
    "vpd_stress_days": "VPD stress days",
    "drought_d3d4_pct": "Severe drought area",
    "soil_awc": "Soil water capacity",
    "soil_drain": "Soil drainage class",
}


@dataclass
class YieldModel:
    """LightGBM quantile ensemble for county-level yield prediction.

    Trains 3 separate LightGBM models (p10, p50, p90 quantiles).
    No Ridge component — county-level data provides sufficient observations.
    """

    crop: str = ""
    week: int = 0
    model_ver: str = ""
    feature_cols: list[str] = field(default_factory=lambda: list(FEATURE_COLS))

    # LightGBM models (set during fit)
    q10: object = None
    q50: object = None
    q90: object = None

    # Training statistics for inference
    train_median_yield: float = 0.0
    county_means: dict[str, float] = field(default_factory=dict)

    # Conformal calibration
    conformal_q80: float | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        """Train p10/p50/p90 quantile models."""
        from lightgbm import LGBMRegressor

        # Drop all-NaN columns
        valid_cols = [c for c in self.feature_cols if c in X.columns and X[c].notna().any()]
        self.feature_cols = valid_cols

        X_clean = X[valid_cols].fillna(X[valid_cols].median())
        self.train_median_yield = float(y.median())

        # Shared hyperparameters (from tech spec)
        shared_params = dict(
            n_estimators=500,
            max_depth=5,
            learning_rate=0.04,
            min_child_samples=20,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            verbose=-1,
            n_jobs=-1,
        )

        self.q10 = LGBMRegressor(objective="quantile", alpha=0.10, **shared_params)
        self.q50 = LGBMRegressor(objective="quantile", alpha=0.50, **shared_params)
        self.q90 = LGBMRegressor(objective="quantile", alpha=0.90, **shared_params)

        self.q10.fit(X_clean, y)
        self.q50.fit(X_clean, y)
        self.q90.fit(X_clean, y)

    def predict(self, X: pd.DataFrame) -> dict:
        """Predict p10/p50/p90 for a single row or small batch.

        Returns dict with keys: p10, p50, p90.
        """
        X_clean = X[self.feature_cols].copy()
        X_clean = X_clean.fillna(X_clean.median())
        if X_clean.isna().any(axis=None):
            X_clean = X_clean.fillna(0)

        p10 = float(self.q10.predict(X_clean)[0])
        p50 = float(self.q50.predict(X_clean)[0])
        p90 = float(self.q90.predict(X_clean)[0])

        # Enforce ordering: p10 <= p50 <= p90
        p10, p50, p90 = sorted([p10, p50, p90])

        # Floor at 0 (yields can't be negative)
        p10 = max(0.0, p10)
        p50 = max(0.0, p50)
        p90 = max(0.0, p90)

        return {
            "p10": round(p10, 1),
            "p50": round(p50, 1),
            "p90": round(p90, 1),
        }

    def predict_batch(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Vectorized prediction for multiple rows."""
        X_clean = X[self.feature_cols].copy()
        X_clean = X_clean.fillna(X_clean.median())
        if X_clean.isna().any(axis=None):
            X_clean = X_clean.fillna(0)

        p10 = self.q10.predict(X_clean)
        p50 = self.q50.predict(X_clean)
        p90 = self.q90.predict(X_clean)

        # Enforce ordering row-wise
        stacked = np.stack([p10, p50, p90], axis=1)
        stacked.sort(axis=1)
        p10, p50, p90 = stacked[:, 0], stacked[:, 1], stacked[:, 2]

        # Floor at 0
        p10 = np.maximum(p10, 0)
        p50 = np.maximum(p50, 0)
        p90 = np.maximum(p90, 0)

        return p10, p50, p90

    def calibrate_conformal(self, X_val: pd.DataFrame, y_val: pd.Series) -> None:
        """Post-hoc conformal calibration on validation set.

        Computes the 80th percentile of absolute residuals for interval scaling.
        """
        X_clean = X_val[self.feature_cols].fillna(X_val[self.feature_cols].median())
        if X_clean.isna().any(axis=None):
            X_clean = X_clean.fillna(0)

        preds = self.q50.predict(X_clean)
        residuals = np.abs(y_val.values - preds)
        self.conformal_q80 = float(np.percentile(residuals, 80))

    @staticmethod
    def confidence_tier(week: int) -> str:
        """Determine confidence tier from week of growing season."""
        if week < 8:
            return "low"
        if week < 16:
            return "medium"
        return "high"

    def get_top_features(self, n: int = 3) -> list[tuple[str, float]]:
        """Get top N features by importance from the p50 model."""
        if self.q50 is None:
            return []
        importances = self.q50.feature_importances_
        feature_imp = sorted(
            zip(self.feature_cols, importances),
            key=lambda x: x[1],
            reverse=True,
        )
        return feature_imp[:n]

    def get_key_driver(self, X_row: pd.DataFrame) -> str:
        """Identify the most important feature for this prediction."""
        top = self.get_top_features(1)
        if top:
            feat_name = top[0][0]
            return FEATURE_LABELS.get(feat_name, feat_name)
        return "Unknown"

    def save(self, path: Path) -> None:
        """Serialize model to pickle + HMAC-SHA256 sidecar."""
        from backend.models._signing import sign_artifact
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        sign_artifact(path)

    @staticmethod
    def load(path: Path) -> "YieldModel":
        """Deserialize model from pickle; verifies HMAC when key is configured."""
        from backend.models._signing import ensure_verified_or_fail
        ensure_verified_or_fail(path)
        with open(path, "rb") as f:
            return pickle.load(f)


# ---- Baseline Models ----

def compute_baselines(
    nass_yields: pd.DataFrame,
    eval_years: list[int],
) -> dict[str, float]:
    """Compute baseline RRMSE for comparison.

    Baselines:
    1. County historical mean — average yield for that county over prior years
    2. Prior year actual — last year's realized yield
    """
    county_mean_errors = []
    prior_year_errors = []

    for year in eval_years:
        train_data = nass_yields[nass_yields["year"] < year]
        test_data = nass_yields[nass_yields["year"] == year]

        for _, test_row in test_data.iterrows():
            fips = test_row["fips"]
            actual = test_row["yield_bu"]

            # County historical mean (all prior years for this county)
            county_hist = train_data[train_data["fips"] == fips]["yield_bu"]
            if len(county_hist) >= 3:
                county_mean = county_hist.mean()
                county_mean_errors.append((actual - county_mean) ** 2)

            # Prior year
            prior = train_data[
                (train_data["fips"] == fips) &
                (train_data["year"] == year - 1)
            ]["yield_bu"]
            if not prior.empty:
                prior_year_errors.append((actual - prior.iloc[0]) ** 2)

    # RRMSE = sqrt(MSE) / mean(actual)
    mean_yield = nass_yields[nass_yields["year"].isin(eval_years)]["yield_bu"].mean()

    results = {}
    if county_mean_errors:
        results["county_mean_rrmse"] = round(
            float(np.sqrt(np.mean(county_mean_errors)) / mean_yield * 100), 2
        )
    if prior_year_errors:
        results["prior_year_rrmse"] = round(
            float(np.sqrt(np.mean(prior_year_errors)) / mean_yield * 100), 2
        )

    return results


def compute_rrmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute Relative RMSE (%) = RMSE / mean(y_true) * 100."""
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    mean_val = np.mean(y_true)
    if mean_val == 0:
        return float("inf")
    return round(float(rmse / mean_val * 100), 2)
