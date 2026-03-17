# Planted Acreage Prediction — Implementation Technical Specification
**Module:** Agricultural Dashboard · Prediction Module 03  
**Version:** 1.0 | **Date:** March 2026  
**Author:** Rajashekar Reddy Vedire  
**Stack:** Next.js + FastAPI + PostgreSQL + AWS EC2  
**Dependency:** Module 01 infrastructure (NASS pipeline) + Module 02 CME futures data  
**Status:** Ready for implementation — build after Module 02 CME futures ingest is live

---

## 1. Overview

This spec is a direct implementation guide for adding planted acreage prediction to the existing agricultural dashboard. The module forecasts state-level acres planted for corn, soybeans, and wheat **before** USDA's Prospective Plantings report (published March 31 each year), giving users 6+ weeks of advance visibility into next season's supply picture.

### 1.1 Infrastructure Leverage

This is the highest-leverage module to implement because it reuses nearly everything already in the pipeline:

| Component | Source | Reuse Level |
|---|---|---|
| NASS QuickStats pipeline | Module 01 / existing | Full reuse — historical acreage already there |
| CME futures data (`futures_daily` table) | Module 02 | Full reuse — just query November contracts |
| RDS PostgreSQL | Existing | Add 2 tables |
| EC2 + EventBridge | Existing | Add 1 annual cron job |
| FastAPI structure | Existing | Add 1 new router file |

Net new work: ERS production costs (annual download), ERS fertilizer prices (quarterly), 2 new models, 2 new DB tables, 3 new API endpoints, 3 new frontend components.

### 1.2 Key Constraint: Annual Cadence

Unlike yield (weekly) and price (monthly), acreage is an **annual** prediction. One forecast per year, published in February. This means:

- No weekly ETL additions needed
- EventBridge trigger fires once per year (February 1)
- Model retrains once per year (January, after ERS cost data updates)
- The UI shows the forecast for the entire pre-season window (February → March 31), then switches to USDA vs. model comparison mode after March 31

---

## 2. Database Schema

```sql
-- Acreage forecast outputs (immutable)
CREATE TABLE acreage_forecasts (
    id              BIGSERIAL PRIMARY KEY,
    forecast_year   SMALLINT      NOT NULL,  -- the planting year being forecast
    state_fips      CHAR(2)       NOT NULL,  -- state FIPS (02-digit) or '00' for national
    commodity       VARCHAR(10)   NOT NULL,  -- 'corn' | 'soybean' | 'wheat'
    forecast_acres  NUMERIC(10,1) NOT NULL,  -- millions of acres
    p10_acres       NUMERIC(10,1),
    p90_acres       NUMERIC(10,1),
    corn_soy_ratio  NUMERIC(6,4),            -- the price ratio used in forecast
    key_driver      VARCHAR(100),            -- top factor label
    model_ver       VARCHAR(20)   NOT NULL,
    published_at    DATE          NOT NULL,  -- date forecast was made public (should be ~Feb 1)
    created_at      TIMESTAMPTZ   DEFAULT NOW(),
    UNIQUE (forecast_year, state_fips, commodity, model_ver)
);

-- Accuracy tracking — populated after USDA releases March 31 + June actuals
CREATE TABLE acreage_accuracy (
    id              BIGSERIAL PRIMARY KEY,
    forecast_year   SMALLINT      NOT NULL,
    state_fips      CHAR(2)       NOT NULL,
    commodity       VARCHAR(10)   NOT NULL,
    model_forecast  NUMERIC(10,1) NOT NULL,  -- our February prediction
    usda_prospective NUMERIC(10,1),          -- USDA March 31 Prospective Plantings
    usda_june_actual NUMERIC(10,1),          -- USDA June Area Survey (ground truth)
    model_vs_usda_pct NUMERIC(6,2),          -- % difference vs. USDA March report
    model_vs_actual_pct NUMERIC(6,2),        -- % difference vs. June actuals
    updated_at      TIMESTAMPTZ   DEFAULT NOW(),
    UNIQUE (forecast_year, state_fips, commodity)
);

-- ERS production costs (static annual — one-time load + annual update)
CREATE TABLE ers_production_costs (
    id              BIGSERIAL PRIMARY KEY,
    year            SMALLINT      NOT NULL,
    commodity       VARCHAR(10)   NOT NULL,
    variable_cost_per_bu NUMERIC(8,4),  -- USD/bushel (seed, fertilizer, fuel, etc.)
    total_cost_per_bu    NUMERIC(8,4),  -- includes fixed costs
    fertilizer_cost_acre NUMERIC(8,2),  -- USD/acre
    UNIQUE (year, commodity)
);

-- ERS fertilizer prices (quarterly — proxy for corn nitrogen cost asymmetry)
CREATE TABLE ers_fertilizer_prices (
    id              BIGSERIAL PRIMARY KEY,
    quarter         VARCHAR(7)    NOT NULL,  -- 'YYYY-QN' e.g. '2025-Q3'
    anhydrous_ammonia_ton NUMERIC(8,2),      -- USD/ton — primary corn N proxy
    dap_ton              NUMERIC(8,2),       -- diammonium phosphate
    potash_ton           NUMERIC(8,2),
    UNIQUE (quarter)
);
```

