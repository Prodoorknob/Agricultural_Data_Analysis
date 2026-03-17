# Crop Yield Prediction — Technical Specification
**Project:** Agricultural Dashboard · Cloud Computing Class Module  
**Version:** 1.0 | **Date:** March 2026  
**Team Size:** 3 | **Cloud Platform:** AWS  
**Status:** Pre-implementation

---

## 1. Project Overview

This module adds in-season, county-level crop yield prediction to the existing agricultural dashboard. The system ingests weather, soil, and crop condition data from free government APIs, computes agronomic features, trains a gradient-boosted ensemble, and exposes predictions via a FastAPI endpoint consumed by the Next.js frontend.

The project is scoped as a cloud computing class deliverable, meaning every infrastructure component must be cloud-native, documented, and demonstrable. The pipeline runs end-to-end on AWS.

### 1.1 Scope

- **Crops:** Corn, Soybeans, Wheat  
- **Spatial granularity:** County (FIPS code)  
- **Temporal granularity:** Weekly in-season updates (May–October)  
- **Forecast output:** p10 / p50 / p90 bushels-per-acre with confidence tier  
- **Accuracy target:** ≤ 12% RRMSE on corn in Corn Belt counties by week 20+  
- **Out of scope:** Sub-county resolution, international crops, real-time streaming

### 1.2 System Context

```
[External APIs] → [AWS S3 Raw Lake] → [EC2 ETL + Feature Engine] → [RDS PostgreSQL]
                                                ↓
                                    [EC2 Model Training Job]
                                                ↓
                                    [RDS: yield_forecasts table]
                                                ↓
                                    [FastAPI on EC2] → [Next.js Frontend]
```

---

## 2. Architecture

### 2.1 AWS Services Used

| Service | Role | Tier / Cost |
|---|---|---|
| **EC2** (t3.medium) | ETL runner, model training job, FastAPI host | ~$30/mo; stop when not running |
| **S3** | Raw data lake — immutable weekly snapshots per source | Free tier + ~$0.023/GB |
| **RDS PostgreSQL** (db.t3.micro) | Feature store + forecast store | ~$15/mo |
| **EventBridge** (CloudWatch Events) | Weekly cron trigger for ETL + training | Free tier |
| **IAM** | Least-privilege roles per service | Free |
| **CloudWatch Logs** | Pipeline run logs, error alerts | Free tier |
| **SNS** (optional) | Email alert on pipeline failure | Free tier |

> **Class note:** This is a teachable, cost-controlled stack. Total AWS cost is under $50/month if EC2 is stopped when not actively running. All services have free tiers sufficient for development.

### 2.2 Data Flow — Detailed

```
THURSDAY PIPELINE (triggered 6:00 AM ET via EventBridge)

Step 1: ETL Job (EC2)
  ├── Pull NASS crop condition ratings (weekly, Tuesday release → available Thursday)
  ├── Pull NOAA GHCN daily temps/precip (7-day lag, backfill missing stations)
  ├── Pull NASA POWER solar radiation + VPD (2-day lag, gridded — no gaps)
  ├── Pull US Drought Monitor USDM API (Thursday release, county-level)
  └── Write raw JSON/CSV to S3: s3://ag-dashboard/raw/{source}/{YYYY-WW}/

Step 2: Feature Engine (EC2)
  ├── Load raw files from S3
  ├── Join on FIPS + crop_year + week_of_season
  ├── Static join: SSURGO soil features (pre-loaded to RDS, join by FIPS)
  ├── Compute derived features (GDD, CCI, precip deficit, VPD stress days)
  └── Write feature matrix to RDS: feature_weekly table

Step 3: Model Inference (EC2)
  ├── Load trained model artifacts from S3: s3://ag-dashboard/models/
  ├── Run inference on current week's feature matrix
  ├── Compute p10/p50/p90 via quantile models
  └── Write to RDS: yield_forecasts table (immutable INSERT, no overwrites)

Step 4: Health Check
  └── Assert row count > 2000 (sanity), log to CloudWatch, SNS alert on failure
```

### 2.3 Storage Schema

