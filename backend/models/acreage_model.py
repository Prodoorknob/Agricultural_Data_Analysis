"""Planted acreage ensemble model (Module 03).

Architecture: Ridge + LightGBM point + LightGBM quantile (p10/p90).
Meta-learner: simple average.  Annual cadence, state-panel data.
Includes: naive baselines, LOYO CV, conformal calibration, rich metrics.
"""

import json
import pickle
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.etl.common import setup_logging

logger = setup_logging("acreage_model")

# Human-readable labels for top feature importance reporting
DRIVER_LABELS = {
    "corn_soy_ratio": "Corn-to-soybean price ratio",
    "relative_profitability": "Relative crop profit margin",
    "anhydrous_price_ton": "Nitrogen fertilizer cost",
    "prior_year_acres": "Prior year planted acreage",
    "profit_margin_bu": "Per-bushel profit margin",
    "yield_trend_5yr": "5-year yield improvement trend",
    "corn_futures_dec": "December corn futures price",
    "soy_futures_nov": "November soybean futures price",
    "wheat_futures_jul": "December wheat futures price",
    "variable_cost_bu": "Variable production cost",
    "prior_3yr_avg_acres": "3-year average planted acreage",
    "prior_5yr_avg_acres": "5-year average planted acreage",
    "prior_year_yield": "Prior year crop yield",
    "rotation_ratio": "Corn-soybean rotation ratio",
    "forecast_year": "Long-term acreage trend",
    "state_fips_code": "State-specific factor",
    # Tier 1 features
    "dsci_nov": "November drought severity",
    "dsci_fall_avg": "Fall drought intensity",
    "insured_acres_prior": "Prior year insured acreage",
    "insured_acres_yoy_change": "Insurance enrollment trend",
    "crp_expiring_acres": "CRP contract expirations",
    "crp_pct_cropland": "Conservation reserve share",
    "export_outstanding_pct": "Export commitments level",
    "export_pace_vs_5yr": "Export pace vs historical",
}

# Baseline gate: model must beat best baseline by at most this margin (pp)
BASELINE_GATE_PP = 0.5


# ---------------------------------------------------------------------------
# Helper metrics
# ---------------------------------------------------------------------------