---

## 3. Data Sources & Ingestion

### 3.1 NASS Historical Acreage (Already in Pipeline)

The existing NASS pipeline pulls crop condition and yield data. Extend it to also pull planted acreage history:

```python
# Add to existing etl/ingest_nass.py — one additional API call
def fetch_nass_acreage(state_fips: str = None, start_year: int = 1980):
    """Pull historical planted acreage at state level from QuickStats."""
    params = {
        "key": NASS_API_KEY,
        "statisticcat_desc": "AREA PLANTED",
        "commodity_desc": "CORN",  # repeat for SOYBEANS, WHEAT
        "agg_level_desc": "STATE",
        "year__GE": str(start_year),
        "format": "JSON",
    }
    # ... fetch, clean, upsert to feature store
```

This is a one-time backfill to 1980, then annual update. Attach to existing NASS Thursday job with a flag: `python etl/ingest_nass.py --include-acreage`.

### 3.2 CME November Contracts (From Module 02)

The planted acreage model uses November 1 futures prices as the core economic signal. Since `futures_daily` is populated by Module 02, this is a pure query — no new ingest needed.

```python
def get_november_price_ratio(year: int) -> float:
    """
    Corn/soy price ratio as of November 1 of the prior year.
    This is the decision-time price ratio farmers use for next-year planting.
    Uses December corn and November soybean contracts.
    """
    as_of = date(year - 1, 11, 1)  # prior November 1
    
    corn_dec = query_futures("corn", as_of, contract_month=f"{year-1}-12")
    soy_nov  = query_futures("soybean", as_of, contract_month=f"{year-1}-11")
    
    if corn_dec is None or soy_nov is None:
        raise DataUnavailableError(f"Missing futures for Nov 1, {year-1}")
    
    return corn_dec.settlement / soy_nov.settlement
```

### 3.3 ERS Production Costs — Annual Download

**File:** `etl/ingest_ers_costs.py`  
Runs once in January each year. Manual trigger is acceptable — add to January EventBridge rule.

```python
ERS_COST_URLS = {
    "corn":    "https://www.ers.usda.gov/webdocs/DataFiles/50048/corncostandreturn.xlsx",
    "soybean": "https://www.ers.usda.gov/webdocs/DataFiles/50048/soybeanscostandreturn.xlsx",
    "wheat":   "https://www.ers.usda.gov/webdocs/DataFiles/50048/wheatcostandreturn.xlsx",
}

def ingest_ers_costs(year: int):
    for commodity, url in ERS_COST_URLS.items():
        df = pd.read_excel(url, sheet_name="Sheet1", header=3)
        # ERS Excel format: rows are cost categories, columns are years
        # Extract: variable costs per bushel, total costs per bushel, fertilizer cost per acre
        row = extract_cost_row(df, year)
        upsert_ers_cost(year, commodity, row)

# Cron: add to January 15 EventBridge rule
# aws events put-rule --schedule-expression "cron(0 12 15 1 ? *)" --name "ag-ers-annual-update"
```

