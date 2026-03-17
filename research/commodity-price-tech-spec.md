# Commodity Price Forecasting — Implementation Technical Specification
**Module:** Agricultural Dashboard · Prediction Module 02  
**Version:** 1.0 | **Date:** March 2026  
**Author:** Rajashekar Reddy Vedire  
**Stack:** Next.js + FastAPI + PostgreSQL + AWS EC2  
**Status:** Ready for implementation

---

## 1. Overview

This spec is a direct implementation guide for adding commodity price forecasting to the existing agricultural dashboard. It assumes the following are already operational:

- Next.js frontend deployed on Vercel (or EC2)
- FastAPI on AWS EC2 — existing endpoints live
- PostgreSQL on AWS RDS — existing tables for NASS data
- USDA NASS QuickStats pipeline running weekly

The module adds probabilistic price forecasts (p10/p50/p90) for corn, soybeans, and wheat at 1–6 month horizons, with calibrated probabilities ("64% chance corn stays above $4.20 through October") designed for farming decision support. It does **not** claim to beat futures markets — it surfaces when supply/demand fundamentals diverge materially from current futures pricing.

### 1.1 Stack Additions Required

| Component | Addition | Why |
|---|---|---|
| Python packages | `statsmodels`, `lightgbm`, `scikit-learn`, `shap` | ARIMAX + LightGBM ensemble + SHAP for key driver labels |
| Data sources | Nasdaq Data Link (CME futures), WASDE CSV, FRED API (DXY), NOAA Seasonal Outlooks | New signal categories not in existing pipeline |
| PostgreSQL | 3 new tables: `futures_daily`, `wasde_releases`, `price_forecasts` | Price-specific storage |
| FastAPI | 3 new route files under `routers/price.py` | Extends existing router structure |
| Next.js | 3 new components + 1 new page section | Fan chart, probability gauge, key driver callout |
| Cron | 1 new monthly job (post-WASDE trigger) + daily futures pull added to existing morning ETL | Price data update cadence |

---

## 2. Database Schema

Add these tables to the existing RDS PostgreSQL instance via Alembic migration.

```sql
-- Daily futures prices (corn, soy, wheat — nearest and deferred contracts)
CREATE TABLE futures_daily (
    id              BIGSERIAL PRIMARY KEY,
    trade_date      DATE          NOT NULL,
    commodity       VARCHAR(10)   NOT NULL,  -- 'corn' | 'soybean' | 'wheat'
    contract_month  VARCHAR(7)    NOT NULL,  -- 'YYYY-MM' (e.g. '2026-12')
    settlement      NUMERIC(8,4)  NOT NULL,  -- USD per bushel
    open_interest   INTEGER,
    volume          INTEGER,
    source          VARCHAR(30)   DEFAULT 'nasdaq_dl',
    ingest_ts       TIMESTAMPTZ   DEFAULT NOW(),
    UNIQUE (trade_date, commodity, contract_month)
);

-- WASDE monthly release snapshots
CREATE TABLE wasde_releases (
    id              BIGSERIAL PRIMARY KEY,
    release_date    DATE          NOT NULL,
    commodity       VARCHAR(10)   NOT NULL,
    marketing_year  VARCHAR(9)    NOT NULL,  -- e.g. '2025-2026'
    us_production   NUMERIC(10,2),           -- million bushels
    us_exports      NUMERIC(10,2),
    ending_stocks   NUMERIC(10,2),
    stocks_to_use   NUMERIC(6,4),            -- ratio (e.g. 0.112)
    world_production NUMERIC(10,2),
    source          VARCHAR(30)   DEFAULT 'usda_wasde',
    UNIQUE (release_date, commodity, marketing_year)
);

-- Price forecast outputs (immutable — never overwrite historical runs)
CREATE TABLE price_forecasts (
    id              BIGSERIAL PRIMARY KEY,
    run_date        DATE          NOT NULL,
    commodity       VARCHAR(10)   NOT NULL,
    horizon_month   VARCHAR(7)    NOT NULL,  -- 'YYYY-MM' (forecast target month)
    p10             NUMERIC(8,4)  NOT NULL,  -- USD/bu
    p50             NUMERIC(8,4)  NOT NULL,
    p90             NUMERIC(8,4)  NOT NULL,
    prob_above_threshold NUMERIC(5,4),       -- calibrated probability (0–1)
    threshold_price NUMERIC(8,4),            -- price used for prob calculation
    key_driver      VARCHAR(100),            -- SHAP top feature label (plain text)
    divergence_flag BOOLEAN       DEFAULT FALSE,  -- TRUE if model diverges from futures
    model_ver       VARCHAR(20)   NOT NULL,
    regime_anomaly  BOOLEAN       DEFAULT FALSE,  -- TRUE if OOD — defer to futures
    created_at      TIMESTAMPTZ   DEFAULT NOW(),
    UNIQUE (run_date, commodity, horizon_month, model_ver)
);

-- Alembic migration file: migrations/versions/003_price_forecasting.py
```

