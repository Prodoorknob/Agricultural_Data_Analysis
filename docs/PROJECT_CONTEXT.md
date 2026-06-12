---
project: Agricultural Data Analysis
product-name: FieldPulse
aliases:
  - FieldPulse
  - ADS
  - Ag Dashboard
  - Agricultural Dashboard
owner: Raj Vedire
status: complete-maintenance
last-updated: 2026-06-12
tags:
  - project/agricultural-data-analysis
  - domain/agriculture
  - domain/usda
  - stack/nextjs
  - stack/react
  - stack/fastapi
  - stack/postgres
  - stack/aws
  - stack/lightgbm
  - stack/recharts
  - stack/deckgl
  - stack/maplibre
related-projects:
  - "[[Aquifer Watch]]"
  - "[[Cobbles & Currents Studios]]"
production:
  frontend: https://agricultural-data-analysis.vercel.app
  backend-api: https://agri-intel.rvedire.com
  rds: ag-dashboard.cvuu6ce8odqc.us-east-2.rds.amazonaws.com
  s3-bucket: usda-analysis-datasets
---

# Agricultural Data Analysis (FieldPulse), Master Context

> Single source of truth for project structure, decisions, deployment, modules, conventions, and collaboration preferences. Originally generated 2026-04-27; refreshed 2026-06-12 to cover Module 05 (analyst agent), the chart-enabled issue composer, the post-outage service restorations, and the Crops-tab specialty-crop expansion. Project is now **complete and in maintenance mode**.

## Project status: COMPLETE, maintenance mode (2026-06-12)

All five modules are built, deployed, and operating. The project is no longer in active feature development. Work from here is **maintenance only**: keeping the scheduled pipelines and the weekly agent running, applying small fixes, and the optional/deferred cleanup items tracked in [Known limitations and open items]. There is no open roadmap of new modules.

## TL;DR

FieldPulse is an interactive dashboard for exploring long-term U.S. agriculture trends (USDA QuickStats) and serving model-driven forecasts for commodity prices, planted acreage, and county-level crop yields, plus a weekly AI analyst agent that writes and publishes an agriculture newsletter. Frontend is Next.js 16 on Vercel; backend is FastAPI on EC2 backed by RDS Postgres; ML training runs locally and ships pickles to S3 which the API hot-loads. All five modules (M01 dashboard, M02 price, M03 acreage, M04 yield, M05 FieldPulse Weekly analyst agent) are complete and deployed. The project is in maintenance mode.

## Status snapshot (2026-06-12)

- **Modules complete:** M01 dashboard, M02 commodity price (18 ensembles), M03 planted acreage (4 ensembles), M04 county yield (60 quantile models), **M05 FieldPulse Weekly analyst agent (live in prod, cron Sun 17:00 CT)**.
- **Service restorations (post-outage recovery, 2026-06-11/12):** three latent failures that had silently broken core workflows are fixed, see [Service restorations]. Cron is runnable again, price inference writes to `price_forecasts`, and a FieldPulse issue now reaches an approvable draft for the first time.
- **Agent / Insights:** Module 05 runs the full mood / editor / researcher / writer / fact-check / reviser / compose / publish pipeline. A deterministic **composer** step now emits a typed `IssueSpec` so issues render as live Recharts charts + KPI strips at `/insights` (reference design at `/insights/model`).
- **Crops tab (2026-06-12, commit `6344c06`):** expanded beyond 11 field crops to fruits, nuts, and vegetables (the served state parquet already carried them); grouped dropdown picker; per-crop adaptive KPIs (yield/production, area planted/harvested/bearing, sales/value of production). Frontend only.
- **Latest commit (`6344c06`, 2026-06-12):** Crops-tab specialty-crop expansion.
- **Open items:** maintenance/cleanup only, see [Known limitations and open items]. No feature roadmap.
- **Out-of-scope deliverables also present locally:** devpost article, V2 pitch deck + speaker notes, yield-forecasting Word report, cloud-architecture doc + diagram, analyst-agent tech spec.

## What this project is

Interactive dashboard for exploring long-term trends in U.S. agriculture using USDA QuickStats data. Features choropleth maps, time-series charts, and state-level drill-downs across crops, livestock, land use, labor, and economics. Layered on top: ML-driven forecasts surfaced through a Predictions/Forecasts tab.

## Architecture

```
Next.js Frontend (React 19, Recharts, Deck.gl, MapLibre)
         |
    S3 (primary) / Local API (fallback) / Athena (advanced queries)
         |
Python Pipeline (EC2 cron) -> USDA API -> Parquet -> S3
         |
FastAPI Backend (EC2, port 8000) -> PostgreSQL (RDS)
         |
FieldPulse Weekly Agent (EC2 cron, Sun 17:00 CT) -> signal board -> LLM pipeline
         |                                          -> S3 + RDS + Slack -> /insights
         |
Production: Vercel (frontend + /insights) + https://agri-intel.rvedire.com (API + /api/v1/agent)
```

Local PC trains models, EC2 serves predictions and runs the weekly agent. Cost target ~$22/mo (RDS $15 + EC2 serving $6 + S3/Athena <$1); the agent adds ~$0.50 per weekly run in LLM cost.

## Tech stack

### Frontend (`web_app/`)
- Next.js 16 (App Router), React 19, TypeScript 5, TailwindCSS 4
- Recharts 3.7 (charts), Deck.gl 9.2 + MapLibre GL 5.18 (maps)
- hyparquet 1.25 (browser-side parquet reading)
- @aws-sdk/client-athena (Athena queries)

### Pipeline (`pipeline/`)
- Python 3, pandas, pyarrow, boto3, requests, numpy
- Runs on EC2 via cron (15th of month, 6 AM)

### Backend (`backend/`)
- FastAPI + Uvicorn, SQLAlchemy 2.0 (async, asyncpg)
- PostgreSQL on RDS (us-east-2)
- LightGBM, statsmodels, scikit-learn, SHAP
- Alembic for migrations

## Directory map