### 3.4 ERS Fertilizer Prices — Quarterly Download

**File:** `etl/ingest_fertilizer.py`  
Runs quarterly. Add to existing Thursday ETL with a quarter-start check.

```python
FERTILIZER_URL = "https://www.ers.usda.gov/webdocs/DataFiles/50048/fertilizerprices.xlsx"

def ingest_fertilizer_prices():
    df = pd.read_excel(FERTILIZER_URL, sheet_name="Anhydrous ammonia")
    # ERS format: calendar year + quarter columns
    # Extract: anhydrous ammonia, DAP, potash — most recent 8 quarters
    rows = parse_fertilizer_excel(df)
    upsert_fertilizer_prices(rows)

# Run check in existing run_pipeline.sh:
# if [ $(date +%m) in ("01","04","07","10") ]; then python etl/ingest_fertilizer.py; fi
```

---

## 4. Feature Engineering

**File:** `features/acreage_features.py`

### 4.1 Annual Feature Matrix

Features are computed as of **November 1 of the prior year** — the natural decision-time snapshot for a February forecast. All features must be available by November 1 to avoid lookahead.

```python
def build_acreage_features(state_fips: str, commodity: str, forecast_year: int) -> pd.Series:
    """
    Features as of November 1 of (forecast_year - 1).
    forecast_year: the year being planted (e.g., 2026)
    decision_date: November 1, 2025 (prior year)
    """
    decision_date = date(forecast_year - 1, 11, 1)
    
    features = {}
    
    # Core economic signal: price ratios
    features["corn_soy_ratio"]          = get_november_price_ratio(forecast_year)
    features["corn_futures_dec"]        = query_futures("corn", decision_date, contract=f"{forecast_year-1}-12").settlement
    features["soy_futures_nov"]         = query_futures("soybean", decision_date, contract=f"{forecast_year-1}-11").settlement
    features["wheat_futures_jul"]       = query_futures("wheat", decision_date, contract=f"{forecast_year}-07").settlement
    
    # Cost structure
    cost_year = forecast_year - 1  # ERS lags by ~1 year
    features["variable_cost_bu"]        = get_ers_cost(commodity, cost_year, "variable_cost_per_bu")
    features["profit_margin_bu"]        = features.get(f"{commodity}_futures_dec", 0) - features["variable_cost_bu"]
    features["anhydrous_price_ton"]     = get_fertilizer_price(decision_date, "anhydrous_ammonia")
    
    # Relative crop profitability (corn vs. soy — primary driver of acre allocation)
    if commodity in ["corn", "soybean"]:
        corn_margin = query_futures("corn", decision_date, contract=f"{forecast_year-1}-12").settlement - get_ers_cost("corn", cost_year, "variable_cost_per_bu")
        soy_margin  = query_futures("soybean", decision_date, contract=f"{forecast_year-1}-11").settlement - get_ers_cost("soybean", cost_year, "variable_cost_per_bu")
        features["relative_profitability"] = corn_margin - soy_margin  # positive = corn favored
    
    # Prior year realized outcomes
    features["prior_year_acres"]        = get_nass_acreage(state_fips, commodity, forecast_year - 1)
    features["prior_year_yield"]        = get_nass_yield(state_fips, commodity, forecast_year - 1)
    features["prior_5yr_avg_acres"]     = get_nass_acreage_avg(state_fips, commodity, forecast_year, n=5)
    
    # Yield trend (captures genetic improvement + practice improvement)
    features["yield_trend_5yr"]         = compute_yield_trend(state_fips, commodity, forecast_year, n=5)
    
    # Crop rotation index (state-level: fraction corn-on-corn vs. corn-after-soy)
    features["rotation_ratio"]          = compute_rotation_ratio(state_fips, forecast_year - 1)
    
    # Structural / policy
    features["forecast_year"]           = forecast_year  # captures secular trend
    features["state_fips_code"]         = int(state_fips)  # ordinal encoding by cluster
    
    return pd.Series(features)
```

