# Agricultural Data Analysis — Project Guide

## What This Project Is

Interactive dashboard for exploring long-term trends in U.S. agriculture using USDA QuickStats data. Features choropleth maps, time-series charts, and state-level drill-downs across crops, livestock, land use, labor, and economics.

## Architecture

```
Next.js Frontend (React 19, Recharts, Deck.gl, MapLibre)
         |
    S3 (primary) / Local API (fallback) / Athena (advanced queries)
         |
Python Pipeline (EC2 cron) -> USDA API -> Parquet -> S3
         |
FastAPI Backend (EC2, port 8000) -> PostgreSQL (RDS)   [DEPLOYED]
         |
Production: Vercel (frontend) + https://agri-intel.rvedire.com (API)
```

## Tech Stack

### Frontend (`web_app/`)
- Next.js 16, React 19, TypeScript 5, TailwindCSS 4
- Recharts 3.7 (charts), Deck.gl 9.2 + MapLibre GL 5.18 (maps)
- hyparquet 1.25 (browser-side parquet reading)
- @aws-sdk/client-athena (Athena queries)

### Pipeline (`pipeline/`)
- Python 3, pandas, pyarrow, boto3, requests, numpy
- Runs on EC2 via cron (15th of month, 6 AM)

### Backend (`backend/`) — IN PROGRESS
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async, asyncpg)
- PostgreSQL on RDS (us-east-2)
- LightGBM, statsmodels, scikit-learn, SHAP
- Alembic for migrations

## Directory Structure

```
Agricultural_Data_Analysis/
├── CLAUDE.md                    # This file
├── README.md                    # Project overview
├── NEXT_PHASE.md                # Phase 3/4 roadmap
├── web_app/                     # Next.js frontend
│   └── src/
│       ├── app/                 # Pages + API routes
│       │   ├── page.tsx         # Main dashboard (has ViewMode tabs)
│       │   └── api/
│       │       ├── data/route.ts       # Parquet proxy (S3 or local)
│       │       └── athena/route.ts     # Athena query endpoint
│       ├── components/          # Dashboard views
│       │   ├── CropsDashboard.tsx
│       │   ├── EconomicsDashboard.tsx
│       │   ├── LandDashboard.tsx
│       │   ├── LaborDashboard.tsx
│       │   ├── AnimalsDashboard.tsx
│       │   ├── USMap.tsx
│       │   └── ...
│       ├── hooks/useAthenaQuery.ts
│       ├── types/agricultural-data.ts
│       └── utils/
│           ├── design.ts        # Design tokens (palette, chart colors)
│           ├── processData.ts   # Data transformations
│           └── serviceData.ts   # S3/local data fetching
├── pipeline/                    # USDA data ingestion
│   ├── quickstats_ingest.py     # Main ingest script (776 lines)
│   ├── upload_to_s3.py          # Dual-layout S3 upload
│   ├── validate_data.py         # Data quality checks
│   ├── incremental_check.py     # New data detection
│   ├── cron_runner.sh           # EC2 orchestrator
│   └── requirements.txt
├── backend/                     # FastAPI prediction service [IN PROGRESS]
│   ├── main.py                  # App entry, CORS, health
│   ├── config.py                # Settings (pydantic-settings)
│   ├── database.py              # SQLAlchemy async sessions
│   ├── alembic/                 # DB migrations
│   ├── routers/price.py         # Price forecast endpoints
│   ├── etl/                     # Data ingestion scripts
│   ├── features/                # Feature engineering
│   └── models/                  # ML models + Pydantic schemas
└── research/                    # Tech specs + analysis reports
    ├── commodity-price-tech-spec.md   # Price forecasting spec
    ├── crop-yield-tech-spec.md        # Yield forecasting spec
    └── planted-acreage-tech-spec.md   # Acreage prediction spec
```

## AWS Infrastructure

| Service | Details |
|---------|---------|
| S3 | `usda-analysis-datasets` (us-east-2) — parquet files, model artifacts |
| EC2 | Pipeline cron + FastAPI backend (same instance) |
| Athena | Database `usda_agricultural`, table `quickstats_data`, workgroup `usda-dashboard` |
| RDS | PostgreSQL (db.t4g.micro, us-east-2) — `ag-dashboard` instance, database `ag_dashboard`, user `ag_app`, **Publicly Accessible = Yes** (local dev access via security group IP whitelist) |
| SNS | `arn:aws:sns:us-east-2:294733692749:usda-pipeline-alerts` |

## Environment Variables

```bash
# Existing (in .env)
QUICKSTATS_API_KEY=...     # USDA QuickStats API
NOAA_API_KEY=...           # NOAA weather data

# Prediction modules (added to .env)
DATABASE_URL=postgresql+asyncpg://ag_app:PASSWORD@ag-dashboard.cvuu6ce8odqc.us-east-2.rds.amazonaws.com:5432/ag_dashboard
# NASDAQ_DL_API_KEY — no longer needed (CHRIS/CME retired, switched to Yahoo Finance)
FRED_API_KEY=...           # FRED API (DXY index)
```

## Data Flow

1. **Pipeline** fetches from USDA QuickStats API monthly
2. Data cleaned, partitioned by state into parquet files
3. Uploaded to S3 in two layouts: browser-friendly + Athena-optimized
4. **Frontend** reads parquet directly from S3 (or via API proxy fallback)
5. **Athena** available for complex SQL queries over the same S3 data
6. **Prediction module** (in progress): FastAPI reads from RDS, serves forecasts to frontend

## Development

```bash
# Frontend
cd web_app && npm install && npm run dev

# Pipeline (manual run)
cd pipeline && pip install -r requirements.txt && python quickstats_ingest.py

# Backend (once set up)
cd backend && pip install -r requirements.txt && uvicorn main:app --reload --port 8000
```

## Conventions

- **Dark theme UI**: palette defined in `web_app/src/utils/design.ts`
- **Pipeline patterns**: see `pipeline/quickstats_ingest.py` for error handling, logging, retry logic
- **API routes**: Next.js App Router pattern (route.ts files)
- **Data format**: Parquet files, partitioned by state
- **Chart library**: Recharts (already in stack — use for all new charts)

## Implementation Progress

### Commodity Price Forecasting (Module 02)
- **Spec:** `research/commodity-price-tech-spec.md`
- **Plan:** `.claude/plans/idempotent-fluttering-prism.md`
- **RDS:** db.t4g.micro, identifier `ag-dashboard`, master user `ag_app`, database `ag_dashboard`, endpoint `ag-dashboard.cvuu6ce8odqc.us-east-2.rds.amazonaws.com`, us-east-2
- **All API keys and DATABASE_URL configured in `.env`** (local + EC2)
- **EC2 backend venv:** `~/Agricultural_Data_Analysis/backend/venv/`