---

## 3. Data Sources & Ingestion

### 3.1 CME Futures — Nasdaq Data Link

**File:** `etl/ingest_futures.py`

```python
import requests
import pandas as pd
from datetime import date, timedelta

NASDAQ_API_KEY = os.environ["NASDAQ_DL_API_KEY"]

TICKER_MAP = {
    "corn":    "CHRIS/CME_C1",   # nearest continuous corn contract
    "soybean": "CHRIS/CME_S1",   # nearest continuous soybean contract
    "wheat":   "CHRIS/CME_W1",   # nearest continuous wheat contract
}

def fetch_futures(commodity: str, start_date: str) -> pd.DataFrame:
    ticker = TICKER_MAP[commodity]
    url = f"https://data.nasdaq.com/api/v3/datasets/{ticker}.json"
    params = {
        "api_key": NASDAQ_API_KEY,
        "start_date": start_date,
        "column_index": "4,5,6",  # Settle, Volume, Open Interest
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()["dataset"]
    df = pd.DataFrame(data["data"], columns=["trade_date", "settlement", "volume", "open_interest"])
    df["commodity"] = commodity
    df["contract_month"] = infer_contract_month(commodity)  # from active contract code
    return df

def run_daily_futures_ingest():
    """Run as part of existing morning ETL — add to run_pipeline.sh after NASS pull."""
    start = (date.today() - timedelta(days=5)).isoformat()
    for commodity in ["corn", "soybean", "wheat"]:
        df = fetch_futures(commodity, start_date=start)
        upsert_futures(df)  # INSERT ... ON CONFLICT DO UPDATE SET settlement=EXCLUDED.settlement

# Cron: add to existing morning ETL — daily at 07:00 ET (after CME close previous day)
```

**Free tier:** 50 API calls/day. Daily pull for 3 commodities = 3 calls/day. Well within limit.

---

### 3.2 USDA WASDE — Monthly CSV

**File:** `etl/ingest_wasde.py`

WASDE releases monthly, typically the 11th. The machine-readable CSV (available since 2020) is preferred over PDF parsing.

```python
WASDE_BASE = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"

def fetch_wasde() -> pd.DataFrame:
    """Download WASDE PSD dataset (all commodities, all years). ~15MB zip."""
    r = requests.get(WASDE_BASE, timeout=60)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        df = pd.read_csv(z.open("psd_alldata.csv"), low_memory=False)
    
    # Filter to US, relevant commodities, key attributes
    target_commodities = {"Corn": "corn", "Soybeans": "soybean", "Wheat": "wheat"}
    target_attrs = ["Beginning Stocks", "Production", "Exports", "Ending Stocks"]
    
    df = df[
        (df["Country_Name"] == "United States") &
        (df["Commodity_Description"].isin(target_commodities)) &
        (df["Attribute_Description"].isin(target_attrs))
    ]
    return pivot_to_wasde_schema(df)

def compute_stocks_to_use(df: pd.DataFrame) -> pd.DataFrame:
    """Stocks-to-use = ending_stocks / (production + beginning_stocks - exports)"""
    # ...
    return df

# Cron: monthly, day after WASDE release (~12th of month)
# Add to run_pipeline.sh with flag: python etl/ingest_wasde.py --monthly
```

---

### 3.3 FRED — US Dollar Index (DXY)

**File:** `etl/ingest_fred.py`  
One API call per daily ETL run — add to existing morning ETL.