```
Agricultural_Data_Analysis/
├── CLAUDE.md                    # Living project log (load-into-Claude-Code)
├── README.md                    # Public overview
├── NEXT_PHASE.md                # Phase 3/4 roadmap
├── docs/
│   ├── PROJECT_CONTEXT.md       # THIS FILE
│   └── Cloud_Architecture_Summary.docx
├── web_app/                     # Next.js frontend (69 source files post-rebuild)
│   └── src/
│       ├── app/(tabs)/          # 6 URL-routed tabs
│       │   ├── overview/
│       │   ├── market/
│       │   ├── crops/
│       │   ├── forecasts/
│       │   ├── land-economy/
│       │   ├── livestock/
│       │   └── api/
│       │       ├── data/route.ts       # Parquet proxy (S3 or local)
│       │       └── athena/route.ts     # Athena query endpoint
│       ├── components/
│       │   ├── shell/                  # header, filter rail, footer
│       │   ├── shared/                 # BandShell, etc.
│       │   ├── maps/
│       │   ├── overview/
│       │   ├── market/
│       │   ├── crops/
│       │   ├── forecasts/
│       │   ├── land-economy/
│       │   ├── livestock/
│       │   └── aquifer/                # Ogallala / Aquifer Watch tab
│       ├── hooks/
│       │   ├── useFilters.ts           # URL-as-state-of-truth
│       │   ├── useAgSeason.ts
│       │   ├── useAthenaQuery.ts
│       │   ├── usePriceForecast.ts
│       │   ├── useAcreageForecast.ts
│       │   └── useYieldForecast.ts
│       ├── types/agricultural-data.ts
│       └── utils/
│           ├── design.ts               # Design tokens (palette, chart colors)
│           ├── processData.ts          # Data transformations
│           └── serviceData.ts          # S3/local data fetching
├── pipeline/
│   ├── quickstats_ingest.py            # Main USDA ingest (~776 lines)
│   ├── upload_to_s3.py                 # Dual-layout S3 upload, --layout {state,county}
│   ├── validate_data.py
│   ├── incremental_check.py
│   ├── fill_county_gaps.py             # Coverage gap-filler
│   ├── _county_coverage_audit.py
│   ├── county_coverage_allowlist.json  # 70 PENDING_PUBLICATION entries
│   ├── cron_runner.sh                  # EC2 orchestrator (multi-mode)
│   ├── enrichments/                    # 5 enrichment ingests (precip, irrigated, IWMS, ERS, EIA)
│   └── requirements.txt
├── backend/
│   ├── main.py                         # App entry, CORS, lifespan model loading
│   ├── config.py                       # pydantic-settings
│   ├── database.py                     # SQLAlchemy async
│   ├── alembic/                        # migrations through 012 (agent tables)
│   ├── routers/
│   │   ├── price.py
│   │   ├── acreage.py
│   │   ├── yield_forecast.py
│   │   └── agent.py                    # /api/v1/agent/* (runs, promote, draft auth, spec)
│   ├── agent/                          # Module 05 FieldPulse Weekly analyst agent
│   │   ├── runner.py                   # Orchestrates the 8-step pipeline
│   │   ├── signal_board.py             # Deterministic 10-source signal scan
│   │   ├── researcher.py               # Sonnet + 5 SQL-guarded tools
│   │   ├── factcheck.py                # Tokenizer + Haiku critique
│   │   ├── reviser.py                  # Corrective check -> revise -> re-check loop
│   │   ├── composer.py                 # Markdown -> typed IssueSpec (1 design call)
│   │   ├── issue_spec.py               # Pydantic IssueSpec contract
│   │   ├── publisher.py                # S3 + RDS + Slack + magic-link tokens
│   │   └── prompts/                    # System prompts per step
│   ├── etl/                            # Ingestion scripts
│   ├── features/                       # Feature engineering per module
│   ├── models/
│   │   ├── price_model.py
│   │   ├── acreage_model.py
│   │   ├── yield_model.py
│   │   ├── train.py                    # Price training
│   │   ├── train_acreage.py
│   │   ├── train_yield.py
│   │   ├── inference.py                # Price inference CLI
│   │   ├── acreage_inference.py
│   │   ├── yield_inference.py
│   │   ├── _signing.py                 # HMAC-SHA256 pickle signing
│   │   ├── db_tables.py                # ORM
│   │   └── schemas.py                  # Pydantic
│   ├── artifacts/                      # Trained pickles + metrics.json
│   └── ag-prediction.service           # systemd unit
└── research/                           # Tech specs + analysis reports
    ├── commodity-price-tech-spec.md
    ├── crop-yield-tech-spec.md
    ├── planted-acreage-tech-spec.md
    ├── acreage-tier1-features-spec.md
    ├── analyst-agent-tech-spec.md
    ├── county-coverage-analysis-2026-04-17.md
    └── county-coverage-analysis-2026-04-19.md
```

## Production stack and access

| Service | Endpoint / ID | Notes |
|---|---|---|
| Frontend | `agricultural-data-analysis.vercel.app` | Vercel project `prj_pS39ei56Z3oIIYN8CCilQsh8mKe0`, team `team_cYafgMDSu0PaJpyR7SuLlRCp` |
| Backend API | `https://agri-intel.rvedire.com` | EC2 i-05846d4343400eadc, nginx + certbot, proxies uvicorn :8000 |
| Database | `ag-dashboard.cvuu6ce8odqc.us-east-2.rds.amazonaws.com` | RDS Postgres, db `ag_dashboard`, user `ag_app`, publicly accessible (IP whitelist) |
| S3 | `usda-analysis-datasets` (us-east-2) | Parquet files + model artifacts |
| EC2 IP | `18.217.181.187` | SG `sg-0e90c29a7a1c531da`, ports 22/80/443/8000 |
| SNS | `arn:aws:sns:us-east-2:294733692749:usda-pipeline-alerts` | Pipeline failure alerts |

### EC2 access

- SSH key: `usda_dataset_kv_pair.pem` (project root, IP-restricted)
- EC2 Instance Connect available: push key via AWS CLI then SSH within 60s
- User: `ubuntu` (NOT ec2-user)
- Venv: `/home/ubuntu/Agricultural_Data_Analysis/backend/venv/`
- Systemd: `ag-prediction.service`
- Deploy: `cd ~/Agricultural_Data_Analysis && git stash && git pull origin main && sudo systemctl restart ag-prediction`
- **Pull gotcha (2026-04-24):** `git stash` does not cover untracked files. If training created new artifacts (e.g. `backend/artifacts/yield/{crop}/summary.json`) and those paths also changed upstream, `git pull` aborts with "untracked working tree files would be overwritten". Fix: `mv` the conflicting files to `/tmp/` before pulling, or add them to `.gitignore`.

### DNS (rvedire.com via Cloudflare since 2026-04-21)

