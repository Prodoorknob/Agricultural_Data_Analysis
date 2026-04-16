"""Commodity price forecasting ensemble model.

PriceEnsemble combines SARIMAX (autocorrelation + exogenous WASDE/DXY signals)
with LightGBM (nonlinear feature interactions) via a Ridge meta-learner.
Quantile predictions (p10/p90) come from LightGBM quantile regressors.
Probability calibration uses IsotonicRegression on the validation set.
Regime anomaly detection uses Mahalanobis distance.
Key driver labels come from SHAP TreeExplainer on the LightGBM point model.

One PriceEnsemble per (commodity, horizon) = 3 commodities x 6 horizons = 18 model sets.
Artifacts are persisted to S3 under models/price/{commodity}/horizon_{N}/.
"""

from __future__ import annotations

import io
import json
import logging
import pickle
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shap
from lightgbm import LGBMRegressor
from scipy.spatial.distance import mahalanobis
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from statsmodels.tsa.statespace.sarimax import SARIMAX

from backend.etl.common import setup_logging

logger = setup_logging("price_model")

MODEL_VERSION_FMT = "%Y-%m-%d"

# Features used by SARIMAX as exogenous regressors (must be available at inference)
ARIMAX_EXOG_COLS = ["wasde_surprise", "dxy", "stocks_to_use"]

# All numeric features fed to LightGBM (excludes metadata columns)
LGBM_FEATURE_COLS = [
    "futures_spot",
    "futures_deferred",
    "basis",
    "term_spread",
    "open_interest_chg",
    "stocks_to_use",
    "stocks_to_use_pctile",
    "wasde_surprise",
    "world_stocks_to_use",
    "dxy",
    "dxy_chg_30d",
    "production_cost_bu",
    "price_cost_ratio",
    "corn_soy_ratio",
    "prior_year_price",
    "seasonal_factor",
]