```python
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = os.environ["FRED_API_KEY"]  # free registration at fred.stlouisfed.org

def fetch_dxy(start_date: str) -> pd.DataFrame:
    params = {
        "series_id": "DTWEXBGS",  # Trade Weighted USD Index — Broad Goods
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
    }
    r = requests.get(FRED_BASE, params=params, timeout=20)
    df = pd.DataFrame(r.json()["observations"])[["date", "value"]]
    df.columns = ["trade_date", "dxy"]
    df["dxy"] = pd.to_numeric(df["dxy"], errors="coerce")
    return df.dropna()
```

---

### 3.4 USDA ERS Production Costs

Annual download. Pull once per year in January. Store in a static RDS table `ers_production_costs(year, commodity, variable_cost_per_bu, total_cost_per_bu)`.

```bash
# Annual pull — add to January run
wget "https://www.ers.usda.gov/webdocs/DataFiles/50048/corncostandreturn.xlsx" -O data/ers_corn_costs.xlsx
# Repeat for soybeans and wheat
python etl/load_ers_costs.py --year 2025
```

---

### 3.5 ERS Fertilizer Prices

Quarterly. Use anhydrous ammonia (82-0-0) as the proxy for corn nitrogen cost.

```python
FERTILIZER_URL = "https://www.ers.usda.gov/webdocs/DataFiles/50048/fertilizerprices.xlsx"

def fetch_fertilizer_prices() -> pd.DataFrame:
    df = pd.read_excel(FERTILIZER_URL, sheet_name="Anhydrous ammonia")
    # Reshape to long format: [quarter, anhydrous_price_per_ton]
    return df
```

---

## 4. Feature Engineering

**File:** `features/price_features.py`

### 4.1 Feature Matrix Construction

All features are computed as of a given `as_of_date`. Monthly updates use November 1 of each year as the base for seasonal features.

```python
def build_price_features(commodity: str, as_of_date: date, horizon_months: int) -> pd.DataFrame:
    """
    Returns one row per (commodity, horizon_month) with all features.
    as_of_date: the date from which the forecast is issued
    horizon_months: 1–6
    """
    features = {}
    
    # Market microstructure (from futures_daily)
    features["futures_spot"]        = get_nearest_futures(commodity, as_of_date)
    features["futures_deferred"]    = get_deferred_futures(commodity, as_of_date, months=6)
    features["basis"]               = features["futures_spot"] - get_cash_price(commodity, as_of_date)
    features["term_spread"]         = features["futures_deferred"] - features["futures_spot"]
    features["open_interest_chg"]   = get_oi_change(commodity, as_of_date, lookback_days=30)
    
    # Fundamental supply/demand (from wasde_releases)
    features["stocks_to_use"]       = get_latest_wasde(commodity, as_of_date, "stocks_to_use")
    features["stocks_to_use_pctile"] = get_historical_percentile(commodity, "stocks_to_use", features["stocks_to_use"])
    features["wasde_surprise"]      = compute_wasde_surprise(commodity, as_of_date)  # current vs. prior month
    features["world_stocks_to_use"] = get_latest_wasde(commodity, as_of_date, "world_stocks_to_use")
    
    # Macroeconomic (from FRED)
    features["dxy"]                 = get_dxy(as_of_date)
    features["dxy_chg_30d"]         = get_dxy_change(as_of_date, days=30)
    
    # Agricultural stress (from Drought Monitor + NASS)
    features["drought_extent_pct"]  = get_drought_extent(commodity, as_of_date)  # major production states
    features["crop_condition_cci"]  = get_cci(commodity, as_of_date)             # if in-season
    
    # Cost structure (from ERS)
    features["production_cost_bu"]  = get_production_cost(commodity, as_of_date.year)
    features["price_cost_ratio"]    = features["futures_spot"] / features["production_cost_bu"]
    
    # Corn-soy interaction (for corn and soybean forecasting)
    if commodity in ["corn", "soybean"]:
        corn_price = get_nearest_futures("corn", as_of_date)
        soy_price  = get_nearest_futures("soybean", as_of_date)
        features["corn_soy_ratio"]  = corn_price / soy_price
    
    # Prior-year price (mean reversion anchor)
    features["prior_year_price"]    = get_historical_price(commodity, as_of_date - timedelta(days=365))
    features["seasonal_factor"]     = compute_seasonal_factor(commodity, as_of_date.month)
    
    # Horizon-specific: target variable label (for training only)
    features["horizon_months"]      = horizon_months
    
    return pd.Series(features)
```