### 4.2 Crop Competition Constraint

Total cropland is approximately conserved at the state level short-term. Implement as a post-processing step, not a hard constraint on the model:

```python
def apply_competition_constraint(state_forecasts: dict, tolerance_pct: float = 0.03) -> dict:
    """
    Soft constraint: total forecast acres across corn + soy + wheat should not
    deviate more than tolerance_pct from prior year's total cropland.
    Scale all three proportionally if violated.
    
    state_forecasts: {'corn': X, 'soybean': Y, 'wheat': Z}
    """
    prior_total = sum(get_nass_acreage("00", c, forecast_year - 1) for c in ["corn", "soybean", "wheat"])
    forecast_total = sum(state_forecasts.values())
    
    if abs(forecast_total - prior_total) / prior_total > tolerance_pct:
        scale = prior_total / forecast_total
        return {k: v * scale for k, v in state_forecasts.items()}
    return state_forecasts
```

---

## 5. Model Architecture

### 5.1 Model Strategy: Ridge Regression + LightGBM Ensemble

Annual state-panel data (~50 states × 3 crops × 45 years = ~6,750 rows). Two-model ensemble:

- **Ridge Regression** — captures the strong linear relationship between price ratio and acreage share; interpretable
- **LightGBM** — captures nonlinear interactions (e.g., high fertilizer cost × marginal price ratio = stronger corn-to-soy shift)

Meta-learner: simple average (unweighted) — sufficient at this sample size.

**File:** `models/acreage_model.py`

```python
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import lightgbm as lgb
import numpy as np

class AcreageEnsemble:
    def __init__(self, commodity: str):
        self.commodity = commodity
        
        self.ridge = Pipeline([
            ("scaler", StandardScaler()),
            ("model",  Ridge(alpha=10.0))
        ])
        
        self.lgbm = lgb.LGBMRegressor(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            min_child_samples=10,  # small dataset — prevent overfitting
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.5,
            reg_lambda=1.0,
        )
        
        self.q_low  = lgb.LGBMRegressor(objective="quantile", alpha=0.10,
                                         n_estimators=300, max_depth=3, min_child_samples=10)
        self.q_high = lgb.LGBMRegressor(objective="quantile", alpha=0.90,
                                         n_estimators=300, max_depth=3, min_child_samples=10)
    
    def fit(self, X: pd.DataFrame, y: pd.Series):
        self.ridge.fit(X, y)
        self.lgbm.fit(X, y)
        self.q_low.fit(X, y)
        self.q_high.fit(X, y)
    
    def predict(self, X: pd.DataFrame) -> dict:
        ridge_pred = self.ridge.predict(X)
        lgbm_pred  = self.lgbm.predict(X)
        p50 = (ridge_pred + lgbm_pred) / 2  # simple average ensemble
        p10 = self.q_low.predict(X)
        p90 = self.q_high.predict(X)
        # Enforce: p10 ≤ p50 ≤ p90
        p10 = np.minimum(p10, p50)
        p90 = np.maximum(p90, p50)
        return {"p10": p10[0], "p50": p50[0], "p90": p90[0]}
    
    def get_key_driver(self, X_row: pd.Series) -> str:
        """Top LightGBM feature importance for this prediction."""
        importances = dict(zip(X_row.index, self.lgbm.feature_importances_))
        top = max(importances, key=importances.get)
        label_map = {
            "corn_soy_ratio":        "Corn-to-soybean price ratio",
            "relative_profitability":"Relative crop profit margin",
            "anhydrous_price_ton":   "Nitrogen fertilizer cost",
            "prior_year_acres":      "Prior year planted acreage",
            "profit_margin_bu":      "Per-bushel profit margin",
            "yield_trend_5yr":       "5-year yield improvement trend",
        }
        return label_map.get(top, top.replace("_", " ").title())
```