# Human-readable labels for SHAP key driver output
FEATURE_LABEL_MAP = {
    "futures_spot": "Nearby futures price level",
    "futures_deferred": "Deferred futures price level",
    "basis": "Cash-futures basis spread",
    "term_spread": "Futures term spread (carry)",
    "open_interest_chg": "Open interest momentum (30d)",
    "stocks_to_use": "USDA stocks-to-use ratio",
    "stocks_to_use_pctile": "Stocks-to-use historical percentile",
    "wasde_surprise": "WASDE monthly supply surprise",
    "world_stocks_to_use": "Global stocks-to-use ratio",
    "dxy": "US dollar strength (DXY)",
    "dxy_chg_30d": "Dollar index 30-day change",
    "production_cost_bu": "Cost of production floor",
    "price_cost_ratio": "Price-to-cost ratio",
    "corn_soy_ratio": "Corn-to-soybean price ratio",
    "prior_year_price": "Prior-year price (mean reversion)",
    "seasonal_factor": "Seasonal price factor",
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _prepare_target(
    features_df: pd.DataFrame, futures_df: pd.DataFrame, horizon_months: int
) -> pd.Series:
    """Build the target variable: realized price `horizon_months` months after as_of_date.

    Parameters
    ----------
    features_df : DataFrame with 'as_of_date' and 'commodity' columns.
    futures_df : DataFrame of futures_daily with 'trade_date', 'commodity', 'settlement'.
    horizon_months : int

    Returns
    -------
    pd.Series aligned to features_df index with realized settlement prices.
    """
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
            # Closest to target_date
            idx = (matched["trade_date"] - target_date).abs().idxmin()
            targets.append(float(matched.loc[idx, "settlement"]))
        else:
            targets.append(np.nan)
    return pd.Series(targets, index=features_df.index, name="target_price")


def _get_lgbm_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract and fill LightGBM feature columns, handling NaN gracefully."""
    cols = [c for c in LGBM_FEATURE_COLS if c in df.columns]
    return df[cols].astype(float)


def _get_arimax_exog(df: pd.DataFrame) -> pd.DataFrame:
    """Extract ARIMAX exogenous columns, filling NaN with 0."""
    cols = [c for c in ARIMAX_EXOG_COLS if c in df.columns]
    return df[cols].astype(float).fillna(0)


# ---------------------------------------------------------------------------
# Regime anomaly detection
# ---------------------------------------------------------------------------


def is_regime_anomaly(
    x_current: np.ndarray,
    x_train: np.ndarray,
    threshold_sigma: float = 3.0,
) -> bool:
    """Return True if current feature vector is outside training distribution.

    Uses Mahalanobis distance with regularized covariance.
    When True, suppress ML forecast and defer to futures curve.
    """
    if x_train.shape[0] < x_train.shape[1] + 2:
        return False  # Not enough data to compute covariance
    cov = np.cov(x_train, rowvar=False)
    # Regularize to avoid singular matrix
    cov += np.eye(cov.shape[0]) * 1e-6
    try:
        cov_inv = np.linalg.pinv(cov)
        mean = np.nanmean(x_train, axis=0)
        dist = mahalanobis(x_current, mean, cov_inv)
        return dist > threshold_sigma
    except (np.linalg.LinAlgError, ValueError):
        return False


# ---------------------------------------------------------------------------
# SHAP key driver
# ---------------------------------------------------------------------------


def get_key_driver_label(model: LGBMRegressor, x_row: pd.DataFrame) -> str:
    """Return plain-English label of the top SHAP feature for this forecast."""
    try:
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(x_row)
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[0]
        if shap_vals.ndim > 1:
            shap_vals = shap_vals[0]
        abs_vals = np.abs(shap_vals)
        top_idx = int(np.argmax(abs_vals))
        top_feature = x_row.columns[top_idx]
        return FEATURE_LABEL_MAP.get(
            top_feature, top_feature.replace("_", " ").title()
        )
    except Exception as e:
        logger.warning("SHAP explanation failed: %s", e)
        return "Multiple factors"


# ---------------------------------------------------------------------------
# Probability calibration
# ---------------------------------------------------------------------------


def _fit_calibrator(
    predictions: np.ndarray, actuals: np.ndarray
) -> IsotonicRegression:
    """Fit isotonic regression for probability calibration.

    Maps raw predicted-vs-actual indicator to calibrated probabilities.
    """
    calibrator = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
    # Use normalized prediction residuals as calibration input
    if len(predictions) < 5:
        return calibrator
    residuals = actuals - predictions
    std = np.std(residuals)
    if std == 0:
        std = 1.0
    # Transform to rough probability scale using empirical CDF
    sorted_residuals = np.sort(residuals)
    ecdf_input = np.searchsorted(sorted_residuals, residuals) / len(residuals)
    calibrator.fit(ecdf_input, (actuals > predictions).astype(float))
    return calibrator


def calibrated_probability(
    p50: float,
    threshold: float,
    residual_std: float,
    calibrator: IsotonicRegression | None,
) -> float:
    """Calibrated probability that realized price > threshold.

    Uses a normal CDF estimate adjusted by isotonic calibration.
    """
    from scipy.stats import norm

    if residual_std <= 0:
        return float(p50 > threshold)
    raw_prob = float(norm.sf(threshold, loc=p50, scale=residual_std))
    if calibrator is None:
        return np.clip(raw_prob, 0.01, 0.99)
    try:
        calibrated = float(calibrator.predict([raw_prob])[0])
        return np.clip(calibrated, 0.01, 0.99)
    except Exception:
        return np.clip(raw_prob, 0.01, 0.99)


# ---------------------------------------------------------------------------
# Divergence detection
# ---------------------------------------------------------------------------


def check_divergence(p50: float, futures_spot: float, threshold_pct: float = 0.05) -> bool:
    """True if model p50 diverges from futures by more than threshold_pct."""
    if futures_spot <= 0:
        return False
    return abs(p50 - futures_spot) / futures_spot > threshold_pct


# ---------------------------------------------------------------------------
# PriceEnsemble
# ---------------------------------------------------------------------------


@dataclass
class EnsembleMetrics:
    """Training/validation/test metrics for a fitted ensemble."""

    mape_train: float = 0.0
    mape_val: float = 0.0
    rmse_val: float = 0.0
    futures_baseline_mape: float = 0.0
    n_train: int = 0
    n_val: int = 0
    coverage_90: float = 0.0  # val coverage (tautological after CQR)
    # Honest out-of-sample metrics on 2023–2024 test window
    mape_test: float = 0.0
    rmse_test: float = 0.0
    coverage_90_test: float = 0.0
    n_test: int = 0


@dataclass
class PriceEnsemble:
    """Ensemble model for one (commodity, horizon) pair.

    Components:
      1. SARIMAX — captures autocorrelation + exogenous WASDE/DXY signals
      2. LightGBM point — nonlinear feature interactions (p50)
      3. LightGBM quantile low — p10
      4. LightGBM quantile high — p90
      5. Ridge meta-learner — combines SARIMAX + LightGBM OOF predictions
      6. IsotonicRegression — probability calibration
    """

    commodity: str
    horizon: int
    model_ver: str = ""

    # Fitted model components (populated by .fit())
    arimax_result: Any = field(default=None, repr=False)
    lgbm_point: LGBMRegressor | None = field(default=None, repr=False)
    lgbm_q10: LGBMRegressor | None = field(default=None, repr=False)
    lgbm_q90: LGBMRegressor | None = field(default=None, repr=False)
    meta: Ridge | None = field(default=None, repr=False)
    calibrator: IsotonicRegression | None = field(default=None, repr=False)

    # Training distribution stats (for regime detection + calibration)
    train_feature_mean: np.ndarray | None = field(default=None, repr=False)
    train_feature_std: np.ndarray | None = field(default=None, repr=False)
    train_features_matrix: np.ndarray | None = field(default=None, repr=False)
    residual_std: float = 0.0

    # Conformalized Quantile Regression offset (Romano et al., 2019).
    # Widens lgbm_q10/q90 intervals by this amount at inference so that
    # marginal out-of-sample coverage ≥ (1 - alpha).
    conformity_offset: float = 0.0

    metrics: EnsembleMetrics = field(default_factory=EnsembleMetrics)

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        X_test: pd.DataFrame | None = None,
        y_test: pd.Series | None = None,
    ) -> EnsembleMetrics:
        """Fit all ensemble components.

        Parameters
        ----------
        X_train, X_val : DataFrames with feature columns from build_price_features.
        y_train, y_val : Target prices (realized price at horizon).
        """
        self.model_ver = date.today().strftime(MODEL_VERSION_FMT)

        X_lgbm_train = _get_lgbm_features(X_train)
        X_lgbm_val = _get_lgbm_features(X_val)

        # Store training distribution for regime detection
        self.train_features_matrix = X_lgbm_train.values.copy()
        self.train_feature_mean = np.nanmean(X_lgbm_train.values, axis=0)
        self.train_feature_std = np.nanstd(X_lgbm_train.values, axis=0)

        # ------------------------------------------------------------------
        # 1. SARIMAX
        # ------------------------------------------------------------------
        exog_train = _get_arimax_exog(X_train)
        exog_val = _get_arimax_exog(X_val)

        try:
            arimax_model = SARIMAX(
                y_train.values,
                exog=exog_train.values,
                order=(2, 1, 1),
                seasonal_order=(1, 0, 1, 12),
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            self.arimax_result = arimax_model.fit(disp=False, maxiter=200)
            arimax_train_pred = self.arimax_result.fittedvalues
            arimax_val_pred = self.arimax_result.forecast(
                steps=len(y_val), exog=exog_val.values
            )
        except Exception as e:
            logger.warning(
                "SARIMAX fit failed for %s h=%d: %s. Using LightGBM only.",
                self.commodity, self.horizon, e,
            )
            self.arimax_result = None
            arimax_train_pred = np.full(len(y_train), np.nan)
            arimax_val_pred = np.full(len(y_val), np.nan)

        # ------------------------------------------------------------------
        # 2. LightGBM point estimate
        # ------------------------------------------------------------------
        lgbm_params = {
            "n_estimators": 400,
            "learning_rate": 0.04,
            "max_depth": 4,
            "min_child_samples": 15,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 1.0,
            "random_state": 42,
            "verbose": -1,
        }

        self.lgbm_point = LGBMRegressor(objective="regression", **lgbm_params)
        self.lgbm_point.fit(
            X_lgbm_train, y_train,
            eval_set=[(X_lgbm_val, y_val)],
            callbacks=[],
        )
        lgbm_train_pred = self.lgbm_point.predict(X_lgbm_train)
        lgbm_val_pred = self.lgbm_point.predict(X_lgbm_val)

        # ------------------------------------------------------------------
        # 3. LightGBM quantile regressors (p10, p90)
        # ------------------------------------------------------------------
        self.lgbm_q10 = LGBMRegressor(
            objective="quantile", alpha=0.10, **lgbm_params
        )
        self.lgbm_q10.fit(X_lgbm_train, y_train)

        self.lgbm_q90 = LGBMRegressor(
            objective="quantile", alpha=0.90, **lgbm_params
        )
        self.lgbm_q90.fit(X_lgbm_train, y_train)

        # ------------------------------------------------------------------
        # 4. Ridge meta-learner on OOF predictions
        # ------------------------------------------------------------------
        # Stack ARIMAX + LightGBM val predictions
        arimax_val_clean = np.nan_to_num(arimax_val_pred, nan=np.nanmean(y_val))
        meta_X_val = np.column_stack([arimax_val_clean, lgbm_val_pred])

        self.meta = Ridge(alpha=1.0)
        self.meta.fit(meta_X_val, y_val)

        # ------------------------------------------------------------------
        # 5. Probability calibration
        # ------------------------------------------------------------------
        p50_val = self.meta.predict(meta_X_val)
        val_residuals = y_val.values - p50_val
        self.residual_std = float(np.std(val_residuals))
        self.calibrator = _fit_calibrator(p50_val, y_val.values)

        # ------------------------------------------------------------------
        # Metrics
        # ------------------------------------------------------------------
        p50_train_meta = self._meta_predict_raw(arimax_train_pred, lgbm_train_pred, y_train)
        p10_val_raw = self.lgbm_q10.predict(X_lgbm_val)
        p90_val_raw = self.lgbm_q90.predict(X_lgbm_val)

        # ------------------------------------------------------------------
        # 6. Conformalized Quantile Regression (CQR) — split val for honest coverage
        # ------------------------------------------------------------------
        # Previously the conformity offset was fit on the same val set used to
        # report coverage_90, making the val coverage tautological. We now split
        # val into cal / val_meas halves: cal fits the offset, val_meas gives
        # an honest marginal coverage reading that matches what the test set
        # will show (modulo regime drift). This is not a true fix for regime
        # non-exchangeability (val=2020-2022, test=2023-2024 are different
        # macro regimes) — the test-set coverage is still the deployment metric
        # — but it removes the leakage and eliminates the inflated val number.
        alpha = 0.10
        n_val_total = len(y_val)
        if n_val_total >= 10:
            cal_size = max(n_val_total // 2, 5)
            cal_idx = np.arange(cal_size)
            meas_idx = np.arange(cal_size, n_val_total)

            scores_cal = np.maximum(
                p10_val_raw[cal_idx] - y_val.values[cal_idx],
                y_val.values[cal_idx] - p90_val_raw[cal_idx],
            )
            level = min(1.0, (1 - alpha) * (1 + 1.0 / len(cal_idx)))
            q_hat = float(np.quantile(scores_cal, level))
            self.conformity_offset = max(0.0, q_hat)
            logger.info(
                "CQR conformity offset for %s h=%d: %.4f "
                "(cal n=%d, meas n=%d, level=%.3f)",
                self.commodity, self.horizon,
                self.conformity_offset, len(cal_idx), len(meas_idx), level,
            )

            # Reported val coverage is measured on the held-out half only
            p10_val_raw_meas = p10_val_raw[meas_idx] - self.conformity_offset
            p90_val_raw_meas = p90_val_raw[meas_idx] + self.conformity_offset
            y_val_meas = y_val.values[meas_idx]
            coverage_val_honest = _coverage(y_val_meas, p10_val_raw_meas, p90_val_raw_meas)
            # For downstream metrics that need widened val intervals across all rows
            p10_val = p10_val_raw - self.conformity_offset
            p90_val = p90_val_raw + self.conformity_offset
        elif n_val_total >= 5:
            # Too small for a split; fall back to non-split calibration but
            # the coverage number is still tautological — log a warning.
            scores = np.maximum(
                p10_val_raw - y_val.values,
                y_val.values - p90_val_raw,
            )
            level = min(1.0, (1 - alpha) * (1 + 1.0 / n_val_total))
            q_hat = float(np.quantile(scores, level))
            self.conformity_offset = max(0.0, q_hat)
            p10_val = p10_val_raw - self.conformity_offset
            p90_val = p90_val_raw + self.conformity_offset
            coverage_val_honest = _coverage(y_val.values, p10_val, p90_val)
            logger.warning(
                "Val set too small (n=%d) for split conformal; val coverage is "
                "tautological. Use test-set coverage as the deployment metric.",
                n_val_total,
            )
        else:
            self.conformity_offset = 0.0
            p10_val = p10_val_raw
            p90_val = p90_val_raw
            coverage_val_honest = _coverage(y_val.values, p10_val, p90_val)

        # ------------------------------------------------------------------
        # 7. Honest out-of-sample test metrics (2023–2024)
        # ------------------------------------------------------------------
        mape_test = 0.0
        rmse_test = 0.0
        cov_test = 0.0
        n_test = 0
        if X_test is not None and y_test is not None and len(y_test) > 0:
            X_lgbm_test = _get_lgbm_features(X_test)
            exog_test = _get_arimax_exog(X_test)
            # SARIMAX forecast on test (if available)
            if self.arimax_result is not None:
                try:
                    arimax_test_pred = np.asarray(
                        self.arimax_result.forecast(
                            steps=len(y_val) + len(y_test),
                            exog=np.vstack([exog_val.values, exog_test.values]),
                        )
                    )[-len(y_test):]
                except Exception:
                    arimax_test_pred = np.full(len(y_test), float(np.nanmean(y_train)))
            else:
                arimax_test_pred = np.full(len(y_test), float(np.nanmean(y_train)))

            lgbm_test_pred = self.lgbm_point.predict(X_lgbm_test)
            meta_X_test = np.column_stack([
                np.nan_to_num(arimax_test_pred, nan=float(np.nanmean(y_train))),
                lgbm_test_pred,
            ])
            p50_test = self.meta.predict(meta_X_test)
            p10_test_raw = self.lgbm_q10.predict(X_lgbm_test)
            p90_test_raw = self.lgbm_q90.predict(X_lgbm_test)
            p10_test = p10_test_raw - self.conformity_offset
            p90_test = p90_test_raw + self.conformity_offset
            # Enforce monotonicity row-wise
            p10_test = np.minimum(p10_test, p50_test)
            p90_test = np.maximum(p90_test, p50_test)

            mape_test = _mape(y_test.values, p50_test)
            rmse_test = _rmse(y_test.values, p50_test)
            cov_test = _coverage(y_test.values, p10_test, p90_test)
            n_test = len(y_test)
            logger.info(
                "Test metrics for %s h=%d: MAPE=%.2f%%, RMSE=%.4f, cov90=%.1f%%, n=%d",
                self.commodity, self.horizon,
                mape_test, rmse_test, cov_test * 100, n_test,
            )

        self.metrics = EnsembleMetrics(
            mape_train=_mape(y_train.values, p50_train_meta),
            mape_val=_mape(y_val.values, p50_val),
            rmse_val=_rmse(y_val.values, p50_val),
            n_train=len(y_train),
            n_val=len(y_val),
            coverage_90=coverage_val_honest,
            mape_test=mape_test,
            rmse_test=rmse_test,
            coverage_90_test=cov_test,
            n_test=n_test,
        )

        logger.info(
            "Fitted %s h=%d: MAPE_val=%.2f%%, RMSE_val=%.4f, coverage_90=%.1f%%, "
            "n_train=%d, n_val=%d",
            self.commodity, self.horizon,
            self.metrics.mape_val, self.metrics.rmse_val,
            self.metrics.coverage_90 * 100,
            self.metrics.n_train, self.metrics.n_val,
        )
        return self.metrics

    def _meta_predict_raw(
        self, arimax_pred: np.ndarray, lgbm_pred: np.ndarray, y_fallback: pd.Series
    ) -> np.ndarray:
        """Combine ARIMAX + LightGBM predictions through meta-learner."""
        arimax_clean = np.nan_to_num(arimax_pred, nan=float(np.nanmean(y_fallback)))
        meta_X = np.column_stack([arimax_clean, lgbm_pred])
        return self.meta.predict(meta_X)

    def predict(self, X: pd.DataFrame) -> dict:
        """Generate point + interval forecast for a single feature row.

        Returns
        -------
        dict with keys: p10, p50, p90, key_driver, regime_anomaly, divergence_flag
        """
        X_lgbm = _get_lgbm_features(X)

        # Regime check
        x_vec = X_lgbm.values[0].copy()
        x_vec = np.nan_to_num(x_vec, nan=0.0)
        regime_anomaly = is_regime_anomaly(
            x_vec, self.train_features_matrix
        ) if self.train_features_matrix is not None else False

        # ARIMAX prediction
        exog = _get_arimax_exog(X)
        if self.arimax_result is not None:
            try:
                arimax_pred = self.arimax_result.forecast(
                    steps=1, exog=exog.values
                )
                arimax_val = float(arimax_pred.iloc[0]) if hasattr(arimax_pred, 'iloc') else float(arimax_pred[0])
            except Exception:
                arimax_val = 0.0
        else:
            arimax_val = 0.0

        # LightGBM predictions
        lgbm_pred = float(self.lgbm_point.predict(X_lgbm)[0])
        p10_raw = float(self.lgbm_q10.predict(X_lgbm)[0])
        p90_raw = float(self.lgbm_q90.predict(X_lgbm)[0])

        # Meta-learner p50
        meta_X = np.array([[arimax_val, lgbm_pred]])
        p50 = float(self.meta.predict(meta_X)[0])

        # CQR widening (ensures ≥90% marginal coverage)
        p10 = p10_raw - self.conformity_offset
        p90 = p90_raw + self.conformity_offset

        # Enforce monotonicity: p50 must sit inside [p10, p90]
        p10 = min(p10, p50)
        p90 = max(p90, p50)

        # Key driver from SHAP
        key_driver = get_key_driver_label(self.lgbm_point, X_lgbm)

        # Divergence check
        futures_spot = float(X["futures_spot"].iloc[0]) if "futures_spot" in X.columns and pd.notna(X["futures_spot"].iloc[0]) else 0.0
        divergence = check_divergence(p50, futures_spot)

        return {
            "p10": round(p10, 4),
            "p50": round(p50, 4),
            "p90": round(p90, 4),
            "key_driver": key_driver,
            "regime_anomaly": regime_anomaly,
            "divergence_flag": divergence,
            "model_ver": self.model_ver,
        }

    def predict_probability(self, X: pd.DataFrame, threshold: float) -> float:
        """Calibrated probability that realized price > threshold."""
        result = self.predict(X)
        return calibrated_probability(
            result["p50"], threshold, self.residual_std, self.calibrator
        )

    def save(self, path: Path) -> None:
        """Persist ensemble to disk as a pickle file + HMAC-SHA256 sidecar."""
        from backend.models._signing import sign_artifact
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        sign_artifact(path)
        logger.info("Saved model to %s", path)

    @staticmethod
    def load(path: Path) -> PriceEnsemble:
        """Load a persisted ensemble; verifies HMAC when key is configured."""
        from backend.models._signing import ensure_verified_or_fail
        ensure_verified_or_fail(path)
        with open(path, "rb") as f:
            model = pickle.load(f)
        logger.info("Loaded model from %s", path)
        return model

    def to_bytes(self) -> bytes:
        """Serialize to bytes for S3 upload."""
        buf = io.BytesIO()
        pickle.dump(self, buf, protocol=pickle.HIGHEST_PROTOCOL)
        return buf.getvalue()

    @staticmethod
    def from_bytes(data: bytes) -> PriceEnsemble:
        """Deserialize from bytes (e.g., S3 download)."""
        buf = io.BytesIO(data)
        return pickle.load(buf)


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def _mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    mask = actual != 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100)


def _rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def _coverage(actual: np.ndarray, lower: np.ndarray, upper: np.ndarray) -> float:
    """Fraction of actuals within [lower, upper] interval."""
    within = (actual >= lower) & (actual <= upper)
    return float(np.mean(within))