### 4.2 WASDE Surprise Signal

This is one of the few genuine edges in commodity price prediction — the market moves when WASDE surprises relative to expectations.

```python
def compute_wasde_surprise(commodity: str, as_of_date: date) -> float:
    """
    Returns the change in stocks-to-use from prior WASDE release to current.
    Negative = bullish (less supply than expected).
    Positive = bearish (more supply).
    """
    current = get_wasde_release(commodity, as_of_date)
    prior   = get_wasde_release(commodity, as_of_date - timedelta(days=35))  # ~prior month
    if current is None or prior is None:
        return 0.0
    return current.stocks_to_use - prior.stocks_to_use
```

---

## 5. Model Architecture

### 5.1 Ensemble Components

**File:** `models/price_model.py`

Three model components, one meta-learner:

```python
from statsmodels.tsa.statespace.sarimax import SARIMAX
import lightgbm as lgb
from sklearn.linear_model import Ridge
from sklearn.isotonic import IsotonicRegression

class PriceEnsemble:
    def __init__(self, commodity: str, horizon: int):
        self.commodity = commodity
        self.horizon   = horizon
        self.arimax    = None   # SARIMAX for autocorrelation + WASDE surprise
        self.xgb       = None   # LightGBM for nonlinear feature interactions
        self.q_low     = None   # LightGBM quantile p10
        self.q_high    = None   # LightGBM quantile p90
        self.meta      = None   # Ridge meta-learner on OOF predictions
        self.calibrator = None  # IsotonicRegression for probability calibration
    
    def fit(self, X_train, y_train, X_val, y_val):
        # 1. ARIMAX — WASDE surprise as exogenous variable
        self.arimax = SARIMAX(
            y_train,
            exog=X_train[["wasde_surprise", "dxy", "drought_extent_pct"]],
            order=(2, 1, 1),
            seasonal_order=(1, 0, 1, 12)
        ).fit(disp=False)
        
        # 2. LightGBM (point + quantile)
        lgb_params = {"objective": "regression", "n_estimators": 400, "learning_rate": 0.04,
                      "max_depth": 4, "min_child_samples": 15, "subsample": 0.8}
        self.xgb = lgb.LGBMRegressor(**lgb_params).fit(X_train, y_train)
        
        self.q_low  = lgb.LGBMRegressor(**{**lgb_params, "objective": "quantile", "alpha": 0.10}).fit(X_train, y_train)
        self.q_high = lgb.LGBMRegressor(**{**lgb_params, "objective": "quantile", "alpha": 0.90}).fit(X_train, y_train)
        
        # 3. Meta-learner on OOF predictions
        oof_arimax = self.arimax.predict(start=len(y_train), end=len(y_train)+len(y_val)-1, exog=X_val[["wasde_surprise", "dxy", "drought_extent_pct"]])
        oof_xgb    = self.xgb.predict(X_val)
        meta_X     = np.column_stack([oof_arimax, oof_xgb])
        self.meta  = Ridge(alpha=1.0).fit(meta_X, y_val)
        
        # 4. Probability calibration (train on val set)
        p50_preds = self.predict_point(X_val)
        self.calibrator = fit_calibrator(p50_preds, y_val)  # IsotonicRegression
    
    def predict_interval(self, X) -> dict:
        arimax_pred = self.arimax.forecast(steps=self.horizon, exog=X[["wasde_surprise", "dxy", "drought_extent_pct"]])
        xgb_pred    = self.xgb.predict(X)
        p50 = self.meta.predict(np.column_stack([arimax_pred, xgb_pred]))[0]
        p10 = self.q_low.predict(X)[0]
        p90 = self.q_high.predict(X)[0]
        # Enforce monotonicity
        p10 = min(p10, p50)
        p90 = max(p90, p50)
        return {"p10": p10, "p50": p50, "p90": p90}
    
    def predict_probability(self, X, threshold: float) -> float:
        """Calibrated probability price stays above threshold through horizon month."""
        p50 = self.predict_point(X)
        raw_prob = float(p50 > threshold)  # placeholder — replace with proper CDF
        return float(self.calibrator.predict([raw_prob])[0])
```