```sql
-- Raw feature store (weekly snapshot)
CREATE TABLE feature_weekly (
    fips        CHAR(5)       NOT NULL,
    crop        VARCHAR(10)   NOT NULL,  -- 'corn' | 'soybean' | 'wheat'
    crop_year   SMALLINT      NOT NULL,
    week        SMALLINT      NOT NULL,  -- 1–30 (week of growing season)
    gdd_ytd     FLOAT,                   -- Growing Degree Days accumulated
    cci_cumul   FLOAT,                   -- Crop Condition Index cumulative
    precip_deficit FLOAT,                -- mm vs. 30-yr normal
    vpd_stress_days SMALLINT,            -- days VPD > 2.0 kPa
    drought_d3d4_pct FLOAT,             -- % county in D3/D4 drought
    soil_awc    FLOAT,                   -- plant-available water capacity (SSURGO)
    soil_drain  SMALLINT,               -- drainage class code (SSURGO)
    ingest_ts   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (fips, crop, crop_year, week)
);

-- Forecast output (immutable)
CREATE TABLE yield_forecasts (
    id          BIGSERIAL PRIMARY KEY,
    fips        CHAR(5)       NOT NULL,
    crop        VARCHAR(10)   NOT NULL,
    crop_year   SMALLINT      NOT NULL,
    week        SMALLINT      NOT NULL,
    p10         FLOAT         NOT NULL,  -- bu/acre
    p50         FLOAT         NOT NULL,
    p90         FLOAT         NOT NULL,
    confidence  VARCHAR(10)   NOT NULL,  -- 'low' | 'medium' | 'high'
    model_ver   VARCHAR(20)   NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (fips, crop, crop_year, week, model_ver)  -- no silent overwrites
);

-- SSURGO static soil features (one-time load)
CREATE TABLE soil_features (
    fips        CHAR(5) PRIMARY KEY,
    awc_cm      FLOAT,   -- plant-available water capacity (cm/cm)
    drain_class SMALLINT -- USDA drainage class 1–8
);
```

---

## 3. Data Sources

### 3.1 Source Registry

| Source | Endpoint | Auth | Pull Frequency | New Setup? |
|---|---|---|---|---|
| USDA NASS QuickStats | `quickstats.nass.usda.gov/api/api_GET` | API key (free) | Weekly | Already in pipeline |
| NOAA GHCN-Daily | `api.ncdc.noaa.gov/v2/data` | Token (free) | Weekly | **Add** |
| NASA POWER | `power.larc.nasa.gov/api/temporal/daily/point` | None | Weekly | **Add** |
| US Drought Monitor | `usdmdataservices.unl.edu/api/5.0/Services` | None | Weekly | **Add** |
| SSURGO (NRCS) | Web Soil Survey bulk download | None | One-time | **Add (static)** |

### 3.2 NOAA Station-to-County Mapping

NOAA data is station-level, not county-level. The mapping strategy:

1. Download NOAA station inventory (`ghcnd-stations.txt`)
2. For each county FIPS, identify all stations within 50 km using Haversine distance
3. Use the nearest station with ≥ 90% completeness for the target date range
4. Fallback: if no station meets threshold → use NASA POWER gridded data (always complete)

```python
# pseudocode — station selection
def select_station(fips, date_range):
    candidates = stations_within_km(fips_centroid(fips), km=50)
    ranked = sorted(candidates, key=lambda s: (completeness(s, date_range), -distance(s, fips)))
    return ranked[0] if ranked[0].completeness >= 0.90 else None  # fall back to NASA POWER
```

### 3.3 SSURGO One-Time Load

```bash
# Download SSURGO national snapshot
wget https://websoilsurvey.sc.egov.usda.gov/DSD/Download/AOI/...
# Parse mapunit → component → chorizon tables for AWC and drainage class
# Aggregate to county FIPS via muaggatt table
# Load to RDS soil_features table
python scripts/load_ssurgo.py --input ssurgo_national.zip --output rds
```

---

## 4. Feature Engineering

### 4.1 Feature Definitions