### 5.2 Training Configuration

```python
# One AcreageEnsemble per commodity = 3 total model objects
# Trained annually in January

TRAIN_YEARS = range(1980, 2021)  # 41 seasons
VAL_YEARS   = range(2021, 2024)  # 3 seasons — tune regularization here
TEST_YEARS  = [2024, 2025]       # held-out accuracy reporting

# Leave-one-year-out validation
for test_year in range(2010, 2025):
    train_idx = df["year"] < test_year
    val_idx   = df["year"] == test_year
    model.fit(X[train_idx], y[train_idx])
    oof_preds[val_idx] = model.predict(X[val_idx])

# Accuracy metric: MAPE at state and national level
# Target: ≤ 10% MAPE at state level, ≤ 5% at national level
```

### 5.3 National Rollup

```python
def compute_national_forecast(state_forecasts: pd.DataFrame) -> dict:
    """
    Sum state predictions to national total.
    National uncertainty is narrower than state-level (partial error cancellation).
    """
    national_p50 = state_forecasts["p50"].sum()
    
    # Propagate uncertainty: national variance = sum of variances + 2×covariance terms
    # Simplified assumption: state errors are 50% correlated (shared weather/price shocks)
    state_variances = ((state_forecasts["p90"] - state_forecasts["p10"]) / (2 * 1.645))**2
    corr_matrix = 0.5 * (1 - np.eye(len(state_forecasts))) + np.eye(len(state_forecasts))
    national_variance = state_variances @ corr_matrix @ state_variances
    national_sigma = np.sqrt(national_variance)
    
    return {
        "p50": national_p50,
        "p10": national_p50 - 1.645 * national_sigma,
        "p90": national_p50 + 1.645 * national_sigma,
    }
```

### 5.4 Model Artifact Storage

```
s3://ag-dashboard/models/acreage/
├── corn_ensemble.pkl
├── soybean_ensemble.pkl
├── wheat_ensemble.pkl
└── metadata.json          ← training date, LOO-CV MAPE by state, feature importances
```

---

## 6. API Specification

**File:** `routers/acreage.py`  
Register in `main.py`: `app.include_router(acreage_router, prefix="/api/v1/predict/acreage")`

---

**`GET /api/v1/predict/acreage`**

```python
@router.get("/")
async def get_acreage_forecast(
    commodity: str = Query(..., regex="^(corn|soybean|wheat)$"),
    year: int = Query(default=None),        # defaults to current forecast year
    level: str = Query(default="national", regex="^(national|state)$"),
    state_fips: Optional[str] = Query(default=None),  # required if level=state
    db: AsyncSession = Depends(get_db)
) -> AcreageForecastResponse:
```

Response (national):
```json
{
  "commodity": "corn",
  "forecast_year": 2026,
  "level": "national",
  "forecast_acres_millions": 91.2,
  "p10_acres_millions": 87.1,
  "p90_acres_millions": 95.3,
  "corn_soy_ratio": 2.28,
  "corn_soy_ratio_pctile": 38,
  "key_driver": "Corn-to-soybean price ratio",
  "vs_prior_year_pct": -2.1,
  "published_at": "2026-02-01",
  "model_ver": "2026-01-15"
}
```

Response (state-level, when `level=state&state_fips=19`):
```json
{
  "commodity": "corn",
  "forecast_year": 2026,
  "level": "state",
  "state_fips": "19",
  "state_name": "Iowa",
  "forecast_acres_millions": 12.8,
  "p10_acres_millions": 12.1,
  "p90_acres_millions": 13.5,
  "key_driver": "Relative crop profit margin",
  "vs_prior_year_pct": -1.8
}
```

---

**`GET /api/v1/predict/acreage/states`**

Returns all state-level forecasts for a given commodity × year — used to populate the state bar chart.