### 5.2 Regime Anomaly Detection

```python
def is_regime_anomaly(X_current: pd.Series, X_train: pd.DataFrame, threshold_sigma: float = 3.0) -> bool:
    """
    Returns True if current feature vector is statistically outside training distribution.
    Uses Mahalanobis distance. When True, suppress ML forecast and display futures curve only.
    """
    from scipy.spatial.distance import mahalanobis
    cov = np.cov(X_train.T)
    cov_inv = np.linalg.pinv(cov)
    dist = mahalanobis(X_current, X_train.mean(), cov_inv)
    return dist > threshold_sigma
```

### 5.3 Key Driver Label (SHAP)

```python
import shap

def get_key_driver_label(model, X_row: pd.Series) -> str:
    """Returns plain-English label of the top SHAP feature for this forecast."""
    explainer = shap.TreeExplainer(model.xgb)
    shap_vals  = explainer.shap_values(X_row.to_frame().T)[0]
    top_feature = pd.Series(dict(zip(X_row.index, abs(shap_vals)))).idxmax()
    
    label_map = {
        "stocks_to_use":        "USDA stocks-to-use ratio",
        "wasde_surprise":       "WASDE monthly supply surprise",
        "dxy":                  "US dollar strength (DXY)",
        "drought_extent_pct":   "Drought extent in production region",
        "corn_soy_ratio":       "Corn-to-soybean price ratio",
        "production_cost_bu":   "Cost of production floor",
        "crop_condition_cci":   "In-season crop condition ratings",
    }
    return label_map.get(top_feature, top_feature.replace("_", " ").title())
```

### 5.4 Training Configuration

```python
# Walk-forward training — never use future data
TRAIN_YEARS = range(2010, 2020)  # 10 years
VAL_YEARS   = range(2020, 2023)  # tune hyperparameters here
TEST_YEARS  = range(2023, 2025)  # reported test accuracy — not tuned on

HORIZONS    = [1, 2, 3, 4, 5, 6]  # months
COMMODITIES = ["corn", "soybean", "wheat"]

# One PriceEnsemble per (commodity, horizon) = 3 × 6 = 18 model sets
# Each model set: 1 ARIMAX + 2 LightGBM (point + quantile) + 1 Ridge meta = 4 objects
# Total artifacts: 72 — stored in S3 models/price/{commodity}/horizon_{N}/
```

### 5.5 Baseline Gate

Before deploying, compare model vs. futures curve benchmark:

```python
def futures_baseline_mape(commodity, horizon, test_years) -> float:
    """MAPE of simply using the CME futures price at horizon as the forecast."""
    errors = []
    for year in test_years:
        futures_forecast = get_futures_price_as_of(commodity, year, months_ahead=horizon)
        actual           = get_realized_price(commodity, year, horizon)
        errors.append(abs(futures_forecast - actual) / actual)
    return np.mean(errors) * 100

# Deployment rule: if model MAPE > futures MAPE + 1.5pp on test set,
# demote to "fundamental divergence signal" mode — display futures curve as forecast.
```

---

## 6. API Specification

**File:** `routers/price.py`  
Register in `main.py`: `app.include_router(price_router, prefix="/api/v1/predict/price")`

### Endpoints

---

**`GET /api/v1/predict/price`**

```python
@router.get("/")
async def get_price_forecast(
    commodity: str = Query(..., regex="^(corn|soybean|wheat)$"),
    horizon_months: int = Query(default=3, ge=1, le=6),
    db: AsyncSession = Depends(get_db)
) -> PriceForecastResponse:
```

Response schema:
```json
{
  "commodity": "corn",
  "run_date": "2026-03-01",
  "horizon_month": "2026-06",
  "p10": 4.05,
  "p50": 4.38,
  "p90": 4.71,
  "unit": "USD/bushel",
  "key_driver": "USDA stocks-to-use ratio",
  "divergence_flag": false,
  "regime_anomaly": false,
  "model_ver": "2026-03-01"
}
```

