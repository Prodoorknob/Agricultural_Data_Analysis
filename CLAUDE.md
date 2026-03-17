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
| RDS | PostgreSQL (db.t3.micro, us-east-2) — prediction module data [TO PROVISION] |
| SNS | `arn:aws:sns:us-east-2:294733692749:usda-pipeline-alerts` |

## Environment Variables

```bash
# Existing (in .env)
QUICKSTATS_API_KEY=...     # USDA QuickStats API
NOAA_API_KEY=...           # NOAA weather data

# Required for prediction modules (add to .env)
DATABASE_URL=postgresql+asyncpg://ag_app:PASSWORD@RDS_ENDPOINT:5432/ag_dashboard
NASDAQ_DL_API_KEY=...      # Nasdaq Data Link (CME futures) — obtained
FRED_API_KEY=...           # FRED API (DXY index) — obtained
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
- **API keys:** NASDAQ_DL_API_KEY and FRED_API_KEY obtained, need to add to `.env`
- **RDS:** db.t4g.micro, identifier `ag-dashboard`, master user `ag_app`, database `ag_dashboard`, us-east-2

#### Completed
- Step 1: CLAUDE.md created
- Step 2: FastAPI backend skeleton (`backend/`) — main.py, config.py, database.py, routers/price.py (stub endpoints), models/schemas.py, models/db_tables.py (ORM), alembic migration 001

#### Remaining Steps (in order)
- **Step 3: DB Migration** — Add DATABASE_URL + API keys to `.env`, run `cd backend && alembic upgrade head` to create 5 tables (futures_daily, wasde_releases, price_forecasts, ers_production_costs, dxy_daily)
- **Step 4: ETL Scripts** — `backend/etl/ingest_futures.py` (daily, Nasdaq Data Link CME), `ingest_fred.py` (daily, FRED DXY), `ingest_wasde.py` (monthly, USDA PSD CSV), `load_ers_costs.py` (annual, ERS Excel). Update `pipeline/cron_runner.sh`.
- **Step 5: Feature Engineering** — `backend/features/price_features.py`: build_price_features() with market, fundamental, macro, cost features. Pandera validation. MVP skips drought/CCI.
- **Step 6: Model Training** — `backend/models/price_model.py`: PriceEnsemble (SARIMAX + LightGBM point/quantile + Ridge meta + IsotonicRegression calibrator). SHAP key drivers, Mahalanobis regime detection. 18 model sets (3 commodities x 6 horizons). Artifacts to S3.
- **Step 7: API Implementation** — Fill in stub endpoints in `backend/routers/price.py`: GET /, /probability, /wasde-signal, /history. Load models on startup.
- **Step 8: Frontend** — `web_app/src/components/predictions/`: PriceFanChart, ProbabilityGauge, KeyDriverCallout, WasdeSignalCard, PriceRegimeAlert, PredictionsDashboard. New hook usePriceForecast.ts. Add PREDICTIONS tab to page.tsx.
- **Step 9: Scheduling & Deployment** — Extend cron_runner.sh, systemd unit for FastAPI on EC2