| Feature | Formula | Data Source | Why It Matters |
|---|---|---|---|
| `gdd_ytd` | Σ max(0, (Tmax+Tmin)/2 − 50°F) from planting date | NOAA | Primary heat accumulation signal; #1 in-season predictor |
| `cci_cumul` | Σ NASS weekly rating (G/E=+2, F=0, P/VP=−2) | NASS | Leading indicator of crop stress visible before yield damage |
| `precip_deficit` | Cumulative actual precip − 30yr normal precip | NOAA + PRISM normals | Drought stress accumulation |
| `vpd_stress_days` | Days with VPD > 2.0 kPa in current season | NASA POWER | Heat + humidity stress, strongest soybean signal |
| `drought_d3d4_pct` | % of county in D3 or D4 drought category | USDM | Severe drought flag; nonlinear effect on yield |
| `soil_awc` | Plant-available water capacity (cm/cm) | SSURGO | Buffers precip deficit in high-AWC soils |
| `soil_drain` | USDA drainage class 1–8 | SSURGO | Wet years hurt poorly-drained counties less |

### 4.2 Week-of-Season Indexing

All features are indexed as **week W of the growing season**, not calendar week. This makes models trained on historical data directly comparable across years despite planting date variation.

```python
# planting_date varies by state and year (from NASS planting progress)
week_of_season = (observation_date - planting_date).days // 7 + 1
```

### 4.3 Temporal Integrity Rule

**No feature may use information unavailable at forecast time.** Feature construction is run with a strict `as_of_date` parameter:

```python
def build_features(fips, crop, crop_year, as_of_week, as_of_date):
    # Only pull data where release_date <= as_of_date
    # Enforced at query level — no silent lookahead leakage
```

---

## 5. Model Architecture

### 5.1 Model Strategy: Per-Crop × Per-Week

Train one model per (crop, week_of_season) combination. A "week 12 corn model" uses only signals available through week 12. A "week 24 corn model" has the fuller picture.

- 3 crops × 20 weekly snapshots = **60 models**  
- Each model is a LightGBM quantile regressor (lightweight, fast to train)
- Training time: ~8 min total on t3.medium

### 5.2 Training Configuration

```python
import lightgbm as lgb

params_median = {
    "objective": "quantile",
    "alpha": 0.50,          # median
    "n_estimators": 500,
    "max_depth": 5,
    "learning_rate": 0.04,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
}
# Also train alpha=0.10 (p10) and alpha=0.90 (p90) variants
```

### 5.3 Validation Strategy: Walk-Forward

```
Train:    2000–2019 (20 seasons)
Validate: 2020–2022 (3 seasons — tune hyperparams here)
Test:     2023–2024 (2 seasons — reported accuracy, not tuned on)
```

**Never** use TimeSeriesSplit that allows future data in training fold. Use leave-future-years-out:

```python
for test_year in [2020, 2021, 2022, 2023, 2024]:
    train_years = range(2000, test_year)
    val_years   = [test_year]
    # Fit on train_years, evaluate on val_years
```

### 5.4 Baseline Comparison (Required)

Before claiming ML value, compare against:
1. **County historical mean** — 10-year average yield for that county × crop
2. **State mean** — same, at state level
3. **Prior year actual** — last year's realized yield

If LightGBM p50 RRMSE is not at least 10% better than county historical mean on the test set, report this honestly — don't ship a model that doesn't beat a simple average.

### 5.5 Model Artifact Storage

```
s3://ag-dashboard/models/
├── corn/
│   ├── week_10_p10.pkl
│   ├── week_10_p50.pkl
│   ├── week_10_p90.pkl
│   ├── week_11_p10.pkl  ...
│   └── metadata.json       ← training date, RRMSE by week, feature importances
├── soybean/ ...
└── wheat/ ...
```

---

## 6. API Specification

### 6.1 Endpoints

All endpoints served from FastAPI on EC2. Base path: `/api/v1/predict/yield`

---

**`GET /api/v1/predict/yield`**

Returns the latest forecast for a county × crop.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `fips` | string | yes | 5-digit FIPS county code |
| `crop` | string | yes | `corn` \| `soybean` \| `wheat` |
| `year` | integer | no | Defaults to current crop year |

Response:
```json
{
  "fips": "19153",
  "crop": "corn",
  "crop_year": 2026,
  "week": 18,
  "p10": 178.4,
  "p50": 191.2,
  "p90": 203.7,
  "unit": "bu/acre",
  "confidence": "medium",
  "county_avg_5yr": 194.1,
  "vs_avg_pct": -1.5,
  "model_ver": "2026-05-01",
  "last_updated": "2026-05-22T06:45:00Z"
}
```

---

**`GET /api/v1/predict/yield/map`**

Returns all county forecasts for a given crop + week (for choropleth rendering).