---

**`GET /api/v1/predict/price/probability`**

Returns calibrated probability that price exceeds a given threshold through the horizon month.

```python
@router.get("/probability")
async def get_price_probability(
    commodity: str,
    threshold_price: float,
    horizon_months: int = Query(default=3, ge=1, le=6),
    db: AsyncSession = Depends(get_db)
) -> ProbabilityResponse:
```

Response:
```json
{
  "commodity": "corn",
  "threshold_price": 4.20,
  "horizon_month": "2026-06",
  "probability": 0.64,
  "confidence_note": "Based on calibrated ensemble; ±8pp historical calibration error"
}
```

---

**`GET /api/v1/predict/price/wasde-signal`**

```python
@router.get("/wasde-signal")
async def get_wasde_signal(
    commodity: str,
    db: AsyncSession = Depends(get_db)
) -> WasdeSignalResponse:
```

Response:
```json
{
  "commodity": "corn",
  "release_date": "2026-03-11",
  "stocks_to_use": 0.108,
  "stocks_to_use_pctile": 18,
  "prior_month_stu": 0.112,
  "surprise": -0.004,
  "surprise_direction": "bullish",
  "historical_context": "Stocks-to-use at 18th percentile since 2000 — historically bullish for prices"
}
```

---

**`GET /api/v1/predict/price/history`**

Returns historical model forecast vs. realized prices for accuracy retrospective.

```json
[
  {"run_date": "2025-03-01", "horizon_month": "2025-06", "p50": 4.21, "actual": 4.18, "error_pct": 0.7},
  ...
]
```

---

## 7. Frontend Integration

### 7.1 New Components

**File locations** (Next.js project):
```
components/predictions/
├── PriceFanChart.jsx          ← 6-month forward fan chart (p10–p90 bands)
├── ProbabilityGauge.jsx       ← Single probability number + user threshold input
├── KeyDriverCallout.jsx       ← Plain-language SHAP driver card
├── WasdeSignalCard.jsx        ← Stocks-to-use percentile + surprise direction
└── PriceRegimeAlert.jsx       ← Banner shown when regime_anomaly = true
```

### 7.2 PriceFanChart.jsx — Spec

Uses Recharts (already likely in stack). Renders p10/p50/p90 bands as an area chart with the CME futures curve overlaid as a reference line.

```jsx
import { AreaChart, Area, Line, XAxis, YAxis, Tooltip, ReferenceLine } from 'recharts';

// data shape: [{month: 'Apr', p10: 4.1, p50: 4.4, p90: 4.7, futures: 4.3}, ...]
// If divergence_flag = true: show annotation "Model diverges from futures — see fundamentals"
// If regime_anomaly = true: hide area chart, show only futures line + alert banner
```

### 7.3 ProbabilityGauge.jsx — Spec

```jsx
// Props: commodity, horizonMonths
// State: thresholdPrice (user-adjustable slider or input)
// API call: GET /predict/price/probability?commodity=corn&threshold_price={thresholdPrice}&horizon_months={horizonMonths}
// Display: Large percentage number + color (green > 60%, amber 40–60%, red < 40%)
// Label below: "chance {commodity} stays above ${threshold} through {horizonMonth}"
```

### 7.4 Regime Anomaly Banner

When `regime_anomaly = true` on any forecast response:

```jsx
<PriceRegimeAlert>
  Current market conditions are statistically outside our model's training range.
  Displaying CME futures curve only — fundamental signals are advisory.
</PriceRegimeAlert>
```

This banner must be impossible to miss and must not be hidden behind a toggle.

---

## 8. Automation & Scheduling

### 8.1 Add to Existing `run_pipeline.sh`

```bash
#!/bin/bash
# Existing pipeline additions for commodity price module

# --- DAILY (already runs 07:00 ET) ---
python etl/ingest_futures.py          # NEW: CME futures daily pull
python etl/ingest_fred.py             # NEW: DXY daily pull

# --- WEEKLY (existing Thursday run) ---
# (no changes — NASS + drought monitor already here)

# --- MONTHLY (new — add to EventBridge rule for ~12th of month) ---
python etl/ingest_wasde.py --monthly  # NEW: WASDE release pull
python models/price_model.py --run-inference  # NEW: monthly forecast update
```