- Nameservers: `karl.ns.cloudflare.com`, `brenna.ns.cloudflare.com` (migrated from Squarespace; `agri-intel` A record had to be re-added manually after the move).
- `agri-intel.rvedire.com` A to `18.217.181.187`, **DNS only / gray cloud** (preserves Let's Encrypt cert path on EC2).
- `www.rvedire.com` CNAME to Vercel DNS (personal site).
- SSL cert auto-renews via certbot timer, expires 2026-07-15.

## Environment variables

```bash
# Existing (in .env, present locally + on EC2)
QUICKSTATS_API_KEY=...     # USDA QuickStats API
NOAA_API_KEY=...           # NOAA weather data
NASDAQ_DL_API_KEY=...      # Deprecated (CHRIS/CME retired); switched to Yahoo Finance
FRED_API_KEY=...           # FRED API (DXY index)
DATABASE_URL=postgresql+asyncpg://ag_app:PASSWORD@ag-dashboard.cvuu6ce8odqc.us-east-2.rds.amazonaws.com:5432/ag_dashboard

# Frontend (in Vercel project settings, baked at build)
NEXT_PUBLIC_PREDICTION_API_URL=https://agri-intel.rvedire.com

# Optional pickle signing
MODEL_SIGNING_KEY=<hmac-secret>
MODEL_REQUIRE_SIGNED=1     # Refuse unverified loads at startup

# Module 05 FieldPulse agent
ANTHROPIC_API_KEY=...               # LLM pipeline (Sonnet 4.6 + Haiku 4.5)
FIELDPULSE_DRAFT_SECRET=...         # Shared secret gating /api/v1/agent promote + reject
AGENT_TRUST_STREAK_REQUIRED=6       # Approved runs before auto-publish flips on
# Slack webhook / signing for draft pings also configured on EC2
```

## Data flow

1. **Pipeline** fetches from USDA QuickStats API monthly (15th, 6 AM ET).
2. Data cleaned, partitioned by state into parquet files.
3. Uploaded to S3 in two layouts: browser-friendly (`partitioned_states/`) + Athena-optimized (`athena_optimized/`). County layout uses `partitioned_states_counties/` + `athena_optimized_counties/`.
4. **Frontend** reads parquet directly from S3 (or via API proxy fallback).
5. **Athena** available for complex SQL queries over the same S3 data.
6. **Prediction modules** read training inputs from RDS, write forecasts back to RDS, and load pickled models from S3 at API startup.

## Module ledger

### Module 01: Dashboard (foundation)

NASS QuickStats ingestion + multi-tab dashboard. State and county data partitioned by state into parquet, served from S3. ~1.93M county rows + state-level data covering 11 (now 12 with WHEAT) commodities × 4 stat categories × 25 years.

**County data (2026-04-09 milestone, 2026-04-19 fill):** 870,995 to 1,932,343 county rows after the gap-filler ran. WHEAT went from 0 to 418,424 rows. See "Pipeline operations" below.

### Module 02: Commodity Price Forecasting

**Spec:** `research/commodity-price-tech-spec.md`. **Status:** complete, all 9 steps shipped.

3 commodities (corn, soybean, wheat) × 6 horizons (1 to 6 months) = 18 ensembles. Each is `PriceEnsemble` (SARIMAX + LightGBM point + LightGBM quantile + Ridge meta-learner + IsotonicRegression calibrator). SHAP TreeExplainer drives the "key drivers" callout. Mahalanobis regime detection with regularized covariance. Calibrated probability via normal CDF + isotonic. Divergence flag fires when model deviates >5% from futures.

**Features (18):** market (futures spot/deferred, basis, term spread, OI change), fundamental (stocks-to-use, percentile, WASDE surprise, world STU), macro (DXY, DXY 30d change), cost (production cost/bu, price/cost ratio), interaction (corn/soy ratio), seasonal (prior-year price, seasonal factor). Pandera schema validation. MVP skips drought/CCI.

**Training:** walk-forward, 2010-2019 train / 2020-2022 val / 2023-2024 test. Futures-baseline MAPE gate (model must beat futures by 1.5pp). Pickled to `backend/artifacts/{commodity}/horizon_{N}/ensemble.pkl`, S3 to `models/price/`. Gate fail blocks S3 upload (override `--allow-failed-gate`).

**Endpoints:** `GET /api/v1/predict/price/`, `/probability`, `/wasde-signal`, `/history`. CQR calibration fixed in 2026-04-16 hardening pass (val set now split 50/50 for calibration vs measurement).

### Module 03: Planted Acreage Prediction

**Spec:** `research/planted-acreage-tech-spec.md`. **Status:** corn / soybean / wheat_winter publishable. wheat_spring close but fails baseline.

State-panel `AcreageEnsemble` per commodity (Ridge + LightGBM point + LightGBM quantile p10/p90, simple average meta). Soft-cap competition constraint enforces total cropland <= state limit. National rollup uses correlated uncertainty propagation (z=1.2816 for 80% interval, fixed in 2026-04-16 hardening).

**Tier 1 features added 2026-04-11 (15 to 23 features):** drought (DSCI nov, fall avg), insurance (RMA insured acres + YoY), CRP (expiring acres, % cropland), exports (FAS outstanding %, pace vs 5yr). 4 new tables (`drought_index`, `rma_insured_acres`, `crp_enrollment`, `export_commitments`).

**Final test MAPE (mixed config, 2026-04-11):**

| Model | Config | Val | Test | Baseline | Gate |
|---|---|---:|---:|---:|---|
| corn | absolute | 8.37% | 6.26% | 6.24% | borderline pass |
| soybean | 3yr residual | 5.39% | 4.64% | 5.42% | pass both gates |
| wheat_winter | 3yr residual | 5.91% | 4.51% | 4.62% | test pass |
| wheat_spring | 3yr residual | 9.94% | 4.92% | 4.17% | test fail |

**Walk-forward persistence (2026-04-14, §7.4):** `acreage_accuracy` table populated with 796 rows. NASS Prospective Plantings + June Actual ingested via `etl/ingest_prospective_plantings.py` (filtering on `reference_period_desc` "MAR ACREAGE" / "JUN ACREAGE"). Frontend reads via national rollup (`state_fips = '00'`).

**Endpoints:** `GET /api/v1/predict/acreage/`, `/states`, `/accuracy`, `/price-ratio`. Acreage response field renamed `forecast_acres_millions` to `forecast_acres` in 2026-04-16 (was always raw acres; suffix was misleading). Frontend dropped `* 1e6` multiplications.

### Module 04: Crop Yield Forecasting

**Spec:** `research/crop-yield-tech-spec.md`. **Status:** all 8 steps shipped, retrained 2026-04-21 against post-county-fill dataset.

3 crops × 20 weeks = 60 LightGBM quantile models (p10/p50/p90). Confidence tiers: weeks <8 low, 8-15 medium, >=16 high. Baselines: county historical mean, prior year. Walk-forward 2000-2019 / 2020-2022 / 2023-2024.

**Features (7):** `gdd_ytd`, `cci_cumul`, `precip_deficit`, `vpd_stress_days`, `drought_d3d4_pct`, `soil_awc`, `soil_drain`. Strict temporal integrity (no lookahead). State-specific planting dates. Hardening pass (2026-04-16) fixed `yield_inference.py` so weather features actually load (was zero-filling silently).

**Yield artifacts (model_ver: 2026-04-21):**

| Crop | Avg val RRMSE | Avg test RRMSE | Baseline | Gate | Weeks pass |
|---|---:|---:|---:|---|---:|
| corn | 14.81% | 17.97% | 23.78% | pass | 20/20 |
| soybean | 17.80% | 17.89% | 23.15% | pass | 20/20 |
| wheat | 21.00% | 25.51% | 21.80% | fail | 0/20 |

Wheat gate failure surfaces with EXPERIMENTAL annotation per the surface-with-annotation policy (yield is a class-project demo, not product-grade like price/acreage). `GET /api/v1/predict/yield/metadata?crop=X` exposes `gate_status` for the frontend banner.

**Walk-forward persistence (§7.4):** `yield_accuracy` table populated with 290,441 rows (corn 124,961 + soybean 86,020 + wheat 79,460). Test RRMSE per crop-week:

| Crop | Range | Baseline | Pass |
|---|---|---:|---|
| corn | 17.44% to 18.51% | 23.78% | all weeks |
| soybean | 17.29% to 17.76% | 23.15% | all weeks |
| wheat | 23.42% to 25.00% | 21.80% | none (hidden) |

**Interval coverage observation:** models under-cover their 80% prediction intervals (corn val 0.688 / test 0.636, soybean val 0.466 / test 0.541, wheat val 0.631 / test 0.427; target 0.80). Conformal q80 quantile applied too tightly, val set possibly too small relative to county variance. Calibration pass deferred.

**Yield inference architecture (Path B):** training and inference both read the same local parquet `backend/etl/data/ghcn_processed/county_weather_2000_2025.parquet` (68 MB, 16M rows, 2000-2025 daily TMAX/TMIN/PRCP by county). The "intended" RDS weather tables (`noaa_daily`, `nasa_power_daily`, `prism_normals`, `crop_conditions`, `station_county_map`, `county_centroids`) were never migrated; migration 003 only created `soil_features`, `feature_weekly`, `yield_forecasts`. ETL scripts (`ingest_noaa.py` etc.) write CSVs to S3, not rows to RDS. `feature_weekly` stays empty; both training and inference compute features in-memory and discard them. `yield_inference.py` imports `load_weather_data` and `compute_weather_features` from `train_yield.py`.

**Yield forecasts state (2026-04-24):** populated for 2024 + 2025, all 3 crops, weeks 1-20. Row counts: corn 36K, soybean 30K, wheat 32K. Total ~99K. 2026 empty (off-season; live cron kicks in May 22). Per-combo skips: ~150 counties lack >=3 prior years of yield, ~1,000+ lack weather data. Net ~750-920 counties with forecasts per (crop, year).

**Endpoints:** `GET /api/v1/predict/yield/`, `/map`, `/history`, `/metadata`, `/accuracy`.

**Resolved 2026-05-06:** the single-county yield endpoint is now week-aware. `routers/yield_forecast.py::get_yield_forecast` accepts `week: int | None = Query(None)` and filters `yield_forecasts` to that exact week before the latest-week fallback, so the forecasts-tab slider and county card stay in sync. (Was a cosmetic known-limitation in the 2026-04-27 doc.)

### Module 05: FieldPulse Weekly Analyst Agent

**Spec:** `research/analyst-agent-tech-spec.md` (v0.3). **Status:** live in production, cron Sun 17:00 CT (= 18:00 ET). First scheduled runs validated; the project's flagship "agent" deliverable.

A weekly AI analyst that scans the data warehouse for anomalies, researches the interesting ones, writes a newsletter, fact-checks itself, and publishes to `/insights`. Deterministic where it can be, LLM where it must be.

**Pipeline (8 steps):** `signal_board` (deterministic, 10 anomaly-driven sources: yield, acreage, price, WASDE, weather, exports, trend-break, calendar, plus composites and feature/explainer signals) -> `mood` (Sonnet 4.6, JSON) -> `editor` (Sonnet 4.6, JSON) -> `researcher` (Sonnet 4.6 + 5 SQL-guarded tools, 30-call cap) -> `writer` (Sonnet 4.6) -> `fact-checker` (deterministic tokenizer + Haiku 4.5 critique) -> **reviser** (bounded check -> revise -> re-check, max 2 passes) -> **composer** (deterministic prose conversion + 1 Sonnet design call -> typed `IssueSpec`) -> `publisher` (S3 + RDS + Slack + magic-link tokens). ~$0.50 per run.

**SQL guard (§7.1):** every researcher tool takes a runtime-injected `as_of_date` the LLM cannot override; the SQL tool rejects DML/DDL and unknown tables via sqlglot AST traversal and injects `<col> <= :as_of` predicates per allowlisted table. Point-in-time correctness by construction.

**Composer + IssueSpec (2026-06-12):** prose is **never** touched by an LLM in the composer step. `composer.py::parse_markdown_blocks` is a Python port of the frontend `IssueRenderer.tsx` parsing so spec prose is byte-identical to the fact-checked markdown; the design call only emits rich blocks (one KPI strip, stat callouts, figures whose chart data is copied from the researcher's chart specs). A numeric guard re-verifies every number in rich blocks against the dossier (factcheck tokenizer + scale tolerance + derivation check); ungroundable blocks are dropped, not revised. Degradation chain: composer/designer failure or zero surviving figures -> `spec=None` -> markdown+PNG publish. Contract mirrored in `backend/agent/issue_spec.py` (pydantic) and `web_app/src/components/insights/model/types.ts`. Reference issue at `/insights/model`.

**Trust period:** auto-publish flips on after 6 consecutive `approved` runs with no `failed_at_step` (`AGENT_TRUST_STREAK_REQUIRED`). Until then every Sunday's draft sits in `newsletters/draft/<slug>/` awaiting Slack-pinged approval. `agent_settings` singleton seeds `force_manual=true` as a kill switch.

**DB (alembic 012):** 5 tables, `agent_runs`, `agent_picks`, `agent_mood`, `agent_settings`, `agent_draft_tokens` (one-shot magic-link tokens).

**Endpoints:** `https://agri-intel.rvedire.com/api/v1/agent/*`: `/runs`, `/promote/{id}`, `/reject/{id}`, `/draft/{slug}/auth`, `/markdown/{slug}`, `/chart/{slug}/{name}`, `/spec/{slug}`. Promote + reject gated by `FIELDPULSE_DRAFT_SECRET`.

**Frontend:** `/insights` (public list), `/insights/{slug}` (reader), `/insights/draft/{slug}` (gated reader with Approve/Reject). Renders `ModelIssue` (live Recharts) when a spec exists, falls back to `IssueRenderer` (markdown) otherwise. Signed-cookie auth via one-shot magic-link tokens posted to Slack.

**Known gaps (non-blocking):** `acreage_accuracy` history is only 5 years deep so state-trend signals show 4-year windows instead of the intended 25-year arcs; calibration weights too imbalanced for a useful AUC fit (running on `DEFAULT_WEIGHTS`); `agent_reader_role.sql` defense-in-depth Postgres role not yet applied to RDS (the sqlglot guard is the actual enforcement).

## Pipeline operations

### County data ingestion

Optimized 2026-04-09: batched stat_cats (4x fewer API calls), expanded skip states, 8 workers @ 1.5s delay, `--resume` flag for interrupted runs. 870,995 county records, 48 states, 2001-2025, 11 commodities × 4 stat categories at the time. Output: `pipeline/output/*.parquet` (18 MB).

### County coverage gap-filler

`pipeline/fill_county_gaps.py` is the canonical tool for closing NASS county-coverage gaps. Workflow: baseline audit (`pipeline/_county_coverage_audit.py`), compute gap set (ideal `MAJOR_PRODUCERS - COUNTY_SKIP_STATES × years` minus allowlist), per-state sequential subprocess to `quickstats_ingest.py --county-only --resume --states <ST>` (atomic per-state commits for throttle resilience), re-audit, classify residuals (NOT_GROWN / NASS_SUPPRESSION / PENDING_PUBLICATION / UNCLASSIFIED), persist. Always resume-by-default; no `--resume` flag on the wrapper itself. Flags: `--states`, `--max-rounds`, `--min-delta`, `--dry-run`.

**2026-04-19 fill result:**

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| County rows | 870,995 | 1,932,343 | +1.06M (+122%) |
| (state, commodity) pairs | 241 | 277 | +36 |
| (state, commodity, year) triples | 2,470 | 4,748 | +2,278 |
| 4/4 stat-complete pairs | 166 | 201 | +35 |
| Counties | 3,101 | 3,105 | +4 |

Per-commodity row deltas: WHEAT 0 to 418,424; HAY +184K; CORN +166K; SOYBEANS +104K; SORGHUM +48K; COTTON +46K; OATS +44K; BARLEY +26K; SUNFLOWER +17K; RICE +6K. 1,192 of 1,764 original gap triples closed (68%). Residual 572 persisted (structural / unreleased / classifier-blind).

**Treat `pipeline/county_coverage_allowlist.json` as authoritative** for "known structural gaps". 70 PENDING_PUBLICATION entries auto-prune on next run. The 572 UNCLASSIFIED residuals can be properly labeled with a one-time state-level NASS pull.

### S3 upload (2026-04-21)

`pipeline/upload_to_s3.py` now takes `--layout {state,county}`. Layout-specific prefixes: state writes to `partitioned_states/` + `athena_optimized/`, county writes to `partitioned_states_counties/` + `athena_optimized_counties/`. Manifest stamp only fires on clean STATE uploads, so county-only uploads cannot falsely promote `uploaded_record_counts` and block the next state ingest. 96 county files uploaded with backups, 0 failed.

### Cron schedule (EC2, TZ=America/Chicago)

| Cadence | Mode | Tasks |
|---|---|---|
| Weekdays 12pm | `--daily` | Futures (yfinance), FRED DXY |
| 12th monthly 2pm | `--monthly-wasde` | WASDE ingest, price inference, restart `ag-prediction` |
| Jan 15 10am | `--annual-ers` | ERS production costs |
| 15th monthly 6am | (NASS) | QuickStats ingest |
| Feb 1 | `--annual-acreage` | Acreage inference |
| quarterly | `--quarterly-fertilizer` | ERS fertilizer prices |
| Thursday 10am | `--weekly-yield` | Yield ETL + inference + restart |
| Thursday 11am | `--weekly-drought` | DSCI ingest (moved off 10am to avoid yield collision) |
| weekly | `--weekly-exports` | FAS export commitments |
| annual | `--annual-rma` | RMA Summary of Business |
| annual | `--annual-crp` | FSA CRP enrollment + expirations |
| Sunday 5pm CT | `--weekly-fieldpulse` | Module 05 analyst agent (full mood/editor/researcher/writer/factcheck/revise/compose/publish) |

Per-mode `flock` re-exec guard (non-blocking) added in 2026-04-16 hardening pass. **Note (2026-06-11):** `cron_runner.sh` must keep its executable bit (mode `100755`); it was committed non-executable and every cron invocation hit "Permission denied" until restored in `f0b4a5a`. See [Service restorations].

### 5 enrichment ingests (ported from Aquifer Watch, 2026-04-21)

In `pipeline/enrichments/`:

- `noaa_climdiv_county_precip.py`: nationwide NCEI climdiv parquet, 3,137 counties, 1895-2025. Output `enrichment/county_precip.parquet` on S3.
- `nass_irrigated_county.py`: NASS Census 2017+2022 irrigated acres by (fips, crop). 252 counties. Output `enrichment/nass_irrigated_county.parquet` on S3.
- `iwms_water.py`: state × crop water-applied per acre (155 rows). Writes parquet + JSON.
- `ers_revenue.py`: national $/acre gross revenue per commodity. Writes JSON.
- `eia_prices.py`: state-level industrial ¢/kWh. 51 states, 2024 static fallback.
- Small outputs (IWMS, ERS, EIA) land in `web_app/public/enrichments/` for direct static fetch.

### Pipeline hardening (2026-04-16)

- `upload_to_s3.py`: multipart verification now uses `ChecksumAlgorithm=SHA256` + ContentLength match; per-file failures aggregated. Was silently skipping MD5+ETag for files >8MB.
- `quickstats_ingest.py` + `upload_to_s3.py` + `incremental_check.py`: `record_counts` is now promoted to `uploaded_record_counts` only after a clean S3 upload. Was permanently suppressing re-ingestion on a failed upload.
- `validate_data.py`: content checks now run across top-10 states by row count, not one arbitrary state.
- `fetch_nass_historical.py`: yield-only rows retained (was dropping 15-20% of training matrix via `dropna(subset=['acres_planted'])`).

## Frontend

### FieldPulse design system v1

File: `web_app/docs/design-system-v1.html`. Confirmed April 2026.

**Key decisions:**
- **Product name:** FieldPulse (not "QuickStats Analytics")
- **Theme:** Light-first, dark-ready (both full citizens). NOT dark-by-default.
- **Primary user:** Farmers / producers. Analysts secondary. Discoverers tertiary.
- **Inspiration:** Farming Simulator 2025 planning layer (crop profitability, market signals, field comparisons). NOT Bloomberg or Grafana.
- **Fonts:** Plus Jakarta Sans (body), Barlow Condensed (hero numbers), JetBrains Mono (data/metadata).
- **Palette:** Field Green (#2D6A4F), Harvest Gold (#B8860B), Soil (#A0522D), Sky (#2B6CB0), Barn Red (#B42318).
- **Background:** Warm off-white #FAF8F4, not cold gray.
- **Choropleth:** Sandy beige to deep green (agricultural), not blue to teal.
- **Hero view:** Market Outlook (Predictions), not Overview. "When should I sell?" comes first.
- **Hero component:** Forecast Card (P50 price + confidence range + WASDE driver).
- **Strategy component:** Comparison Row ("corn vs soybeans $/acre" with winner badge).
- **Voice:** Farmer vocabulary (bu/acre, $/bu, planting window). Direct, not passive. Not patronizing.
- **Tab order:** Market > Crops > Overview > Economics > More (Animals, Land, Labor).

### Frontend rebuild v1 (2026-04-15)

69 source files, 6 URL-routed tabs, light-first design system with dark mode toggle. Rebuilt from a 656-line single-page monolith with hardcoded dark hex colors, no URL routing, and Inter-only fonts.

**Architecture:**
- Next.js 16 App Router with `(tabs)` route group.
- URL is source of truth for all filter state via `useFilters()` hook.
- `useAgSeason()` drives seasonal UI behavior (dormant panels, rotating story cards).
- `BandShell` wrapper handles loading / error / empty / seasonal visibility for every band.
- CSS custom properties for all design tokens (`:root` light, `[data-theme='dark']` dark).
- Component structure: `shell/` (header, filter rail, footer), `shared/` (reusable), `maps/`, then per-page folders.

### Frontend Spec v1 + Accuracy Pipeline (§7.4)

**Spec:** `web_app/docs/frontend-spec-v1.md`, paired with `design-system-v1.html`. 6 tabs, per-page specs, cross-cutting systems, seasonal behavior, narrative formation.

**Accuracy tables:** wired walk-forward test predictions to the Forecasts tab accuracy panel (§5.3.D).

| Table | Rows | Source |
|---|---:|---|
| `acreage_accuracy` | 796 | `train_acreage.py --persist-accuracy` + `ingest_prospective_plantings.py --api` |
| `yield_accuracy` | 290,441 | `train_yield.py --persist-accuracy` |

Frontend contract:
- Acreage: `SELECT forecast_year, commodity, model_vs_usda_pct, model_vs_actual_pct FROM acreage_accuracy WHERE state_fips = '00'`
- Yield: `SELECT crop, week, forecast_year, AVG(pct_error), AVG(in_interval) FROM yield_accuracy GROUP BY crop, week, forecast_year`

### Crops tab redesign (2026-04-21)

Inverted-L layout with click-to-drill choropleth. New components in `web_app/src/components/crops/`:

- `CropsStateMap.tsx`: SVG choropleth, all 50 states' counties from `/us-counties.geojson`. Yield-anomaly-vs-state-median color ramp, clamped ±30%. Click calls back with FIPS.
- `CropsCountyDrill.tsx`: status pills (rank of N, anomaly %), 3 KPIs, growing-season precipitation block from NOAA nClimDiv (30-yr normal / recent / anomaly %).
- `CropsPeers.tsx`: mode-aware. Top-5 / weakest-3 in state mode, 6 nearest-yield peers in county mode.

Layout uses float-based inverted L (not grid). Map floats left at 30%, panel is a BFC (`flow-root`) to pack right, peers clears left for full-width wrap, method band clears both. `720px` breakpoint collapses to single column. `globals.css:308-358`.

Verified end-to-end with Indiana corn 2024: state KPIs (198 bu/ac, 5.2M ac, $4.3B sales), 92 counties rendered (72 with reported yield), Gibson County drill shows real NOAA precip (1223 mm/yr normal, 1238 recent, +1.3% anomaly).

**3 P0 data bugs fixed in this pass:**
- `processData.ts::filterData` now drops `YEAR - *` reference_period variants and includes `reference_period_desc + class_desc + prodn/util practice + short_desc` in the SURVEY/CENSUS dedup key. Indiana corn 2024 planted acres: 31.0M to 5.2M.
- `getCommodityStory` switched from `sum` to `max` with unit gates. Biotech-PCT sub-rows can no longer contaminate acre totals. Harvest efficiency chart peaks 300% to max 100%.
- `YieldTrendChart` percentile ordinal computed client-side (96th, 91st, 22nd with proper 11/12/13 special case). Fixed "—th percentile" rendering bug.
- `crops/page.tsx` 5-year baseline now skips zero-yield years so Census-year SURVEY gaps don't drag the baseline down ~20%.

### County yield map: state filter + week slider (2026-04-26, commit `ca05f9c`)

`CountyYieldForecast.tsx` gained a state dropdown + week slider. `YieldChoroplethMap.tsx` accepts `selectedState` (dims out-of-state counties to 0.35 fill-opacity) and `onStateClick` (clicking gray no-data counties filters to that state). New `StateYieldCard.tsx` is the right-panel state aggregate (county count, p50 median/min/max, mean anomaly). Crop/year change resets all selections. Selecting a county auto-syncs `selectedState` to its prefix.

### Crops tab: specialty crops + grouped dropdown picker (2026-06-12, commit `6344c06`)

The Crops tab was hardcoded to 11 field crops, so states like California (whose output is almonds, grapes, lettuce, strawberries) showed mostly empty cards even though the served state parquet already carried FRUIT & TREE NUTS, VEGETABLES, and HORTICULTURE rows. Root cause was frontend-only: the picker filtered on `AREA PLANTED > 0`, which most specialty crops never report (they use AREA BEARING / PRODUCTION). Frontend only, no pipeline or schema change.

- **`processData.ts::deriveCropOptions()`** builds the picker dynamically from the loaded parquet, grouped Field Crops / Fruits & Nuts / Vegetables (HORTICULTURE excluded as $-sales-only), listing only crops with renderable data in the recent window, ordered by economic weight, with a small denylist for NASS catch-all aggregates ("FIELD CROPS, OTHER", "GRAIN", etc.).
- **`getCommodityStory()`** extended to capture **area bearing** (tree fruits/nuts), **value of production** ($), and a **dominant production unit** (oranges report both TONS and BOXES in the same year; max across both mixed scales).
- **`CommodityPicker.tsx`** renders the grouped path as **one compact dropdown per group** (too many crops for chips); the flat chip path is preserved for the Market tab.
- **`CropHeroRow.tsx`** is now an adaptive card list. Yield (native unit) falls back to Production; Area Planted -> Harvested -> Bearing; Sales -> Value of Production. Empty metrics drop out. Profit/efficiency panels hide for crops without ERS cost data.

Verified in preview: CA oranges (348 BOXES/ACRE + area bearing), grapes (8.5 TONS/ACRE + area bearing + sales), lettuce (CWT/ACRE), and IL corn unchanged (no regression). Specialty crops correctly show no county choropleth / profit / forecast (NASS doesn't survey those at county level and the models are row-crop only). `tsc` + production build clean.

## End-to-end review and hardening (2026-04-16)

Full-project audit produced 20 findings. All non-deferred items fixed in one pass plus two display bugs and a yield retrospective feature. No retraining or schema migrations required.

### ML / backend

- **Training gates enforced.** `train.py` (price) and `train_acreage.py` block S3 upload on gate fail. Override: `--allow-failed-gate`. Yield gate is surface-with-annotation; `summary.json` + `/metadata` endpoint.
- **Yield inference weather fix.** `yield_inference.py` now invokes `compute_weather_features` (was zero-filling silently).
- **CQR calibration fixed** in `price_model.py`. Val set split 50/50 for calibration vs measurement halves. Reported `coverage_90` is from the held-out half (was tautologically >=90%).
- **Acreage national-rollup z-score fixed** (`compute_national_forecast`): stored interval is 80% (z=1.2816), not 90% (z=1.645). State sigma recovery was off by ~22%.
- **Pickle artifact signing.** `_signing.py` provides HMAC-SHA256 sidecar `.sig` files. Set `MODEL_SIGNING_KEY` to enable, `MODEL_REQUIRE_SIGNED=1` to refuse unverified loads. `main.py::_download_from_s3` fetches the matching `.sig`. `train.py::_upload_to_s3` uploads the sig.
- **Async event-loop fix** in `routers/price.py`: `_build_features` wrapped with `asyncio.to_thread`. Was blocking uvicorn on synchronous psycopg2 reads.
- **SQL injection surface reduced** in `acreage_features.py`: `_query_ers_cost(field=...)` and `_query_fertilizer_price(product=...)` gated by frozenset allowlists.

### Frontend

- **Acreage unit rename (breaking schema change).** `forecast_acres_millions` to `forecast_acres`, etc. Frontend dropped four `* 1e6` multiplications.
- **Duplicate state rows fixed.** `routers/acreage.py::get_states_forecast` dedupes on `(state_fips, created_at DESC)`.
- **Yield Season Review component.** `YieldSeasonReview.tsx` shows per-week walk-forward test RRMSE vs baseline, crop tabs, behind a Current/Review toggle. Defaults to Review during off-season (Nov-Apr).
- **Misc P0 bugs:** `useYieldForecast` now fires via `useEffect` (was inert); wheat key reconciliation; `AcreageCard` React-key dedupe; acreage accuracy data piped into cards.

### Deferred (operator decision)

- `.env` rotation: committed values are placeholder-style. Address before public demo.

## Service restorations (post-outage recovery, 2026-06-11/12)

A post-outage recovery pass surfaced three latent failures that had silently prevented core workflows from ever succeeding. All three are fixed and the corresponding services are restored.

### Cron pipeline restored (commit `f0b4a5a`)

`pipeline/cron_runner.sh` had been committed mode `100644` (non-executable), so **every** scheduled cron invocation hit "Permission denied" and exited, meaning none of the daily/weekly/monthly pipelines (market data, WASDE, yield, drought, exports, FieldPulse) ever ran from cron. Fix: set the executable bit so fresh clones/pulls keep it runnable.

### Price inference restored (commit `f0b4a5a`)

`backend/models/inference.py` upserted with `ON CONFLICT (commodity, run_date, horizon_month)`, but the only unique constraint on `price_forecasts` is `uq_price_forecasts` over four columns (`run_date, commodity, horizon_month, model_ver`). Postgres raised `InvalidColumnReference` on every row, so `price_forecasts` stayed empty since the table was created. Never caught because the price ensembles were never deployed to S3/EC2, so inference had no models to insert with. Fix: switch to `ON CONFLICT ON CONSTRAINT uq_price_forecasts`.

### FieldPulse draft-to-approve flow restored (commits `9164226`, `9ecddc1`)

Two months of FieldPulse runs had hard-failed before reaching an approvable draft. Three coupled fixes closed the loop:

- **Reviser corrective loop.** New `backend/agent/reviser.py` + prompt: a corrections editor that takes the draft, the fact-checker's flagged claims, and the dossier, and corrects or drops each bad figure (grounded in dossier numbers only). `runner.py` runs a bounded check -> revise -> re-check loop (max 2 passes).
- **Fact-checker refinement.** `factcheck.py`: fixed a tokenizer scale bug ("6.24 million" was read as 6.24, the scale word matched but never multiplied) and now accepts correctly-derived numbers (a gap, sum, ratio, %-change, or %-of two dossier values) that never appear verbatim in the dossier. Removes a class of false-positive failures no reviser pass could fix.
- **Surface-with-annotation in draft mode.** A residual fact-check failure no longer discards the run; the publisher stages the draft with the issues attached (S3 `factcheck.json` sidecar + Slack flag list) for the human approver. Only the auto-publish path still hard-blocks.
- **Draft magic-link auth wired.** `consumeDraftToken`/`setDraftSession` existed but nothing called them and there was no auth route, so every draft link showed "Draft not authorized". Added `insights/draft/[slug]/auth/route.ts` to redeem the one-shot token and set the signed cookie. The follow-up `9ecddc1` then scoped the `fp_draft_auth` cookie to `/` (was `/insights`) so it also reaches the `/api/insights/{approve,reject}` action routes, which had been returning 401.

## Conventions

- **Dark theme UI:** original palette in `web_app/src/utils/design.ts`. The 2026-04-15 rebuild moved everything to CSS custom properties on `:root` light + `[data-theme='dark']` dark, with FieldPulse tokens.
- **Pipeline patterns:** see `pipeline/quickstats_ingest.py` for error handling, logging, retry logic.
- **API routes:** Next.js App Router pattern (route.ts files).
- **Data format:** Parquet, partitioned by state.
- **Chart library:** Recharts (already in stack; use for all new charts).
- **Em dash policy:** never use em dashes (`—`) in any user-facing text. Use commas, periods, parentheses, or sentence restructure. En dashes (`–`) for numeric ranges (e.g., "2019–2023") are fine. See [Collaboration preferences].

## Collaboration preferences

### No em dashes in any user-facing text

Never use em dashes (`—`) in docs, articles, captions, UI strings, commit messages, PR descriptions, walkthrough scripts, or anything Raj or his audience will read. Substitute with comma, period, colon, parentheses, or sentence restructure. Run a final pass on any new doc before delivering, especially generated Markdown or HTML. En dashes (`–`) for numeric ranges are fine; only em dash (`—`) is blocked. Avoid faux-substitutes like `--` that read as dashes.

### Model gate policy: surface with annotation, do not block (yield only)

For the **yield** module, when a model fails its baseline gate, surface it in the dashboard with an explicit performance annotation (EXPERIMENTAL pill, Test MAPE vs Baseline strip) rather than blocking it at the API layer. For **price** and **acreage**, the gate blocks S3 upload (those are product-grade).

**Why:** Yield is a class-project demo, not product. Hiding it would remove the artifact needed for the demo. Annotating preserves honesty without blocking.

**Pattern for new demonstrative modules:** wire a `/metadata` endpoint that exposes gate status so the frontend can render a performance banner. Layout: `artifacts/{module}/{subject}/summary.json` + `GET /{module}/metadata?subject=X`.

## Known limitations and open items

The project is in maintenance mode; everything below is optional cleanup or a deferred polish item, not a blocker.

| Severity | Item | Where |
|---|---|---|
| optional | 572 UNCLASSIFIED triples in `county_coverage_allowlist.json` | `pipeline/_county_coverage_audit.py` |
| optional | Audit script literal still says "11 commodities" (runtime adds WHEAT) | `_county_coverage_audit.py:31`, `:445` |
| deferred | `.env` rotation (placeholder values committed) | `.env` |
| deferred | Yield interval coverage under-shoots 80% target | `train_yield.py` calibration |
| low priority | NASS CENSUS 403 residual: 5 states for irrigated overlay | `enrichments/nass_irrigated_county.py` (rerun at concurrency=2) |
| low priority | IWMS / ERS / EIA enrichments ingested but not yet bound to UI | Water-productivity KPI is the obvious next hook |
| deferred | Agent `acreage_accuracy` history only 5 years deep (state-trend signals show 4-yr windows vs intended 25-yr arcs) | backfill historical state NASS |
| deferred | Agent calibration weights too imbalanced for a useful AUC fit; running on `DEFAULT_WEIGHTS` | `backend/agent/data/weights.degenerate.json`, relabel signals |
| deferred | Agent reader-role Postgres views (defense-in-depth) not applied to RDS; sqlglot guard is the real enforcement | `backend/agent/sql/agent_reader_role.sql` |
| housekeeping | Crops mockup artifacts safe to delete | `web_app/public/crops-redesign-mockup.html`, `crops-mockup-data.json`, `_compare_state_vs_county.py` |

## Reference docs

| Doc | Path |
|---|---|
| Commodity price spec | `research/commodity-price-tech-spec.md` |
| Crop yield spec | `research/crop-yield-tech-spec.md` |
| Planted acreage spec | `research/planted-acreage-tech-spec.md` |
| Acreage Tier 1 features | `research/acreage-tier1-features-spec.md` |
| Analyst agent spec | `research/analyst-agent-tech-spec.md` |
| County coverage 2026-04-17 | `research/county-coverage-analysis-2026-04-17.md` |
| County coverage 2026-04-19 | `research/county-coverage-analysis-2026-04-19.md` |
| Frontend spec v1 | `web_app/docs/frontend-spec-v1.md` |
| Design system v1 | `web_app/docs/design-system-v1.html` |
| Cloud architecture summary | `docs/Cloud_Architecture_Summary.docx` |
| Yield-forecasting report | `reports/yield-forecasting-report.docx` |
| Devpost article | `research/devpost/article.md` |

## Beyond-spec deliverables (untracked, present locally)

- `presentations/Final_presentation_V2.pptx` + `Speaker_Notes.docx`
- `presentations/fieldpulse-master-slides.pptx`
- `reports/yield-forecasting-report.docx` + builder JS
- `research/devpost/article.{html,md}` + `tech-stack.md`
- `cloud_arch_diagram/` (PNG + draw script)
- `docs/Cloud_Architecture_Summary.docx`
- `research/analyst-agent-tech-spec.md`
- `tools/philosophy.md`

## Cross-project notes (Obsidian)

- `[[Aquifer Watch]]` shares ingestion DNA with this project. The 5 enrichment ingests in `pipeline/enrichments/` were ported from Aquifer Watch (NOAA climdiv, NASS irrigated, IWMS, ERS revenue, EIA prices). Both projects target the same RDS `ag_dashboard` instance? No, separate RDS. Same S3 bucket? Yes (`usda-analysis-datasets`). When making changes to shared enrichment scripts, sync both projects.
- `[[Cobbles & Currents Studios]]` is the umbrella for several portfolio projects including this one. Reports, devpost, and presentation artifacts are produced under that brand.
- The yield-forecasting Word report uses the html-report-templates "Cobbles & Currents" theme.
- Deployment infrastructure (rvedire.com, EC2, RDS) is shared with the personal site. Any DNS or SSL changes here may affect `www.rvedire.com`.

## Reproducible workflows

### Train all models locally and ship to S3

```bash
# Price (gate blocks on fail)
python -m backend.models.train --upload-s3
# Acreage (gate blocks on fail; persist accuracy table)
python -m backend.models.train_acreage --persist-accuracy --upload-s3
# Yield (gate fails surface; persist accuracy table)
python -m backend.models.train_yield --persist-accuracy --upload-s3

# Reload on EC2
ssh ec2-host 'sudo systemctl restart ag-prediction'
```

### Apply DB migrations + repopulate accuracy tables

```bash
alembic upgrade head
python -m backend.models.train_acreage --persist-accuracy --skip-cv --local-only
python -m backend.etl.ingest_prospective_plantings --api --year-start 2021 --year-end 2025
python -m backend.models.train_yield --persist-accuracy --skip-cv --local-only

# Verify
psql $DATABASE_URL -c "SELECT COUNT(*) FROM acreage_accuracy; SELECT COUNT(*) FROM yield_accuracy;"
```

### County coverage gap-fill round

```bash
python -m pipeline.fill_county_gaps --max-rounds 2
python pipeline/upload_to_s3.py --layout county --backup
# Then retrain yield (county data flows into yield features)
python -m backend.models.train_yield --persist-accuracy --upload-s3
ssh ec2-host 'sudo systemctl restart ag-prediction'
```

### Backfill yield forecasts for a year

```python
from backend.models.train_yield import load_weather_data, load_prism_normals, load_nass_county_yields
from backend.models.yield_inference import run_inference

wx = load_weather_data()
pn = load_prism_normals()
nass = {c: load_nass_county_yields(comm, local_only=True)
        for c, comm in [('corn','CORN'),('soybean','SOYBEANS'),('wheat','WHEAT')]}

for crop in ['corn','soybean','wheat']:
    for year in [2024, 2025]:
        for week in range(1, 21):
            run_inference(crop, week, year, nass_yields=nass[crop],
                         weather_df=wx, prism_normals=pn)
```

## Document maintenance

This document is regenerated by hand from `CLAUDE.md` + Claude Code memory files in `~/.claude/projects/.../memory/`. To refresh:

1. Make sure CLAUDE.md is current (committed working tree).
2. Make sure memory files are current (`MEMORY.md` + individual files).
3. Re-run the consolidation in a Claude Code session: "regenerate `docs/PROJECT_CONTEXT.md` from CLAUDE.md and memory."
4. Commit the regenerated doc with a dated message.

The project is in **maintenance mode** as of 2026-06-12; this doc should only need light updates from here (operational fixes, deferred-item cleanup), not new module sections.

Last regeneration: 2026-04-27 from commit `70ea315`. Last refresh: 2026-06-12 from commit `6344c06` (added Module 05 agent + composer, service restorations, Crops specialty crops; marked complete / maintenance mode).