| Parameter | Type | Required |
|---|---|---|
| `crop` | string | yes |
| `week` | integer | no — defaults to current |
| `year` | integer | no — defaults to current |

Response: array of `{fips, p50, confidence, vs_avg_pct}` — lightweight for map use.

---

**`GET /api/v1/predict/yield/history`**

Returns historical forecast vs. actual for accuracy retrospective.

| Parameter | Type | Description |
|---|---|---|
| `fips` | string | County |
| `crop` | string | Crop |
| `start_year` | integer | First year to include |

Response: array of `{crop_year, week, p50_forecast, actual_yield, error_pct}` ordered by year → week.

---

### 6.2 Confidence Tier Logic

```python
def confidence_tier(week_of_season: int) -> str:
    if week_of_season < 8:   return "low"     # pre-pollination
    if week_of_season < 16:  return "medium"  # vegetative growth
    return "high"                              # grain fill + dough stages
```

---

## 7. Frontend Integration

### 7.1 New UI Components

| Component | Location | Description |
|---|---|---|
| `YieldForecastLayer` | Map page | Choropleth overlay toggle — color by `vs_avg_pct` (z-score vs. county 5yr avg) |
| `YieldForecastCard` | County detail panel | p10/p50/p90 display + confidence label + USDA comparison |
| `ConfidenceStrip` | County detail panel | Horizontal timeline showing how forecast bands narrow week-by-week |
| `SeasonAccuracy` | Analytics page | Line chart: historical forecast p50 vs. realized yield, by season |

### 7.2 Color Scale (Choropleth)

```
vs_avg_pct < -10%  → deep red    #b03030
-10% to -5%        → light red   #e08080
-5% to +5%         → neutral     #e8e8e8
+5% to +10%        → light green #80c080
> +10%             → deep green  #2a7a4b
```

### 7.3 Confidence UI Rule

**Always display confidence tier in the UI alongside any forecast number.** When `confidence = "low"`, show a visible warning banner: *"Early-season estimate — wide uncertainty. Forecast improves through July."* This is non-negotiable; the model is least reliable when users are most tempted to act on early numbers.

---

## 8. Infrastructure Setup (AWS)

### 8.1 EC2 Configuration

```bash
# Instance type: t3.medium (2 vCPU, 4GB RAM) — sufficient for training 60 models
# AMI: Ubuntu 22.04 LTS

# Python environment
python3 -m venv /opt/ag-venv
source /opt/ag-venv/bin/activate
pip install lightgbm pandas numpy scikit-learn sqlalchemy psycopg2-binary boto3 fastapi uvicorn requests

# Directory structure
/opt/ag-pipeline/
├── etl/
│   ├── ingest_nass.py
│   ├── ingest_noaa.py
│   ├── ingest_nasa_power.py
│   ├── ingest_drought_monitor.py
│   └── load_ssurgo.py
├── features/
│   └── build_features.py
├── models/
│   ├── train.py
│   └── inference.py
├── api/
│   └── main.py
└── run_pipeline.sh      ← master script called by EventBridge
```

### 8.2 IAM Role for EC2

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::ag-dashboard/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["sns:Publish"],
      "Resource": "arn:aws:sns:us-east-1:*:ag-pipeline-alerts"
    }
  ]
}
```

### 8.3 EventBridge Weekly Trigger

```json
{
  "ScheduleExpression": "cron(0 10 ? * 5 *)",
  "Description": "Trigger crop yield pipeline every Thursday at 10:00 UTC",
  "Targets": [{
    "Id": "ag-yield-pipeline",
    "Arn": "arn:aws:ec2:...",
    "Input": "{\"action\": \"run_pipeline\"}"
  }]
}
```

> **Note:** EventBridge triggers an SSM Run Command on the EC2 instance to execute `run_pipeline.sh`. EC2 does not need to stay running 24/7 — use EC2 Instance Scheduler or simply start/stop manually around Thursday runs for cost control.

### 8.4 S3 Bucket Structure

```
s3://ag-dashboard/
├── raw/
│   ├── nass/{YYYY-WW}/crop_conditions.json
│   ├── noaa/{YYYY-WW}/daily_obs.csv
│   ├── nasa_power/{YYYY-WW}/solar_vpd.csv
│   └── drought_monitor/{YYYY-WW}/usdm_county.csv
├── models/
│   ├── corn/week_{N}_{quantile}.pkl
│   ├── soybean/...
│   ├── wheat/...
│   └── metadata.json
└── processed/
    └── feature_matrix/{YYYY-WW}/features.parquet