### 8.2 New EventBridge Rule — Monthly WASDE Trigger

```json
{
  "Name": "ag-price-forecast-monthly",
  "ScheduleExpression": "cron(0 14 12 * ? *)",
  "Description": "Trigger price forecast pipeline on 12th of each month at 14:00 UTC (day after WASDE)",
  "Targets": [{
    "Id": "price-forecast-run",
    "Arn": "arn:aws:ssm:us-east-1:...:automation-definition/RunShellScript",
    "Input": "{\"commands\": [\"cd /opt/ag-pipeline && bash run_pipeline.sh --monthly\"]}"
  }]
}
```

---

## 9. Stack Enhancements for This Module

| Area | Current | Recommended Addition | Priority |
|---|---|---|---|
| **Python packages** | Existing ETL deps | Add `statsmodels`, `shap`, `lightgbm` (may already have) | Required |
| **Feature validation** | None noted | Add `pandera` DataFrameSchema on price feature matrix | High |
| **Calibration testing** | None | Add calibration reliability diagram to model evaluation notebook | High |
| **API rate limiting** | None noted | Add `slowapi` rate limiter to price endpoints (abuse vector for probability queries) | Medium |
| **Secrets** | `.env` on EC2 | Move `NASDAQ_DL_API_KEY` and `FRED_API_KEY` to AWS Secrets Manager | Medium |
| **WASDE parser resilience** | N/A | Add a fallback CSV URL if primary download fails; test monthly in CI | Medium |
| **Data freshness check** | None | Add `/api/v1/predict/price/health` endpoint returning last ingest timestamps | Low |

---

## 10. Environment Variables

Add to existing `.env` / AWS Secrets Manager:

```bash
# New — Commodity Price Module
NASDAQ_DL_API_KEY=        # Nasdaq Data Link — free registration at data.nasdaq.com
FRED_API_KEY=             # FRED API — free registration at fred.stlouisfed.org
WASDE_DOWNLOAD_URL=https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip

# Existing (already set)
DB_HOST=
DB_PORT=5432
DB_NAME=ag_dashboard
DB_USER=ag_app
DB_PASSWORD=
S3_BUCKET=ag-dashboard
AWS_REGION=us-east-1
```

---

## 11. Testing Checklist

- [ ] `test_futures_ingest` — assert settlement prices land in `futures_daily`; verify no gaps > 3 trading days
- [ ] `test_wasde_ingest` — assert stocks-to-use computable from parsed columns
- [ ] `test_wasde_surprise_sign` — verify surprise is negative when ending stocks decrease month-over-month
- [ ] `test_ensemble_monotonicity` — assert p10 < p50 < p90 for all commodities × horizons
- [ ] `test_regime_anomaly_flag` — assert anomaly fires correctly on synthetic OOD inputs
- [ ] `test_probability_calibration` — assert calibrated probs are within 8pp of empirical frequencies
- [ ] `test_api_probability_endpoint` — assert probability ∈ [0, 1]; assert 400 for unknown commodity
- [ ] `test_futures_baseline_gate` — assert model MAPE ≤ futures MAPE + 1.5pp on 2023–2024 test set

---

## 12. Glossary

| Term | Definition |
|---|---|
| WASDE | World Agricultural Supply and Demand Estimates — USDA monthly supply/demand report |
| MAPE | Mean Absolute Percentage Error — forecast accuracy metric |
| Stocks-to-use | Ending stocks ÷ total use — primary supply tightness indicator |
| DXY | US Dollar Index — inverse relationship with grain export demand |
| Basis | Cash price minus futures price — measures local market premium/discount |
| Term spread | Deferred futures price minus spot futures price — contango/backwardation signal |
| p10/p50/p90 | 10th, 50th, 90th percentile — forecast uncertainty interval |
| Regime anomaly | Current market conditions statistically outside model's training distribution |
| SHAP | SHapley Additive exPlanations — model interpretability framework |
| OOF | Out-of-fold — predictions made on held-out validation data, used to train meta-learner |