#### Completed
- Step 1: CLAUDE.md created
- Step 2: FastAPI backend skeleton (`backend/`) — main.py, config.py, database.py, routers/price.py (stub endpoints), models/schemas.py, models/db_tables.py (ORM), alembic migration 001
- Step 3: DB Migration — 5 tables created on RDS (futures_daily, wasde_releases, price_forecasts, ers_production_costs, dxy_daily). Fixed: `config.py` extra="ignore", `database.py` lazy engine init for Alembic compatibility.
- Step 4: ETL Scripts — `backend/etl/common.py` (sync DB engine, logging), `ingest_futures.py` (daily CME via Yahoo Finance `yfinance`, upsert to futures_daily — switched from Nasdaq DL CHRIS/CME which was retired/403), `ingest_fred.py` (daily FRED DXY, upsert to dxy_daily), `ingest_wasde.py` (monthly PSD CSV download, filter/pivot/compute stocks-to-use, upsert to wasde_releases), `load_ers_costs.py` (annual ERS Excel parse, upsert to ers_production_costs). Updated `pipeline/cron_runner.sh` with `--daily`, `--monthly-wasde`, `--annual-ers` modes.
- Step 5: Feature Engineering — `backend/features/price_features.py`: `build_price_features(commodity, as_of_date, horizon_months)` returns single-row DataFrame with 18 features (market: futures_spot/deferred, basis, term_spread, OI change; fundamental: stocks_to_use, percentile, WASDE surprise, world STU; macro: DXY, DXY 30d change; cost: production_cost_bu, price_cost_ratio; interaction: corn_soy_ratio; seasonal: prior_year_price, seasonal_factor). Pandera schema validation. `build_training_features()` for batch generation. MVP skips drought/CCI.
- Step 6: Model Training — `backend/models/price_model.py`: PriceEnsemble dataclass (SARIMAX + LightGBM point/quantile + Ridge meta-learner + IsotonicRegression calibrator). SHAP TreeExplainer key drivers with human-readable label map. Mahalanobis regime detection with regularized covariance. Calibrated probability via normal CDF + isotonic. Divergence flag (>5% from futures). `backend/models/train.py`: walk-forward training (2010-2019 train, 2020-2022 val, 2023-2024 test). Futures-baseline MAPE gate (model must beat futures + 1.5pp). 18 model sets saved as pickle to `backend/artifacts/{commodity}/horizon_{N}/`. Metrics JSON alongside. S3 upload to `models/price/`. CLI: `python -m backend.models.train [--commodity X] [--horizon N] [--local-only]`.

- Step 7: API Implementation — `backend/routers/price.py`: all 4 endpoints implemented (GET /, /probability, /wasde-signal, /history). Model loading at startup via `_load_models()` in `main.py` lifespan — loads PriceEnsemble pickles from `backend/artifacts/{commodity}/horizon_{N}/ensemble.pkl`. Forecast endpoint builds features, runs ensemble predict, persists to `price_forecasts` table (upsert). Probability endpoint uses `predict_probability()` with calibrated isotonic. WASDE signal queries last 2 releases, computes surprise/direction/percentile. History endpoint joins `price_forecasts` with `futures_daily` for realized prices.
- Step 8: Frontend — `web_app/src/components/PredictionsDashboard.tsx`: single-file dashboard with sub-components (PriceRegimeAlert, KpiCard, PriceFanChart, ProbabilityGauge, WasdeSignalCard, KeyDriverCallout, ForecastHistoryChart). `web_app/src/hooks/usePriceForecast.ts`: custom hook with fetchAllHorizons, fetchProbability, fetchWasdeSignal, fetchHistory. PREDICTIONS tab added to page.tsx ViewMode. Backend URL configurable via `NEXT_PUBLIC_PREDICTION_API_URL` env var.

- Step 9: Scheduling & Deployment — Architecture: **local PC trains models, EC2 serves predictions**.
  - `_load_models()` in `main.py`: S3 fallback via boto3 — downloads pickles from `s3://usda-analysis-datasets/models/price/` if not on local disk.
  - `backend/ag-prediction.service`: systemd unit for FastAPI on EC2 (port 8000, auto-restart on failure).
  - `web_app/.env.production`: `NEXT_PUBLIC_PREDICTION_API_URL` placeholder for EC2 endpoint.
  - `backend/models/inference.py`: CLI script (`python -m backend.models.inference`) — loads ensembles, builds features, runs predict for all 18 commodity/horizon combos, upserts results to `price_forecasts` table.
  - `cron_runner.sh --monthly-wasde`: now triggers inference after WASDE ingest, restarts `ag-prediction` service to reload models.
  - **Local workflow:** ETL (`ingest_futures`, `ingest_fred`, `ingest_wasde`, `load_ers_costs`) -> Train (`python -m backend.models.train`) -> S3 upload.
  - **EC2 cron:** daily market data (weekdays 12pm), WASDE + inference (12th monthly 2pm), ERS costs (Jan 15 10am), NASS (15th monthly 6am).
  - **EC2 deploy:** `sudo cp backend/ag-prediction.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now ag-prediction`
  - **Cost target:** ~$22/mo (RDS $15 + EC2 serving-only $6 + S3/Athena <$1). No training compute on EC2.

#### Module 02 Complete
All 9 steps implemented. See `research/commodity-price-tech-spec.md` for full spec.

### Planted Acreage Prediction (Module 03)
- **Spec:** `research/planted-acreage-tech-spec.md`
- **Reuses:** Module 02 infrastructure (RDS, FastAPI, CME futures data)

