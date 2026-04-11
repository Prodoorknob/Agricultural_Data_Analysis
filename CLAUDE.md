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
FastAPI Backend (EC2, port 8000) -> PostgreSQL (RDS)   [IN PROGRESS]
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

#### Module 03 Status
Training infrastructure complete. Soybean publishable; corn/wheat need Tier 1 features or residual modeling to beat persistence baseline. See `research/planted-acreage-tech-spec.md` for original spec, `research/acreage-tier1-features-spec.md` for next phase.

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