```

---

## 9. Testing Requirements

### 9.1 Unit Tests

- `test_gdd_calculation` — verify GDD accumulation against USDA published example county
- `test_cci_scoring` — verify rating-to-score mapping matches NASS definitions
- `test_no_lookahead` — assert feature builder raises `AssertionError` if any source data postdates `as_of_date`
- `test_model_monotonicity` — assert p10 < p50 < p90 for every forecast row

### 9.2 Integration Tests

- `test_pipeline_end_to_end` — run on 2023 season, assert final RRMSE < 15% for Iowa corn
- `test_api_response_schema` — assert all API responses match Pydantic schema
- `test_s3_write_and_read` — assert raw ingest files appear in S3 after ETL step

### 9.3 Accuracy Benchmarks (Gate for Deployment)

| Crop | Region | Metric | Minimum Threshold |
|---|---|---|---|
| Corn | Corn Belt (IA, IL, IN, OH, MN) | RRMSE @ week 20 | ≤ 15% |
| Soybean | Corn Belt | RRMSE @ week 20 | ≤ 15% |
| Wheat | Winter wheat belt (KS, OK, TX) | RRMSE @ week 16 | ≤ 18% |

If thresholds are not met, the module ships with county-historical-mean as the displayed forecast, with ML predictions demoted to "experimental" status in the UI.

---

## 10. Environment Variables

```bash
# .env — never commit to git
NASS_API_KEY=
NOAA_TOKEN=
DB_HOST=<rds-endpoint>.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ag_dashboard
DB_USER=ag_app
DB_PASSWORD=
S3_BUCKET=ag-dashboard
AWS_REGION=us-east-1
PIPELINE_SNS_ARN=arn:aws:sns:us-east-1:...:ag-pipeline-alerts
```

---

## 11. Stack Recommendations & Enhancements

### 11.1 Recommended Additions vs. Existing Stack

| Component | Recommendation | Rationale |
|---|---|---|
| **Model serialization** | Use `joblib` not `pickle` for sklearn-compatible models; LightGBM native `.txt` for LGB models | Safer cross-version deserialization |
| **Feature store** | Add a `processed/feature_matrix/` S3 Parquet layer | Decouples ETL from training; teammates can re-train without re-pulling APIs |
| **Logging** | `structlog` → CloudWatch Logs | Structured JSON logs are searchable; critical for team debugging |
| **Schema validation** | `pydantic` on all API I/O + `pandera` on DataFrames | Catches data quality issues before they corrupt forecasts |
| **Database migrations** | `alembic` with version-controlled migration scripts | Essential once 3 people are touching the DB schema |
| **Secrets** | AWS Secrets Manager (not `.env` files on EC2) | Safer for multi-person team; rotate without code changes |
| **CI** | GitHub Actions — run unit tests on every PR | Prevents broken merges; beginner-friendly to set up |

### 11.2 What NOT to Add (for this scope)

- **Docker/Kubernetes** — overkill for a class project with 60 lightweight models; adds complexity without learning payoff
- **SageMaker** — too expensive for student budgets; EC2 training is sufficient at this scale
- **Airflow** — EventBridge + bash script is the right level of complexity for 3 people and weekly runs
- **Redis cache** — API response times are acceptable from RDS at this query volume

---

## 12. Glossary

| Term | Definition |
|---|---|
| GDD | Growing Degree Days — accumulated heat units from planting date, base 50°F for corn |
| CCI | Crop Condition Index — numeric score derived from NASS weekly 5-tier condition ratings |
| RRMSE | Relative Root Mean Squared Error — RMSE divided by the mean yield, expressed as % |
| FIPS | Federal Information Processing Standards — 5-digit county code used as spatial key |
| AWC | Available Water Capacity — soil's ability to retain plant-usable water (cm/cm) |
| SSURGO | Soil Survey Geographic Database — NRCS county-level soil property dataset |
| USDM | US Drought Monitor — weekly county-level drought severity classification |
| p10/p50/p90 | 10th, 50th, 90th percentile forecast — the uncertainty interval around the median prediction |