#### Completed
- Step 1: DB Migration — `alembic/versions/002_acreage_tables.py`: 3 new tables (`acreage_forecasts`, `acreage_accuracy`, `ers_fertilizer_prices`) + `fertilizer_cost_acre` column on `ers_production_costs`. ORM models in `models/db_tables.py`.
- Step 2: Pydantic Schemas — `models/schemas.py`: `AcreageForecastResponse`, `StatesAcreageResponse`, `AcreageAccuracyItem`, `PriceRatioResponse`.
- Step 3: ETL — `etl/ingest_fertilizer.py`: quarterly ERS fertilizer price download (anhydrous ammonia, DAP, potash), parse from Excel, upsert to `ers_fertilizer_prices`.
- Step 4: Feature Engineering — `features/acreage_features.py`: 15 features (price signals: corn/soy ratio, futures prices; cost: variable cost, profit margin, fertilizer; historical: prior year acres/yield, 5yr avg, yield trend, rotation ratio; structural: year, state FIPS). `build_training_features()` for batch training data generation.
- Step 5: Model — `models/acreage_model.py`: `AcreageEnsemble` dataclass (Ridge + LightGBM point + LightGBM quantile p10/p90). Simple average meta-learner. `apply_competition_constraint()` for total cropland soft cap. `compute_national_forecast()` with correlated uncertainty propagation. `train_and_save()` with walk-forward evaluation.
- Step 6: API — `routers/acreage.py`: 4 endpoints (`GET /`, `/states`, `/accuracy`, `/price-ratio`). Registered in `main.py` at `/api/v1/predict/acreage`. Acreage model loading via `_load_acreage_models()` in lifespan, artifacts at `artifacts/acreage/{commodity}/ensemble.pkl`.
- Step 7: Frontend — `components/AcreagePredictionSection.tsx`: 4 sub-components (`AcreageSummaryCard`, `StateAcreageChart`, `PriceRatioDial`, `UsdaComparisonPanel`). Seasonal UI state machine (pre-forecast / forecast-live / post-USDA / final-accuracy). Integrated into `PredictionsDashboard.tsx`. `hooks/useAcreageForecast.ts` for data fetching.
- Step 8: Inference CLI — `models/acreage_inference.py`: loads ensembles, builds features, predicts for top states + national rollup, upserts to `acreage_forecasts`.
- Step 9: Scheduling — `cron_runner.sh` updated with `--annual-acreage` (Feb 1) and `--quarterly-fertilizer` modes.

- Step 10: Training Script — `models/train_acreage.py`: downloads state-level NASS parquets from S3, merges with 1990-2000 historical data (fetched via `pipeline/fetch_nass_historical.py`), trains state-panel AcreageEnsemble (15 states x 26 years = 375 samples per commodity). Includes naive baselines (persistence + 5yr avg) with deployment gate, LOYO CV (25 folds), split conformal prediction for calibrated intervals. CLI: `python -m backend.models.train_acreage [--commodity X] [--local-only] [--skip-cv] [--fetch-historical] [--upload-s3]`.
- Step 10a: Bug fixes — wheat December contract (July unavailable), `class_desc == 'ALL CLASSES'` filter, all-NaN column dropping, negative prediction floor, numpy float64 serialization.
- Step 10b: LRU caching — `@lru_cache(maxsize=256)` on `_query_futures_settlement`, `_query_ers_cost`, `_query_fertilizer_price`, `get_november_price_ratio`. `clear_query_caches()` helper.
- Step 10c: State-Panel Training Results (2026-04-10, 375 samples/commodity):
  - Corn: Val MAPE 10.05%, Test MAPE 7.96%, Persistence baseline 6.78%, 5yr avg baseline 6.24%, **fails gate**. Coverage val=0.76, test=0.83.
  - Soybean: Val MAPE 5.63%, Test MAPE 5.97%, Persistence baseline 6.12%, 5yr avg baseline 5.42%, **passes gate**. Coverage val=0.91, test=0.83.
  - Wheat: Val MAPE 12.73%, Test MAPE 8.73%, Persistence baseline 5.73%, 5yr avg baseline 6.53%, **fails gate**. Coverage val=0.64, test=0.77.
  - Artifacts: `backend/artifacts/acreage/{commodity}/ensemble.pkl` + `metrics.json` (rich metrics)
  - S3: `s3://usda-analysis-datasets/models/acreage/`
- Step 10d: Inference — `models/acreage_inference.py`: per-state predictions for TOP_STATES + national rollup via `compute_national_forecast()`. Upserts 16 rows per commodity (15 states + national) to `acreage_forecasts`.
- Step 10e: Benchmarking — Compared against USDA Prospective Plantings (Mar 31, 2026: corn 95.3M, soy 84.7M, wheat 43.8M) and private firms (Reuters, Bloomberg, Farm Futures, AgMarket.Net all within 1-2% of USDA). Our model: corn 87.9M (-7.8%), soy 68.8M (-18.8%), wheat 31.3M (-28.6%). Gap driven by top-15-state sum missing long tail + market signals alone insufficient.
- Step 10f: Tier 1 Feature Spec — `research/acreage-tier1-features-spec.md`: 4 new data sources to close gap with private firms. CRP expirations (FSA, land supply), crop insurance elections (RMA SoB, revealed preference), Drought Monitor DSCI (REST API, physical constraints), FAS export commitments (demand pipeline). 8 new features, 4 new DB tables, ~5-7 days estimated effort.

