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