def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    mask = y_true != 0
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def _coverage(y_true: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    inside = (y_true >= lo) & (y_true <= hi)
    return float(np.mean(inside))


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------

@dataclass
class AcreageEnsemble:
    """Ridge + LightGBM ensemble for planted acreage prediction.

    When use_residual=True, the model predicts the delta (acres - prior_year_acres)
    instead of absolute acres. At prediction time, prior_year_acres is added back.
    This lets the model focus on year-over-year changes and start from the
    persistence baseline rather than competing with it.
    """

    commodity: str
    model_ver: str = ""
    feature_cols: list[str] = field(default_factory=list)

    # Models (set during fit)
    ridge: Pipeline | None = None
    lgbm: object = None  # LGBMRegressor
    q_low: object = None  # quantile α=0.10
    q_high: object = None  # quantile α=0.90

    # Residual modeling — if True, target = acres - baseline_col
    use_residual: bool = False
    prior_year_col: str = "prior_year_acres"  # used as residual baseline

    # Conformal calibration
    conformal_q80: float | None = None  # absolute residual quantile for 80% coverage
    median_train_acres: float | None = None  # for scaling intervals by state size

    # Metrics
    train_mape: float | None = None
    val_mape: float | None = None

    def _to_delta(self, X: pd.DataFrame, y: pd.Series) -> tuple[pd.Series, pd.Series]:
        """Convert absolute target to delta from prior year. Returns (y_delta, base)."""
        base = X[self.prior_year_col].fillna(y.median())
        return y - base, base

    def _from_delta(self, delta: np.ndarray, base: np.ndarray) -> np.ndarray:
        """Convert delta predictions back to absolute acres."""
        return delta + base

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """Train all 4 sub-models."""
        import lightgbm as lgb

        self.feature_cols = list(X.columns)

        # Drop columns that are entirely NaN
        all_nan_cols = X.columns[X.isna().all()].tolist()
        if all_nan_cols:
            logger.info(f"Dropping all-NaN columns: {all_nan_cols}")
            X = X.drop(columns=all_nan_cols)
            self.feature_cols = list(X.columns)

        # Handle NaN: fill with column medians
        X_filled = X.fillna(X.median())

        # Residual target: predict delta from prior year
        if self.use_residual and self.prior_year_col in X_filled.columns:
            y_fit, _ = self._to_delta(X_filled, y)
            logger.info(f"  Residual mode: target mean delta = {y_fit.mean():,.0f} acres")
        else:
            y_fit = y
            if self.use_residual:
                logger.warning(f"  {self.prior_year_col} not in features, falling back to absolute")
                self.use_residual = False

        # Store median training acres for conformal scaling
        self.median_train_acres = float(y.median())

        # Ridge regression (standardized)
        self.ridge = Pipeline([
            ("scaler", StandardScaler()),
            ("model", Ridge(alpha=10.0)),
        ])
        self.ridge.fit(X_filled, y_fit)

        # LightGBM point estimate
        self.lgbm = lgb.LGBMRegressor(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            min_child_samples=10,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.5,
            reg_lambda=1.0,
            verbose=-1,
        )
        self.lgbm.fit(X_filled, y_fit)

        # LightGBM quantiles (kept as fallback, but conformal preferred)
        self.q_low = lgb.LGBMRegressor(
            objective="quantile", alpha=0.10,
            n_estimators=300, max_depth=3, min_child_samples=10, verbose=-1,
        )
        self.q_low.fit(X_filled, y_fit)

        self.q_high = lgb.LGBMRegressor(
            objective="quantile", alpha=0.90,
            n_estimators=300, max_depth=3, min_child_samples=10, verbose=-1,
        )
        self.q_high.fit(X_filled, y_fit)

        logger.info(f"Trained AcreageEnsemble for {self.commodity} on {len(X)} samples"
                     f" (residual={self.use_residual})")

    def _raw_predict(self, X_filled: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Core prediction in model-native space (delta if residual, absolute otherwise)."""
        ridge_pred = self.ridge.predict(X_filled)
        lgbm_pred = self.lgbm.predict(X_filled)
        p50_raw = (ridge_pred + lgbm_pred) / 2

        if self.conformal_q80 is not None:
            if self.use_residual:
                # In residual mode, conformal q80 is already in delta-acre units
                # No scaling needed — the interval width is constant
                q = np.full_like(p50_raw, self.conformal_q80)
            elif self.median_train_acres:
                # In absolute mode, scale interval by predicted magnitude
                scale = np.maximum(np.abs(p50_raw), 1) / max(self.median_train_acres, 1)
                q = self.conformal_q80 * scale
            else:
                q = np.full_like(p50_raw, self.conformal_q80)
            p10_raw = p50_raw - q
            p90_raw = p50_raw + q
        else:
            p10_raw = self.q_low.predict(X_filled)
            p90_raw = self.q_high.predict(X_filled)

        return p10_raw, p50_raw, p90_raw

    def _reconstruct(self, p10_raw, p50_raw, p90_raw, X_filled):
        """Convert from model space back to absolute acres."""
        if self.use_residual and self.prior_year_col in X_filled.columns:
            base = X_filled[self.prior_year_col].fillna(self.median_train_acres or 0).values
            p50 = self._from_delta(p50_raw, base)
            p10 = self._from_delta(p10_raw, base)
            p90 = self._from_delta(p90_raw, base)
        else:
            p50, p10, p90 = p50_raw, p10_raw, p90_raw

        # Enforce ordering and non-negativity
        p50 = np.maximum(p50, 0)
        p10 = np.minimum(p10, p50)
        p10 = np.maximum(p10, 0)
        p90 = np.maximum(p90, p50)
        return p10, p50, p90

    def predict(self, X: pd.DataFrame) -> dict:
        """Predict planted acreage with uncertainty bounds."""
        X = X[[c for c in self.feature_cols if c in X.columns]]
        X_filled = X.fillna(X.median() if len(X) > 1 else 0)

        p10_raw, p50_raw, p90_raw = self._raw_predict(X_filled)
        p10, p50, p90 = self._reconstruct(p10_raw, p50_raw, p90_raw, X_filled)

        return {
            "p10": float(p10[0]),
            "p50": float(p50[0]),
            "p90": float(p90[0]),
        }

    def predict_batch(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Predict for multiple rows at once. Returns (p10, p50, p90) arrays."""
        X = X[[c for c in self.feature_cols if c in X.columns]]
        X_filled = X.fillna(X.median()).fillna(0)

        p10_raw, p50_raw, p90_raw = self._raw_predict(X_filled)
        return self._reconstruct(p10_raw, p50_raw, p90_raw, X_filled)

    def calibrate_conformal(self, X_val: pd.DataFrame, y_val: pd.Series):
        """Calibrate prediction intervals using split conformal prediction.

        Computes absolute residuals on validation set in model-native space
        (deltas if residual mode) and stores the 80th percentile.
        """
        X_use = X_val[[c for c in self.feature_cols if c in X_val.columns]]
        X_filled = X_use.fillna(X_use.median()).fillna(0)

        _, p50_raw, _ = self._raw_predict(X_filled)

        # Residuals in native space
        if self.use_residual and self.prior_year_col in X_filled.columns:
            y_native, _ = self._to_delta(X_filled, y_val)
            residuals = np.abs(y_native.values - p50_raw)
        else:
            residuals = np.abs(y_val.values - p50_raw)

        n = len(residuals)
        level = 0.80 * (1 + 1 / n) if n > 0 else 0.80
        self.conformal_q80 = float(np.quantile(residuals, min(level, 1.0)))
        logger.info(f"  Conformal q80 = {self.conformal_q80:,.0f} acres (from {n} val samples)")

    def get_key_driver(self, X_row: pd.Series) -> str:
        """Return the most important feature for this prediction."""
        if self.lgbm is None:
            return "Model not trained"
        importances = dict(zip(self.feature_cols, self.lgbm.feature_importances_))
        top = max(importances, key=importances.get)
        return DRIVER_LABELS.get(top, top.replace("_", " ").title())

    def get_top_features(self, n: int = 3) -> list[str]:
        """Return top-n feature names by importance."""
        if self.lgbm is None:
            return []
        pairs = sorted(
            zip(self.feature_cols, self.lgbm.feature_importances_),
            key=lambda x: x[1], reverse=True,
        )
        return [name for name, _ in pairs[:n]]

    def save(self, path: Path):
        """Serialize ensemble to disk + HMAC-SHA256 sidecar."""
        from backend.models._signing import sign_artifact
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        sign_artifact(path)
        logger.info(f"Saved AcreageEnsemble to {path}")

    @staticmethod
    def load(path: Path) -> "AcreageEnsemble":
        """Load ensemble from disk; verifies HMAC when key is configured."""
        from backend.models._signing import ensure_verified_or_fail
        ensure_verified_or_fail(path)
        with open(path, "rb") as f:
            return pickle.load(f)


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def compute_baselines(
    nass_data: pd.DataFrame,
    commodity: str,
    states: list[str],
    eval_years: list[int],
) -> dict[str, float]:
    """Compute persistence and 5-year-average baseline MAPEs.

    Returns dict with persistence_mape and fiveyear_avg_mape.
    """
    # wheat_winter/wheat_spring map to NASS "wheat"
    nass_commodity = commodity.split("_")[0] if "_" in commodity else commodity
    subset = nass_data[
        (nass_data["commodity"] == nass_commodity)
        & (nass_data["state_fips"].isin(states))
    ].copy()

    persist_errors = []
    avg5_errors = []

    for year in eval_years:
        for state in states:
            actual_row = subset[
                (subset["state_fips"] == state) & (subset["year"] == year)
            ]
            if actual_row.empty:
                continue
            actual = actual_row["acres_planted"].values[0]
            if actual == 0:
                continue

            # Persistence: prior year
            prior = subset[
                (subset["state_fips"] == state) & (subset["year"] == year - 1)
            ]
            if not prior.empty:
                persist_errors.append(abs(prior["acres_planted"].values[0] - actual) / actual)

            # 5-year average
            recent = subset[
                (subset["state_fips"] == state)
                & (subset["year"] >= year - 5)
                & (subset["year"] < year)
            ]
            if len(recent) >= 3:
                avg5 = recent["acres_planted"].mean()
                avg5_errors.append(abs(avg5 - actual) / actual)

    return {
        "persistence_mape": round(float(np.mean(persist_errors)) * 100, 2) if persist_errors else None,
        "fiveyear_avg_mape": round(float(np.mean(avg5_errors)) * 100, 2) if avg5_errors else None,
    }


# ---------------------------------------------------------------------------
# Leave-One-Year-Out CV
# ---------------------------------------------------------------------------

def leave_one_year_out_cv(
    commodity: str,
    nass_data: pd.DataFrame,
    feature_df: pd.DataFrame,
    avail_cols: list[str],
    year_range: list[int],
) -> dict:
    """Run LOYO CV and return summary metrics.

    Args:
        commodity: commodity name
        nass_data: full NASS DataFrame
        feature_df: pre-built feature DataFrame with _year, _state_fips, acres_planted
        avail_cols: feature column names
        year_range: years to hold out one at a time

    Returns:
        dict with cv_mean_mape, cv_std_mape, cv_worst_fold_year, cv_worst_fold_mape
    """
    fold_mapes = {}

    for holdout_year in year_range:
        train_mask = feature_df["_year"] != holdout_year
        test_mask = feature_df["_year"] == holdout_year

        X_train = feature_df.loc[train_mask, avail_cols]
        y_train = feature_df.loc[train_mask, "acres_planted"]
        X_test = feature_df.loc[test_mask, avail_cols]
        y_test = feature_df.loc[test_mask, "acres_planted"]

        if len(X_train) < 10 or len(X_test) == 0:
            continue

        fold_model = AcreageEnsemble(commodity=commodity)
        fold_model.fit(X_train, y_train)

        _, p50, _ = fold_model.predict_batch(X_test)
        fold_mape = _mape(y_test.values, p50)
        fold_mapes[holdout_year] = fold_mape

    if not fold_mapes:
        return {}

    mapes = list(fold_mapes.values())
    worst_year = max(fold_mapes, key=fold_mapes.get)

    return {
        "cv_mean_mape": round(float(np.mean(mapes)), 2),
        "cv_std_mape": round(float(np.std(mapes)), 2),
        "cv_n_folds": len(mapes),
        "cv_worst_fold_year": int(worst_year),
        "cv_worst_fold_mape": round(fold_mapes[worst_year], 2),
    }


# ---------------------------------------------------------------------------
# National rollup
# ---------------------------------------------------------------------------

def apply_competition_constraint(
    state_forecasts: dict[str, float],
    prior_year_total: float,
    tolerance_pct: float = 0.03,
) -> dict[str, float]:
    """Soft constraint: total forecast acres should not deviate > tolerance_pct
    from prior year's total cropland. Scale proportionally if violated."""
    forecast_total = sum(state_forecasts.values())
    if prior_year_total > 0 and abs(forecast_total - prior_year_total) / prior_year_total > tolerance_pct:
        scale = prior_year_total / forecast_total
        return {k: v * scale for k, v in state_forecasts.items()}
    return state_forecasts


def compute_national_forecast(state_df: pd.DataFrame, commodity: str | None = None) -> dict:
    """Sum state-level predictions to national total with correlated uncertainty.

    The per-state p10/p90 stored on each prediction is an 80% symmetric
    conformal interval (see calibrate_conformal, level=0.80), so σ is
    recovered with the 80% z-score 1.2816 — not 1.645 (which is 90%).
    Using 1.645 here was understating state sigma by ~22% and producing
    a too-narrow national rollup.

    When ``commodity`` is supplied, the final p50/p10/p90 are multiplied
    by NATIONAL_COVERAGE_MULTIPLIERS[commodity] to scale the top-15-state
    sum to a true US-wide total consistent with USDA's Prospective
    Plantings report. Interval widens proportionally so coverage is
    preserved. Without the multiplier, soybean rolled up to 71.7M
    against a USDA-published 83.5M (missing long-tail states).
    """
    # Two-sided 80% normal quantile: Φ⁻¹(0.90) ≈ 1.2816
    Z_80 = 1.2816

    national_p50 = state_df["p50"].sum()

    state_sigmas = (state_df["p90"] - state_df["p10"]) / (2 * Z_80)
    state_variances = state_sigmas ** 2

    rho = 0.5
    total_var = state_variances.sum()
    cross_var = 0.0
    sigmas = state_sigmas.values
    for i in range(len(sigmas)):
        for j in range(i + 1, len(sigmas)):
            cross_var += sigmas[i] * sigmas[j]
    national_var = total_var + 2 * rho * cross_var
    national_sigma = np.sqrt(max(national_var, 0))

    # Apply the long-tail state scale-up (see acreage_features.NATIONAL_COVERAGE_MULTIPLIERS).
    multiplier = 1.0
    if commodity is not None:
        # Import here to avoid circular dependency on module-level import.
        from backend.features.acreage_features import NATIONAL_COVERAGE_MULTIPLIERS
        multiplier = NATIONAL_COVERAGE_MULTIPLIERS.get(commodity, 1.0)

    return {
        "p50": national_p50 * multiplier,
        "p10": (national_p50 - Z_80 * national_sigma) * multiplier,
        "p90": (national_p50 + Z_80 * national_sigma) * multiplier,
        "scale_multiplier": multiplier,
    }


# ---------------------------------------------------------------------------
# Training orchestrator
# ---------------------------------------------------------------------------

def train_and_save(
    commodity: str,
    nass_data: pd.DataFrame,
    output_dir: Path,
    states: list[str] | None = None,
    train_years: range = range(1995, 2021),
    val_years: range = range(2021, 2024),
    use_residual: bool = False,
    residual_col: str = "prior_year_acres",
    test_years: list[int] | None = None,
    run_cv: bool = True,
) -> tuple[AcreageEnsemble, dict, pd.DataFrame]:
    """Train an AcreageEnsemble with full evaluation pipeline.

    Returns:
        (ensemble, metrics_dict, predictions_df)

    predictions_df has one row per (val + test) prediction with columns:
        forecast_year, state_fips, commodity, model_p50, model_p10, model_p90,
        actual, split ('val' | 'test')
    This is used by train_acreage.py's --persist-accuracy flag to populate the
    acreage_accuracy table.
    """
    from backend.features.acreage_features import (
        build_training_features, FEATURE_COLS, TOP_STATES, clear_query_caches,
    )

    if test_years is None:
        test_years = [2024, 2025]
    if states is None:
        states = TOP_STATES.get(commodity, ["00"])

    clear_query_caches()
    model_ver = date.today().strftime("%Y-%m-%d")

    # Build feature matrix
    all_years = range(min(train_years), max(max(val_years), max(test_years)) + 1)
    df = build_training_features(
        commodity, nass_data,
        year_start=min(all_years),
        year_end=max(all_years),
        states=states,
    )

    if df.empty:
        raise ValueError(f"No training data for {commodity}")

    # Split
    train = df[df["_year"].isin(train_years)]
    val = df[df["_year"].isin(val_years)]
    test = df[df["_year"].isin(test_years)]

    avail_cols = [c for c in FEATURE_COLS if c in df.columns]
    X_train = train[avail_cols]
    y_train = train["acres_planted"]

    # ---- Train ----
    ensemble = AcreageEnsemble(
        commodity=commodity, model_ver=model_ver,
        use_residual=use_residual, prior_year_col=residual_col,
    )
    ensemble.fit(X_train, y_train)

    # ---- Metrics ----
    metrics = {
        "commodity": commodity,
        "model_ver": model_ver,
        "n_train": len(X_train),
        "n_val": len(val),
        "n_test": len(test),
        "n_states": len(states),
    }

    # Per-row walk-forward predictions for acreage_accuracy persistence (§7.4 WI-1)
    prediction_rows: list[dict] = []

    # Train MAPE
    _, p50_train, _ = ensemble.predict_batch(X_train)
    metrics["train_mape"] = round(_mape(y_train.values, p50_train), 2)

    # Val evaluation + conformal calibration
    if not val.empty:
        X_val = val[avail_cols]
        y_val = val["acres_planted"]

        ensemble.calibrate_conformal(X_val, y_val)

        p10_val, p50_val, p90_val = ensemble.predict_batch(X_val)
        metrics["val_mape"] = round(_mape(y_val.values, p50_val), 2)
        metrics["val_rmse"] = round(_rmse(y_val.values, p50_val), 0)
        metrics["coverage_80_val"] = round(_coverage(y_val.values, p10_val, p90_val), 2)
        ensemble.val_mape = metrics["val_mape"]
        logger.info(f"  Val MAPE: {metrics['val_mape']}%  Coverage: {metrics['coverage_80_val']}")

        # Capture per-row val predictions
        for i, (idx, row) in enumerate(val.iterrows()):
            prediction_rows.append({
                "forecast_year": int(row["_year"]),
                "state_fips": str(row["_state_fips"]),
                "commodity": commodity,
                "model_p50": float(p50_val[i]),
                "model_p10": float(p10_val[i]),
                "model_p90": float(p90_val[i]),
                "actual": float(y_val.iloc[i]),
                "split": "val",
            })

    # Test evaluation
    if not test.empty:
        X_test = test[avail_cols]
        y_test = test["acres_planted"]
        p10_test, p50_test, p90_test = ensemble.predict_batch(X_test)
        metrics["test_mape"] = round(_mape(y_test.values, p50_test), 2)
        metrics["test_rmse"] = round(_rmse(y_test.values, p50_test), 0)
        metrics["coverage_80_test"] = round(_coverage(y_test.values, p10_test, p90_test), 2)
        logger.info(f"  Test MAPE: {metrics['test_mape']}%  Coverage: {metrics['coverage_80_test']}")

        # Capture per-row test predictions
        for i, (idx, row) in enumerate(test.iterrows()):
            prediction_rows.append({
                "forecast_year": int(row["_year"]),
                "state_fips": str(row["_state_fips"]),
                "commodity": commodity,
                "model_p50": float(p50_test[i]),
                "model_p10": float(p10_test[i]),
                "model_p90": float(p90_test[i]),
                "actual": float(y_test.iloc[i]),
                "split": "test",
            })

    # ---- Baselines ----
    eval_years_all = list(val_years) + list(test_years)
    baselines = compute_baselines(nass_data, commodity, states, eval_years_all)
    metrics.update(baselines)

    best_baseline = min(
        v for v in [baselines.get("persistence_mape"), baselines.get("fiveyear_avg_mape")]
        if v is not None
    )
    model_eval_mape = metrics.get("val_mape", metrics.get("test_mape", 999))
    beats = model_eval_mape <= best_baseline + BASELINE_GATE_PP
    metrics["best_baseline_mape"] = best_baseline
    metrics["improvement_over_baseline_pp"] = round(best_baseline - model_eval_mape, 2)
    metrics["beats_baseline"] = beats

    if beats:
        logger.info(f"  PASS: model {model_eval_mape:.2f}% vs baseline {best_baseline:.2f}%")
    else:
        logger.warning(
            f"  GATE FAIL: model {model_eval_mape:.2f}% vs baseline {best_baseline:.2f}% "
            f"(+{BASELINE_GATE_PP}pp gate)"
        )

    # ---- LOYO CV ----
    if run_cv:
        logger.info("  Running leave-one-year-out CV ...")
        cv_years = sorted(set(train["_year"]))
        cv_results = leave_one_year_out_cv(commodity, nass_data, df, avail_cols, cv_years)
        metrics.update(cv_results)
        if cv_results:
            logger.info(
                f"  CV mean MAPE: {cv_results['cv_mean_mape']}% "
                f"(std={cv_results['cv_std_mape']}%, worst={cv_results['cv_worst_fold_year']})"
            )

    # Conformal q80
    if ensemble.conformal_q80 is not None:
        metrics["conformal_q80"] = round(ensemble.conformal_q80, 0)

    # Top features
    metrics["top_features"] = ensemble.get_top_features(5)

    # ---- Save ----
    artifact_dir = output_dir / commodity
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ensemble.save(artifact_dir / "ensemble.pkl")

    with open(artifact_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    predictions_df = pd.DataFrame(prediction_rows)
    return ensemble, metrics, predictions_df