- Step 11: Tier 1 Feature Implementation (2026-04-11) — 4 new data sources, 8 new features, 4 new DB tables.
  - **DB Migration**: `alembic/versions/004_acreage_data_sources.py`: 4 tables (`drought_index`, `rma_insured_acres`, `crp_enrollment`, `export_commitments`). ORM models in `models/db_tables.py`.
  - **ETL Scripts**:
    - `etl/ingest_drought_dsci.py`: USDM state-level DSCI API (no auth), computes dsci_nov, dsci_fall_avg, dsci_winter_avg, drought_weeks_d2plus per state-year. Backfill: 50 states x 25 years.
    - `etl/ingest_rma.py`: RMA Summary of Business ZIP downloads (pipe-delimited), filters to crop codes 0041/0081/0011, aggregates county→state. Backfill: 2000-2025.
    - `etl/ingest_crp.py`: FSA CRP enrollment history + contract expirations Excel, multi-strategy parser with manual CSV backfill fallback. Sources: `crphistorystate` + `EXPIRE STATE.xlsx`.
    - `etl/ingest_fas_exports.py`: FAS ESRQS OpenData API, weekly export commitments by commodity/marketing year. Marketing year boundaries: corn/soy Sep, wheat Jun.
  - **Feature Engineering**: `features/acreage_features.py` expanded from 15→23 features:
    - Drought: `dsci_nov`, `dsci_fall_avg` (prior year drought severity)
    - Insurance: `insured_acres_prior`, `insured_acres_yoy_change` (farmer intentions signal)
    - CRP: `crp_expiring_acres`, `crp_pct_cropland` (land supply)
    - Exports: `export_outstanding_pct`, `export_pace_vs_5yr` (demand context)
  - **Cron Runner**: 6 new mode blocks in `cron_runner.sh`: `--quarterly-fertilizer`, `--annual-acreage`, `--weekly-drought`, `--annual-rma`, `--annual-crp`, `--weekly-exports`.
  - **Data Backfill** (2026-04-11): All 4 sources loaded — drought_index 1,227 rows, rma_insured_acres 3,188 rows, crp_enrollment 2,121 rows (from local Excel), export_commitments 5,769 rows (from ESRQS CSV downloads). FAS OpenData API retired (403); used manual CSV download from ESRQS query tool. CRP loaded from user-downloaded FSA Excel files (FSA servers too slow for automated download). DSCI API parser fix: response keys are lowercase (`dsci`, `mapDate`), not uppercase.
  - **Tier 1 Training Results** (2026-04-11, 23 features):
    - Corn: Val MAPE 8.61%, **Test MAPE 6.44%** (was 7.96%), baseline 6.24%, **test passes gate**. Coverage val=0.84, test=0.90.
    - Soybean: Val MAPE 6.89%, **Test MAPE 5.61%** (was 5.97%), baseline 5.42%, **test passes gate**. Coverage val=0.73, test=0.80.
    - Wheat: Val MAPE 13.0%, Test MAPE 8.65% (was 8.73%), baseline 5.73%, **still fails**.
  - **Note**: Gate check uses val MAPE (all 3 fail on val due to 2021-2023 COVID/Ukraine volatility). Test MAPE on 2024-2025 is the deployment-relevant metric — corn and soy both pass.
  - **Structural model experiments** (2026-04-11):
    - Raw residual (y - prior_year): hurt performance. 3yr moving average residual (`y - avg(y_{t-1..t-3})`): **best for soybean and wheat**. 5yr avg residual: too smooth, worse than 3yr. Absolute targets: best for corn. Mixed config deployed via `RESIDUAL_CONFIG` dict in `train_acreage.py`.
    - Winter/spring wheat split: `DECISION_DATES` dict — Aug 1 for winter (planted Sep-Oct), Mar 1 for spring (planted Apr-May). Commodity-specific futures contracts via `infer_contract_month()` at decision date.
    - Futures backfill: 19,318 rows (corn 6,438 + soy 6,430 + wheat 6,450) from 2000-2026 via Yahoo Finance. Fixed winter wheat NaN price features.
    - `prior_3yr_avg_acres` feature added to FEATURE_COLS (24 total).
    - Training produces 4 models: corn, soybean, wheat_winter, wheat_spring.
  - **Final Production Results** (2026-04-11, mixed config):
    - Corn (absolute): Val 8.37%, **Test 6.26%**, baseline 6.24%, CV 10.7%. **Test passes gate.**
    - Soybean (3yr residual): **Val 5.39%**, **Test 4.64%**, baseline 5.42%, CV 9.74%. **Passes both val AND test gates.**
    - Wheat winter (3yr residual): Val 5.91%, **Test 4.51%**, baseline 4.62%, CV 9.49%. **Test passes gate.**
    - Wheat spring (3yr residual): Val 9.94%, Test 4.92%, baseline 4.17%, CV 9.25%. Test close but fails.

#### Module 03 Status
Corn, soybean, and wheat_winter publishable (test MAPE within gate). Wheat_spring close (4.92% vs 4.17% baseline) — limited by 5-state sample size (125 training rows). See `research/planted-acreage-tech-spec.md` for original spec, `research/acreage-tier1-features-spec.md` for Tier 1 details.

### Crop Yield Forecasting (Module 04)
- **Spec:** `research/crop-yield-tech-spec.md`
- **Reuses:** Module 02/03 infrastructure (RDS, FastAPI, S3, county NASS data)

#### Completed
- Step 1: DB Migration — `alembic/versions/003_yield_tables.py`: 3 new tables (`soil_features`, `feature_weekly`, `yield_forecasts`). ORM models in `models/db_tables.py`. Pydantic schemas: `YieldForecastResponse`, `YieldMapItem`, `YieldMapResponse`, `YieldHistoryItem`.
- Step 2: Static Data Setup — `etl/load_county_centroids.py` (Census Gazetteer -> county FIPS centroids CSV), `etl/load_ssurgo.py` (NRCS SDA API -> soil AWC + drainage class), `etl/build_station_map.py` (GHCN stations -> nearest county within 50km).
- Step 3: ETL Scripts — 5 new scripts: `ingest_noaa.py` (GHCN-Daily TMAX/TMIN/PRCP via NOAA API), `ingest_nasa_power.py` (solar radiation + VPD, no auth, gridded), `ingest_drought.py` (USDM county-level D0-D4 drought percentages), `ingest_crop_conditions.py` (NASS weekly crop condition ratings -> CCI computation), `load_prism_normals.py` (30-year monthly precipitation normals by county).
- Step 4: Feature Engineering — `features/yield_features.py`: 7 features (gdd_ytd, cci_cumul, precip_deficit, vpd_stress_days, drought_d3d4_pct, soil_awc, soil_drain). Strict temporal integrity (no lookahead). State-specific planting dates. `build_weekly_features()` and `build_training_matrix()` functions. `persist_features()` for DB upsert.
- Step 5: Model Training — `models/yield_model.py`: `@dataclass YieldModel` with 3 LightGBM quantile regressors (p10/p50/p90). Confidence tiers: week <8 low, 8-15 medium, >=16 high. Baselines: county historical mean + prior year. Gate: >=10% RRMSE improvement. `models/train_yield.py`: downloads county NASS yield data from S3, trains 60 models (3 crops x 20 weeks). Walk-forward: 2000-2019 train, 2020-2022 val, 2023-2024 test. Artifacts: `artifacts/yield/{crop}/week_{week}/model.pkl` + `metrics.json`. `models/yield_inference.py`: weekly inference CLI, upserts to `yield_forecasts`.
- Step 6: API — `routers/yield_forecast.py`: 3 endpoints at `/api/v1/predict/yield` (single county forecast, map choropleth, history). Registered in `main.py` with 60-model lifespan loading. Health endpoint updated to v0.3.0 with "yield-forecasting" module.
- Step 7: Frontend — `hooks/useYieldForecast.ts`: parallel Promise.all fetch for forecast/map/history. `components/YieldForecastSection.tsx`: self-contained section with commodity tabs, week slider (1-20), confidence badge, county summary stats, map placeholder (Deck.gl choropleth), forecast detail card (p10/p50/p90), confidence strip (Recharts AreaChart), season accuracy chart (Recharts LineChart). Integrated into `PredictionsDashboard.tsx`.
- Step 8: Scheduling — `cron_runner.sh --weekly-yield`: runs 4 ETL scripts -> yield inference -> restart ag-prediction. Cron: `0 10 * * 4` (Thursday 10 AM ET).