```json
{
  "commodity": "corn",
  "forecast_year": 2026,
  "states": [
    {"state_fips": "17", "state": "Illinois", "forecast_acres_millions": 11.2, "vs_prior_pct": -0.9},
    {"state_fips": "19", "state": "Iowa",     "forecast_acres_millions": 12.8, "vs_prior_pct": -1.8},
    ...
  ]
}
```

---

**`GET /api/v1/predict/acreage/accuracy`**

Returns historical model accuracy (populated after March 31 USDA release).

```json
[
  {
    "forecast_year": 2025,
    "commodity": "corn",
    "level": "national",
    "model_forecast": 90.4,
    "usda_prospective": 90.7,
    "usda_june_actual": 90.0,
    "model_vs_usda_pct": -0.3,
    "model_vs_actual_pct": 0.4
  }
]
```

---

**`GET /api/v1/predict/acreage/price-ratio`**

Returns the current corn/soy ratio with historical percentile context — primary driver visualization.

```json
{
  "as_of_date": "2025-11-01",
  "corn_dec_futures": 4.42,
  "soy_nov_futures": 9.81,
  "corn_soy_ratio": 2.31,
  "historical_percentile": 41,
  "historical_context": "A ratio of 2.31 is near the neutral zone. Ratios below 2.2 have historically shifted 2–4M acres to soybeans.",
  "implication": "neutral"
}
```

---

## 7. Frontend Integration

### 7.1 New Components

```
components/predictions/
├── AcreageSummaryCard.jsx      ← National forecast headline (one per commodity)
├── StateAcreageChart.jsx       ← Horizontal bar chart — top 12 states vs. prior year
├── PriceRatioDial.jsx          ← Corn/soy ratio gauge with historical percentile
├── UsdaComparisonPanel.jsx     ← Post-March 31: model vs. USDA side-by-side
└── AcreageForecastBanner.jsx   ← Pre-season banner (Feb 1 → Mar 31)
```

### 7.2 AcreageSummaryCard.jsx — Spec

```jsx
// Displays: forecast year, national acres (millions), p10/p90 band, vs. prior year %
// Color coding: green if acres up vs. prior, red if down (inverted from yield — more acres = more supply)
// Key driver label below the number
// Shows "Forecast window" badge: "Feb 1 – Mar 31" during pre-USDA period
// After April 1: switches to accuracy comparison mode automatically based on API response
```

### 7.3 StateAcreageChart.jsx — Spec

```jsx
import { BarChart, Bar, Cell, XAxis, YAxis, Tooltip, ReferenceLine } from 'recharts';

// Data: GET /predict/acreage/states for top 12 producing states
// X axis: forecast acres (millions)
// Each bar labeled with state name + vs_prior_pct annotation
// Color: green if positive vs_prior_pct, red if negative
// Reference line at "prior year" with dashed stroke
```

### 7.4 PriceRatioDial.jsx — Spec

```jsx
// Semi-circular gauge showing current corn/soy ratio
// Scale: 1.8 (strong soy) → 2.0 → 2.2 → 2.4 → 2.6 → 2.8 (strong corn)
// Colored zones: red zone < 2.2 ("soy favored"), green zone > 2.5 ("corn favored"), gray neutral
// Historical percentile shown as text: "41st percentile since 1990"
// Below gauge: "implication" text from API
// Source footnote: "Based on December corn / November soybean CME futures as of Nov 1"
```

### 7.5 UsdaComparisonPanel.jsx — Spec

Rendered only after `published_at` for USDA Prospective Plantings (April 1) is available in DB.

```jsx
// Condition: show only when acreage_accuracy table has a row for current year
// Layout: three columns — "Our Feb Forecast" | "USDA Mar 31" | "Difference"
// Populated automatically via GET /predict/acreage/accuracy
// Expandable table for state-by-state breakdown
// Headline: "We were {X}% from the USDA print on national corn acreage"
```

### 7.6 Seasonal UI State Machine

The acreage prediction UI has four distinct states — implement as a single `AcreagePredictionSection` component that renders differently based on date:

```
Pre-forecast (Oct 1 – Jan 31):    Show "Coming February 1" teaser + prior year actuals
Forecast live (Feb 1 – Mar 30):   Show AcreageSummaryCard + StateAcreageChart + PriceRatioDial
Post-USDA (Apr 1 – Jun 30):       Add UsdaComparisonPanel (model vs. USDA); keep forecast card
Final accuracy (Jul 1+):          Switch to full accuracy retrospective (model vs. June actuals)
```

---

## 8. Automation & Scheduling

### 8.1 Annual Cron Schedule

```bash
# Add to EventBridge — 4 annual triggers

# Jan 15: ERS cost data update + model retrain
cron(0 12 15 1 ? *)
→ python etl/ingest_ers_costs.py --year $(date +%Y - 1)
→ python models/acreage_model.py --train --year $(date +%Y)

# Feb 1: Publish forecast
cron(0 12 1 2 ? *)
→ python models/acreage_model.py --run-inference --publish-date $(date +%Y)-02-01

# Apr 1: Ingest USDA Prospective Plantings + compute accuracy
cron(0 16 1 4 ? *)
→ python etl/ingest_usda_prospective.py
→ python models/acreage_model.py --compute-accuracy --report-type prospective

# Jul 1: Ingest USDA June Area Survey (final ground truth)
cron(0 16 1 7 ? *)
→ python etl/ingest_usda_june_survey.py
→ python models/acreage_model.py --compute-accuracy --report-type june_actual
```

### 8.2 USDA Prospective Plantings Ingest

**File:** `etl/ingest_usda_prospective.py`

```python
# USDA releases Prospective Plantings as a PDF + Excel on March 31
# Use NASS QuickStats API — available ~April 1 as a structured query
def fetch_prospective_plantings(year: int) -> pd.DataFrame:
    params = {
        "key": NASS_API_KEY,
        "statisticcat_desc": "AREA PLANTED",
        "year": str(year),
        "source_desc": "SURVEY",
        "agg_level_desc": "NATIONAL",
        "format": "JSON",
    }
    # Returns USDA's official March 31 planted acreage estimates
    # Insert to acreage_accuracy.usda_prospective
```

### 8.3 Quarterly Fertilizer Price Update

Add to existing `run_pipeline.sh` — runs on first Thursday of January, April, July, October:

```bash
MONTH=$(date +%m)
if [[ "$MONTH" == "01" || "$MONTH" == "04" || "$MONTH" == "07" || "$MONTH" == "10" ]]; then
    DAY=$(date +%d)
    if [[ "$DAY" -le "07" ]]; then  # first week of quarter-start month
        python etl/ingest_fertilizer.py
    fi
fi
```

---

## 9. Stack Enhancements for This Module

| Area | Recommendation | Priority | Notes |
|---|---|---|---|
| **Excel parsing** | Use `openpyxl` not `xlrd` for ERS Excel files (`.xlsx` format) | Required | xlrd dropped xlsx support in v2.0 |
| **Annual job monitoring** | Add CloudWatch custom metric for annual job success/failure — separate from weekly pipeline | High | Annual jobs are easy to forget; make them loud on failure |
| **UI seasonal state** | Manage acreage UI state via a server-side date check (not client-side) — prevents stale states after timezone issues | High | Client-side `new Date()` can serve wrong state near midnight Jan 31/Feb 1 |
| **USDA Prospective Plantings alert** | Add SNS notification when USDA Prospective Plantings data is ingested — auto-triggers UI switch | Medium | Good demo feature: the dashboard updates itself after the USDA print |
| **Historical data quality** | Pre-1985 NASS acreage data has inconsistent formatting — add a data quality flag per row | Medium | Avoid training artifacts from early data |
| **Accuracy page** | Dedicate a `/analytics/acreage-accuracy` page showing multi-year accuracy track record | Low (post-launch) | Strongest credibility builder over time |

---

## 10. Environment Variables

No new secrets required beyond what Module 02 adds. All needed variables:

```bash
# From Module 02 (already set)
NASDAQ_DL_API_KEY=
FRED_API_KEY=

# From existing pipeline (already set)
NASS_API_KEY=
DB_HOST=
DB_PORT=5432
DB_NAME=ag_dashboard
DB_USER=ag_app
DB_PASSWORD=
S3_BUCKET=ag-dashboard
AWS_REGION=us-east-1

# ERS download URLs are public — no auth needed (hardcode in etl scripts)
```

---

## 11. Testing Checklist

- [ ] `test_price_ratio_calculation` — assert corn/soy ratio matches manually computed value for Nov 1, 2023 (known data)
- [ ] `test_nass_acreage_backfill` — assert acreage rows exist for all 3 crops × 50 states × 1980–2024
- [ ] `test_feature_lookahead_guard` — assert feature builder raises if any source data is dated after `decision_date`
- [ ] `test_competition_constraint` — assert total forecast acres within 3% of prior year total after constraint is applied
- [ ] `test_ensemble_monotonicity` — assert p10 ≤ p50 ≤ p90 for all state × crop combinations
- [ ] `test_national_rollup` — assert national p50 = sum of state p50s (before uncertainty propagation)
- [ ] `test_accuracy_compute` — populate test row in `acreage_forecasts`; run accuracy script; assert `acreage_accuracy` row created correctly
- [ ] `test_usda_ingest` — assert Prospective Plantings data for 2024 corn matches USDA published figure (90.7M acres)
- [ ] `test_api_state_level` — assert state-level response includes `state_name` and `vs_prior_year_pct`
- [ ] `test_ui_state_machine` — assert correct component renders for each of the 4 date ranges

---

## 12. Implementation Order

Given the module's annual cadence and infrastructure leverage, implement in this order:

1. **DB migration** — create 4 new tables (`acreage_forecasts`, `acreage_accuracy`, `ers_production_costs`, `ers_fertilizer_prices`)
2. **NASS acreage backfill** — extend existing NASS ingest script; run historical pull to 1980
3. **ERS ingestion** — one-time download + load for costs and fertilizer (both are small static files)
4. **Feature engineering module** — `acreage_features.py`; validate with spot-check against known ratio values
5. **Model training** — `acreage_model.py`; run LOO-CV; validate against 2024 USDA actuals (90M corn acres)
6. **S3 artifact storage** — save 3 model objects; write metadata JSON
7. **FastAPI routes** — `routers/acreage.py`; all 4 endpoints
8. **Frontend components** — `AcreageSummaryCard`, `StateAcreageChart`, `PriceRatioDial`, `UsdaComparisonPanel`
9. **Seasonal UI state machine** — `AcreagePredictionSection` wrapper component
10. **EventBridge annual schedule** — 4 cron rules; test with dry-run flags
11. **USDA Prospective Plantings ingest** — `ingest_usda_prospective.py`; test against 2024 data
12. **Testing + accuracy retrospective** — full test suite; populate accuracy table for 2020–2025 as demo data

---

## 13. Glossary

| Term | Definition |
|---|---|
| Prospective Plantings | USDA's March 31 annual report of intended planted acreage — the market benchmark this module aims to precede |
| June Area Survey | USDA's final June planted acreage count — the ground truth used for accuracy measurement |
| Corn/Soy Ratio | December corn futures ÷ November soybean futures as of November 1 — primary economic driver of corn/soy acre allocation |
| Anhydrous Ammonia | High-nitrogen fertilizer (82-0-0) used primarily on corn — asymmetric cost vs. nitrogen-fixing soybeans |
| ARC/PLC | Agricultural Risk Coverage / Price Loss Coverage — federal farm support program that can shift planting incentives |
| LOO-CV | Leave-One-Out Cross-Validation — validation strategy that trains on all years except the target year |
| National Rollup | Sum of state-level forecasts to national total, with correlated uncertainty propagation |
| Rotation Ratio | Fraction of a state's corn acres planted after soybeans vs. corn-on-corn — captures agronomic constraint on rapid acreage swings |