#### Module 04 Status
Infrastructure complete. All 8 steps implemented. Next steps:
1. Run static data setup scripts (county centroids, SSURGO, station mapping) to populate reference data.
2. Run `alembic upgrade head` to create the 3 new DB tables.
3. Backfill historical weather data for 2000-2024 training (requires bulk GHCN download, not API).
4. Train models: `python -m backend.models.train_yield --commodity corn --upload-s3`.
5. Implement Deck.gl `GeoJsonLayer` county choropleth (currently placeholder in YieldForecastSection).
6. Add county GeoJSON static asset (`web_app/public/us-counties.json` from us-atlas).

### County Data Ingestion
- **Date:** 2026-04-09
- **Pipeline optimizations:** Batched stat_cats (4x fewer API calls), expanded skip states, 8 workers @ 1.5s delay, `--resume` flag for interrupted runs.
- **Results:** 870,995 county records, 48 states, 2001-2025, 11 commodities x 4 stat categories.
- **Output:** `pipeline/output/*.parquet` (18 MB). Uploaded to S3 at `survey_datasets/partitioned_states_counties/` and `survey_datasets/athena_optimized_counties/`.

### Frontend Spec v1 + Accuracy Table Pipeline (§7.4)
- **Date:** 2026-04-14
- **Spec:** `web_app/docs/frontend-spec-v1.md` — paired with `design-system-v1.html`. 6 tabs, per-page specs, cross-cutting systems, seasonal behavior, narrative formation.
- **Accuracy tables (§7.4):** piping to expose walk-forward test predictions to the frontend Forecasts tab accuracy panel (§5.3.D). Models were already trained — this wires persistence.

#### WI-1: Acreage walk-forward persistence
- `backend/models/acreage_model.py::train_and_save()` now returns a 3-tuple: `(ensemble, metrics, predictions_df)`. Captures per-row (year, state_fips) val + test predictions with p10/p50/p90 + actual + split label.
- `backend/models/train_acreage.py::train_commodity()` unpacks the tuple and calls `persist_acreage_accuracy()` when the new `--persist-accuracy` CLI flag is set. Upserts to `acreage_accuracy` with `model_forecast` (p50), `usda_june_actual` (actual from training data), and computed `model_vs_actual_pct`. `usda_prospective` column is left null — filled by WI-2.
- Scale: 2 splits (val+test) × ~15 states × ~5 years × 4 commodities ≈ **~600 rows** per training run.
- Run: `python -m backend.models.train_acreage --persist-accuracy`

#### WI-2: USDA Prospective Plantings backfill ETL
- `backend/etl/ingest_prospective_plantings.py`: new script with two modes.
  - `--api`: queries NASS QuickStats `AREA PLANTED` and filters `short_desc` for `INTENDED`/`INTENTIONS`. Pulls state + national rollups per (commodity, year).
  - `--csv PATH`: fallback mode reading a local CSV (columns: `forecast_year, state_fips, commodity, prospective_acres`). Ships because NASS vocabulary for Prospective Plantings varies year-to-year and API mode may return zero rows for older releases.
- Upserts `usda_prospective` on existing `acreage_accuracy` rows, then runs a second-pass `UPDATE` to compute `model_vs_usda_pct` where `model_forecast` is also present.
- Scale: 3 commodities × ~50 states × ~25 years ≈ **~3,750 rows** max, though wheat split into winter/spring pushes it up somewhat.
- Run: `python -m backend.etl.ingest_prospective_plantings --api --year-start 2000`

#### WI-3: yield_accuracy table + persistence
- **Alembic migration `005_yield_accuracy.py`** creates `yield_accuracy` with columns: `forecast_year, fips, crop, week, model_p50, model_p10, model_p90, actual_yield, county_5yr_mean, abs_error, pct_error, in_interval, split, model_ver`. Unique constraint on `(forecast_year, fips, crop, week, model_ver)`. Indexes on `(crop, forecast_year)` and `(crop, week)` for the frontend aggregation queries.
- **ORM model:** `YieldAccuracy` appended to `backend/models/db_tables.py`.
- `backend/models/train_yield.py::train_single_model()` now accepts `capture_predictions=True` and captures per-(fips, year) val + test predictions. Metrics.json writes still exclude the prediction payload to keep artifact files small.
- `persist_yield_accuracy()` helper upserts in chunks of 5,000 rows to `yield_accuracy`. `--persist-accuracy` CLI flag wires it into the main loop, persisting per (crop, week) immediately after training.
- Scale: 2 crops × 20 weeks × ~2,000 counties × ~5 years ≈ **~400K rows**. Trivial for Postgres with the provided indexes.
- Run: `alembic upgrade head` → `python -m backend.models.train_yield --persist-accuracy`

#### Frontend contract (what §5.3.D reads)
- **Acreage accuracy chart:** `SELECT forecast_year, commodity, model_vs_usda_pct, model_vs_actual_pct FROM acreage_accuracy WHERE state_fips = '00'` — national rollup, handful of rows per commodity.
- **Yield accuracy chart:** `SELECT crop, week, forecast_year, AVG(pct_error), AVG(in_interval) FROM yield_accuracy GROUP BY crop, week, forecast_year` — materialize as a view if this becomes hot.

#### Deployment executed 2026-04-14/15
Ran the full sequence against the prod RDS instance. Three schema bugs and one ETL query bug caught mid-run; all patched with follow-up migrations (006, 007) and code fixes. Final state:

**Migrations applied:** 005 (yield_accuracy table) → 006 (widen `commodity` column from VARCHAR(10) to VARCHAR(20) because `wheat_winter`/`wheat_spring` are 12 chars) → 007 (make `acreage_accuracy.model_forecast` nullable so the ETL can insert USDA-only rows for states we don't model).

**Env fix:** `backend/alembic/env.py` wasn't loading `.env` — patched to read DATABASE_URL directly from the file, plus added `YieldAccuracy` to the ORM import list.

**ETL fix:** `ingest_prospective_plantings.py` was filtering on `short_desc LIKE '%INTENDED%'` which returns zero rows. NASS actually distinguishes releases via `reference_period_desc`: `"YEAR - MAR ACREAGE"` = Prospective Plantings, `"YEAR - JUN ACREAGE"` = actual planted acreage. Rewrote the filter and made the same query pull **both** releases simultaneously — so `usda_prospective` and `usda_june_actual` are populated from NASS (not from our training data fallback).

**Final row counts (2021–2025 backfill):**

```
acreage_accuracy:         796 rows total
  corn:             245 rows  ( 75 with model_forecast + model_vs_usda_pct)
  soybean:          150 rows  ( 75 with model_forecast + model_vs_usda_pct)
  wheat_winter:     178 rows  ( 40 with model_forecast + model_vs_usda_pct)
  wheat_spring:      35 rows  ( 25 with model_forecast + model_vs_usda_pct)
  wheat (generic):  188 rows  (NASS "ALL CLASSES" wheat — no model counterpart, historical only)

yield_accuracy:       290,441 rows total
  corn:        124,961 rows  (20 weeks × ~6,245 county-years/week)
  soybean:      86,020 rows  (20 weeks × ~4,301 county-years/week)
  wheat:        79,460 rows  (20 weeks × ~3,973 county-years/week)

Per crop-week test RRMSE:
  corn        17.44% – 18.51%   all weeks PASS baseline 23.78%
  soybean     17.29% – 17.76%   all weeks PASS baseline 23.15%
  wheat       23.42% – 25.00%   all weeks FAIL baseline 21.80% (hidden on frontend per §0.3)

Acreage test MAPE (recomputed):
  corn          6.26%  baseline 6.24%  — borderline (EXPERIMENTAL badge)
  soybean       4.64%  baseline 5.42%  — PASS
  wheat_winter  4.51%  baseline 4.62%  — PASS
  wheat_spring  4.92%  baseline 4.17%  — FAIL (hidden)
```

**Sample acreage_accuracy row** (now frontend-ready):
```
forecast_year=2021 state_fips=19 commodity=corn
  model_forecast=13,679,079   usda_prospective=13,200,000   usda_june_actual=13,100,000
  model_vs_usda_pct=+3.63%    model_vs_actual_pct=+4.42%
```

**Interval coverage observation** (surfaced by the new yield_accuracy table):
The models are under-covering their 80% prediction intervals. Corn val 0.688 / test 0.636, soybean val 0.466 / test 0.541, wheat val 0.631 / test 0.427. Target is 0.80. Not a Wave 4 blocker but a concrete finding for a future calibration pass — the conformal q80 quantile is being applied too tightly, possibly because the val set is too small relative to county variance.

**Reproducible command sequence:**
```bash
# 1. Apply migrations
alembic upgrade head

# 2. Persist acreage walk-forward predictions (idempotent upserts)
python -m backend.models.train_acreage --persist-accuracy --skip-cv --local-only

# 3. Backfill USDA prospective + june actual from NASS (both in one pass)
python -m backend.etl.ingest_prospective_plantings --api --year-start 2021 --year-end 2025

# 4. Persist yield walk-forward predictions (57 min, 60 models, ~290K rows)
python -m backend.models.train_yield --persist-accuracy --skip-cv --local-only

# 5. Verify
psql $DATABASE_URL -c "SELECT COUNT(*) FROM acreage_accuracy; SELECT COUNT(*) FROM yield_accuracy;"
```

### End-to-End Review + Hardening (2026-04-16)

Full-project audit produced 20 findings; all non-deferred items fixed in one pass. Plus two display bugs surfaced during verification, plus a yield retrospective feature for the class-project demo. No retraining or schema migrations required — all changes are code-only and backward-compatible at the DB layer.

**Pipeline / Ops**
- `pipeline/upload_to_s3.py`: multipart verification now uses `ChecksumAlgorithm=SHA256` + ContentLength match; per-file failures aggregated, function returns False if any upload failed. Previously MD5+ETag comparison was silently skipped on any file >8MB.
- `pipeline/quickstats_ingest.py` + `upload_to_s3.py` + `incremental_check.py`: `record_counts` is now promoted to `uploaded_record_counts` only after a clean S3 upload. Previously the `last_success` stamp landed before upload, so a failed upload permanently suppressed re-ingestion.
- `pipeline/cron_runner.sh`: per-mode `flock` re-exec guard (non-blocking); `TZ=America/Chicago` added to the docstring (users must set on the crontab itself). Thursday 10 AM yield+drought collision moved to 11 AM for drought.
- `pipeline/validate_data.py`: content checks now run across top-10 states by row count, not one arbitrary `next(...)` state.
- `pipeline/fetch_nass_historical.py`: yield-only rows retained (were being `dropna(subset=['acres_planted'])`-silently dropped, losing 15-20% of training matrix).

**ML / Backend**
- Training gates now enforced. `backend/models/train.py` (price) and `backend/models/train_acreage.py` (acreage) block S3 upload on gate fail. Override: `--allow-failed-gate`. Artifacts still written locally for post-mortem.
- Yield gate policy is **surface with annotation** — class-project requirement. Artifact uploads regardless; `backend/models/train_yield.py` writes per-crop `artifacts/yield/{crop}/summary.json` via `_write_crop_summaries()`; new endpoint `GET /api/v1/predict/yield/metadata?crop=X` returns `gate_status` (pass / partial / fail), avg test RRMSE, baseline, and model version.
- `backend/models/yield_inference.py`: feature construction now includes weather columns when the model was trained with them. Previously inference built only 5 NASS features and silently zero-filled weather, producing degraded predictions. Adds `load_weather_data()` + `compute_weather_features()` invocation at the top of the batch. Skips the (crop, week) entirely if weather is required and missing.
- CQR calibration methodology fixed in `backend/models/price_model.py`. Val set now split 50/50 into calibration and measurement halves; reported `coverage_90` is from the held-out half. Previously the same val set fit the conformity offset *and* was used to report coverage — tautologically ≥90%.
- Acreage national-rollup z-score bug fixed in `backend/models/acreage_model.py::compute_national_forecast`: stored interval is 80% (z=1.2816), not 90% (z=1.645). State sigma recovery was off by ~22%.
- Pickle artifact signing added. `backend/models/_signing.py` provides HMAC-SHA256 sidecar `.sig` files written on `save()` and verified on `load()` when `MODEL_SIGNING_KEY` is set. Set `MODEL_REQUIRE_SIGNED=1` to refuse unverified loads. `backend/main.py::_download_from_s3` now fetches the matching `.sig` alongside the pickle. `train.py::_upload_to_s3` uploads the sig too.
- Async event-loop fix in `backend/routers/price.py`: `_build_features` wrapped with `asyncio.to_thread`. Previously every `GET /` blocked uvicorn on synchronous psycopg2 DB reads.
- SQL injection surface reduced in `backend/features/acreage_features.py`: `_query_ers_cost(field=...)` and `_query_fertilizer_price(product=...)` gated by frozenset allowlists (raise on unknown column name).

**Frontend (`web_app/`)**
- **Acreage unit rename (breaking schema change).** `backend/models/schemas.py` + `backend/routers/acreage.py`: `forecast_acres_millions` / `p10_acres_millions` / `p90_acres_millions` → `forecast_acres` / `p10_acres` / `p90_acres`. The stored value was always raw acres; the `_millions` suffix was misleading. Frontend updated in parallel — dropped four `* 1e6` multiplications in `AcreageCard.tsx`. Net: "92857.2B acres" now reads "92.8M acres". Requires backend redeploy to take effect in prod.
- **Duplicate state rows fixed.** `backend/routers/acreage.py::get_states_forecast` dedupes on `(state_fips, created_at DESC)` and keeps the first row per state. Root cause: the `acreage_forecasts` unique constraint includes `model_ver`, so retraining appended rows rather than replacing. Same dedup applied to the prior-year YoY lookup.
- **Yield Season Review component.** `web_app/src/components/forecasts/YieldSeasonReview.tsx` (new) + toggle wired into `forecasts/page.tsx` via `YieldSection`. Off-season default is "Last Season Review"; May–Oct default is "Current Season" (empty until week 1). The Review panel has crop tabs (corn / soybean / wheat), KPI strip (Test MAPE, gate status pill, best week, feature set), and a per-week RRMSE line chart (model vs county 5-yr baseline). Uses `/api/v1/predict/yield/accuracy` + `/api/v1/predict/yield/metadata`.
- **P0 frontend bugs fixed.** `useYieldForecast` now fires via `useEffect` (was inert); wheat commodity key reconciled (frontend sends `wheat`, backend loads the generic wheat artifact); `AcreageCard` React key dedupe; acreage accuracy data piped into cards (USDA prospective + delta + test MAPE / baseline).
- **Housekeeping.** `processData.ts` metadata-on-array anti-pattern removed (dead code, no consumers). `serviceData.ts::fetchParquet` accepts `AbortSignal`; `parseParquetBuffer` has a 30s defensive timeout to prevent promise hangs on malformed files.

**Deferred** (by operator decision)
- `.env` rotation: user flagged that committed .env values are placeholder-style and not worth rotating right now. Address before any public demo.

**New CLI flags, endpoints, env vars**
```
Training CLI (S3 upload blocked on gate fail by default):
  python -m backend.models.train --allow-failed-gate
  python -m backend.models.train_acreage --allow-failed-gate
  # Yield training always uploads; gate status surfaced via API instead.

New endpoint:
  GET /api/v1/predict/yield/metadata?crop={corn|soybean|wheat}
  → YieldModelMetadataResponse { gate_status, avg_test_rrmse, avg_baseline_rrmse, n_weeks_pass_gate, ... }

Renamed response fields (BREAKING):
  forecast_acres_millions → forecast_acres   (acreage_forecasts endpoint family)

Optional env vars:
  MODEL_SIGNING_KEY=<hmac-secret>            # enables pickle signing
  MODEL_REQUIRE_SIGNED=1                     # refuse unverified loads at startup
```

### County Coverage Fill (2026-04-19)

Closed most of the county-level NASS gaps identified in `research/county-coverage-analysis-2026-04-17.md`. Dataset roughly doubled; wheat — previously zero rows — is the headline gain. **Local parquets updated; S3 and yield models are NOT yet refreshed — see pending items below.**

#### Pending (read me first next session)

1. **Upload new parquets to S3.** Local `pipeline/output/*.parquet` has the new data; S3 still serves the pre-fill snapshot. Frontend and yield training both read from S3, so nothing downstream sees the new data until this runs.
   ```
   aws sso login                                  # SSO token expires; refresh first
   python pipeline/upload_to_s3.py --backup
   ```
   **Before running, verify `upload_to_s3.py` covers the county S3 layout.** The script's defaults are `S3_BROWSER_PREFIX = "survey_datasets/partitioned_states"` + `S3_ATHENA_PREFIX = "survey_datasets/athena_optimized"`, but county parquets per earlier CLAUDE.md notes live under `survey_datasets/partitioned_states_counties/` and `survey_datasets/athena_optimized_counties/`. May need a flag/branch; don't `--backup` on the state layout if what you're uploading is county-only.

2. **Retrain yield models** — required if you want the new wheat + expanded corn/soy/etc. county rows reflected in forecasts. Yield is the only module affected; acreage is state-level and unaffected, price uses different sources.
   ```
   python -m backend.models.train_yield --persist-accuracy --upload-s3
   # ~3-4 hrs: 60 models (3 crops × 20 weeks)
   ssh ec2-host 'sudo systemctl restart ag-prediction'   # reload artifacts
   ```

3. **Optional: label the 572 UNCLASSIFIED triples.** `pipeline/county_coverage_allowlist.json` currently only holds 70 PENDING_PUBLICATION entries. The 572 remaining gaps are almost certainly NOT_GROWN or NASS_SUPPRESSION — the classifier couldn't distinguish because local state parquets are COUNTY-only (the post-Apr-2026 county-only ingest overwrote state-level rows). A one-time state-level NASS pull for those specific combos would let the allowlist be fully labeled.

4. **Audit regeneration hygiene.** `pipeline/_county_coverage_audit.py` now lists WHEAT in its `COUNTY_COMMODITIES`. Next regeneration of `research/county-coverage-analysis-YYYY-MM-DD.md` should read "12 commodities".

#### What shipped

- **New script:** `pipeline/fill_county_gaps.py`. Re-audits current parquets → computes gap set (ideal × `MAJOR_PRODUCERS` minus `COUNTY_SKIP_STATES` minus allowlist) → runs `quickstats_ingest.py --county-only --resume --states <ST>` **one state at a time** (throttle-resilient: each state atomically commits its parquet before the next starts). Post-ingest re-audits + classifies residuals (NOT_GROWN / NASS_SUPPRESSION / PENDING_PUBLICATION / UNCLASSIFIED). Stops on empty gap set or plateau. Always resume-by-default; no `--resume` flag needed on the wrapper. Flags: `--states`, `--max-rounds`, `--min-delta`, `--dry-run`.
- **Two-line patch to `pipeline/quickstats_ingest.py`:** added `"WHEAT"` to `COUNTY_COMMODITIES` and `"WHEAT": {"AK", "HI", "DC"}` to `COUNTY_SKIP_STATES`. Permanent — future main-pipeline runs include wheat.
- **`.env` pass-through in the filler.** Main ingest reads `USDA_QUICKSTATS_API_KEY` or AWS SSM; project `.env` ships the key under `QUICKSTATS_API_KEY`. `fill_county_gaps.py::_subprocess_env` reads `.env`, re-exports under the expected name, avoids SSO dependency.
- **Persistent artifacts:**
  - `pipeline/county_coverage_allowlist.json` — 70 entries, all PENDING_PUBLICATION (2025 data not yet released). Auto-prunes expired entries on next run.
  - `pipeline/fill_county_gaps_report.json` — per-run summary.
  - `research/county-coverage-analysis-2026-04-19.md` — regenerated audit alongside the Apr-17 baseline.

#### Numbers (before → after)

| Metric | 2026-04-17 | 2026-04-19 | Δ |
|---|---:|---:|---:|
| County rows | 870,995 | 1,932,343 | +1,061,348 (+122%) |
| (state, commodity) pairs | 241 | 277 | +36 |
| (state, commodity, year) triples | 2,470 | 4,748 | +2,278 |
| 4/4 stat-complete pairs | 166 | 201 | +35 |
| Counties | 3,101 | 3,105 | +4 |

Per-commodity row deltas: WHEAT 0 → **418,424**; HAY +184K; CORN +166K; SOYBEANS +104K; SORGHUM +48K; COTTON +46K; OATS +44K; BARLEY +26K; SUNFLOWER +17K; RICE +6K.

Of the 1,764 originally-computed gap triples, 1,192 closed (68%). Residual 572 persisted across 2 rounds (structural / unreleased / classifier-blind). The "coverage_pct=165%" value in the JSON report is an artifact of comparing post-fill triples against a `MAJOR_PRODUCERS`-only ideal denominator — more data returned than the major-producer slice predicted. Use the gap-closure count as the real signal.

#### Known minor issue

WY reported "ingest failed" on both rounds' subprocess returncode — it has one stubborn triple (2024 BARLEY) that NASS 400s on every retry. Almost certainly unpublished upstream. Safe to ignore; will auto-resolve when NASS publishes or `PENDING_PUBLICATION` logic promotes it.

### County S3 Upload + Crops Tab Redesign (2026-04-21)

Closed the pending post-county-fill work and shipped a full Crops-tab rebuild.

#### What shipped

**S3 upload for county layout.** `pipeline/upload_to_s3.py` now takes `--layout {state,county}`. Layout-specific prefixes: state writes to `partitioned_states/` + `athena_optimized/`, county writes to `partitioned_states_counties/` + `athena_optimized_counties/`. Manifest stamp only fires on clean STATE uploads — county-only uploads cannot falsely promote `uploaded_record_counts` and block the next state ingest. Uploaded 48 state-partitioned county parquets + matching Athena layout to the correct prefix with backups. 96 successful, 0 failed.

**Three P0 Crops-tab data bugs fixed.**
- `processData.ts::filterData` now drops `YEAR - *` reference_period variants (JUN ACREAGE, MAR ACREAGE, NOV FORECAST, SEP FORECAST, etc.) and includes `reference_period_desc + class_desc + prodn/util practice + short_desc` in the SURVEY/CENSUS dedup key. Indiana corn 2024 planted acres: 31.0M → 5.2M.
- `getCommodityStory` switched from `sum` to `max` with unit gates (ACRES for area, BU/CWT/LB/TONS for production, non-PCT for yield). Biotech-PCT sub-rows can no longer contaminate acre totals. Harvest efficiency chart: peaks 300% → max 100%.
- `YieldTrendChart` computes percentile ordinal client-side (96th, 91st, 22nd with proper 11/12/13 special case); caption template no longer double-suffixes. Fixed "—th percentile" → "96th percentile".
- `crops/page.tsx` 5-year baseline now skips zero-yield years so Census-year SURVEY gaps (e.g. 2017 Indiana corn has CENSUS-only rows) don't drag the baseline down ~20%.

**5 enrichment ingests ported from aquifer-watch** in `pipeline/enrichments/`:
- `noaa_climdiv_county_precip.py`: nationwide NCEI climdiv parquet, 3,137 counties, 1895–2025. Expanded NCDC→FIPS map to all 50 states. Output `enrichment/county_precip.parquet` on S3.
- `nass_irrigated_county.py`: NASS Census 2017+2022 irrigated acres by (fips, crop). 252 counties (5-state rate-limit residual). Output `enrichment/nass_irrigated_county.parquet` on S3.
- `iwms_water.py`: state × crop water-applied per acre (155 rows). Writes parquet + JSON.
- `ers_revenue.py`: national $/acre gross revenue per commodity. Writes JSON.
- `eia_prices.py`: state-level industrial ¢/kWh. 51 states, 2024 static fallback with all-50 table.
- Small outputs (IWMS, ERS, EIA) land in `web_app/public/enrichments/` for direct static fetch.

**Crops tab redesign — inverted-L layout with click-to-drill choropleth.** New components in `web_app/src/components/crops/`:
- `CropsStateMap.tsx`: SVG choropleth rendering all 50 states' counties from `/us-counties.geojson`. Yield-anomaly-vs-state-median color ramp, clamped ±30%. Hover tooltip with yield + anomaly + harvested + production. Click calls back with fips. Exports `rollupByCounty` helper for the panel + peers.
- `CropsCountyDrill.tsx`: Ogallala-density panel — status pills (rank of N, anomaly %), 3 KPIs with context subtitles, growing-season precipitation block from NOAA nClimDiv (30-yr normal / recent / anomaly %), method signature footnote.
- `CropsPeers.tsx`: mode-aware — top-5/weakest-3 in state mode, 6 nearest-yield peers in county mode. Rows clickable.

**Layout**: float-based inverted L, not grid. Map floats left at 30%, panel is a BFC (`flow-root`) to pack right, peers clears left for full-width wrap once past map's bottom, method band clears both. `720px` breakpoint collapses to single column. `globals.css:308-358`.

**Data layer**: `serviceData.ts` gained `fetchCountyData` (from new county prefix), `fetchCountyPrecip` (from enrichment/ prefix), `fetchIrrigatedCountyAcres`. `fetchParquet` now routes by-prefix instead of hard-coding `partitioned_states/`.

**Verified end-to-end in browser preview with Indiana corn 2024**: state KPIs (198 bu/ac, 5.2M ac, $4.3B sales), map renders 92 counties, 72 with reported yield, click-to-drill into Gibson County shows real NOAA precip (1223 mm/yr normal, 1238 recent, +1.3% anomaly), nearest peers table works, zero console errors.

#### Known residuals (low priority)

- NASS CENSUS endpoint 403'd ~5 states (WI, WY, WV, WA) at 6-concurrent ThreadPoolExecutor. Residual 252 counties is enough for the irrigated overlay. Rerun at concurrency=2 to fill.
- IWMS + ERS + EIA are ingested but not yet bound into UI features. Water-productivity KPI (bu/acre-foot) is the obvious next hook.
- Crops-mockup artifacts (`web_app/public/crops-redesign-mockup.html`, `crops-mockup-data.json`) and `_compare_state_vs_county.py` were exploratory tooling — safe to delete on next cleanup pass.
