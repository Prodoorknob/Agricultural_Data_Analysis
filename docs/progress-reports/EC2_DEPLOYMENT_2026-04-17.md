# EC2 Deployment — 2026-04-17 Session

**Target:** production FastAPI backend at `https://agri-intel.rvedire.com` (EC2 instance, us-east-2).
**Systemd unit:** `ag-prediction.service`.
**Instance user:** `ec2-user`.
**Repo path on EC2:** `/home/ec2-user/Agricultural_Data_Analysis`.
**Venv:** `/home/ec2-user/Agricultural_Data_Analysis/backend/venv`.

## What this deployment covers

- **4 new Alembic migrations** (008 → 011): ERS per-acre cost columns, wider `yield_units` field, new `land_use_categories` table, new `bls_establishments` table.
- **3 new routers** registered in `backend/main.py`: `crops`, `meta`, and an expanded `market` router (adds `/exports`).
- **New shared dependency** `backend/routers/deps.py` used by 14 endpoints.
- **Acreage scale-up multiplier** added to `backend/features/acreage_features.py` and applied in `compute_national_forecast`. Next acreage inference run will produce nationally-scaled forecasts.
- **ERS ingest** now covers 9 commodities and populates per-acre columns.
- **No code changes to the trained model pickles themselves** — corn and soy acreage ensembles were retrained with the restored 15-state panel (same artifact format, same signed pickle path).

Frontend is not deployed by these steps; Vercel ships the rebuilt `web_app/` automatically on `main` push.

---

## Pre-flight

**From your workstation:**

```bash
# Confirm the remote has the new commit
git ls-remote origin main | head -1
# Should show: ce2f4c2 or newer
```

**Optional:** bump CloudFront/CDN cache for the new S3 overview parquets so the frontend picks up the fresh aggregates rather than any stale cache.

```bash
aws s3 ls s3://usda-analysis-datasets/survey_datasets/overview/
# Expect: state_totals.parquet, state_commodity_totals.parquet,
#         land_use.parquet, bls_establishments.parquet,
#         county_metrics/ (50 files)
```

---

## Step 1 — SSH in and pull

```bash
ssh ec2-user@agri-intel.rvedire.com
cd /home/ec2-user/Agricultural_Data_Analysis
git fetch origin
git log HEAD..origin/main --oneline  # preview what's coming
git pull origin main
```

Expected incoming: commit `ce2f4c2 Tab-by-tab audit fixes: pipeline correctness + Overview rewire`.

---

## Step 2 — Activate venv, install any new deps

No new Python packages were added this session (every dep was already in the venv), but run a clean install anyway in case requirements drifted:

```bash
source backend/venv/bin/activate
pip install -r backend/requirements.txt --quiet
# If requirements.txt doesn't exist, at least verify:
python -c "import fastapi, pandas, sqlalchemy, boto3, requests; print('ok')"
```

---

## Step 3 — Run Alembic migrations

Four new migrations, numbered 008 through 011. They are strictly additive (no column drops on existing data). Verify `.env` has `DATABASE_URL` pointing at the prod RDS:

```bash
cd /home/ec2-user/Agricultural_Data_Analysis/backend
grep -c DATABASE_URL ../.env  # should be 1
alembic current  # should report 007 before running
alembic upgrade head
alembic current  # should report 011 after running
```

What each migration does:
- **008** — widen `ers_production_costs.commodity` from `VARCHAR(10)` to `VARCHAR(20)`; add `variable_cost_per_acre`, `total_cost_per_acre`, `yield_units`, `yield_value`.
- **009** — widen `ers_production_costs.yield_units` from `VARCHAR(20)` to `VARCHAR(40)` (ERS phrases like "bushels per planted acre" exceed 20 chars).
- **010** — create `land_use_categories` table (id, state_fips, state_alpha, year, category, acres) with unique constraint on `(state_fips, year, category)`.
- **011** — create `bls_establishments` table (id, state_fips, year, naics, establishments, employment, avg_annual_pay) with unique constraint on `(state_fips, year, naics)`.

If any migration fails, `alembic downgrade -1` returns to the prior state. None of them drop user-facing data.

---

## Step 4 — Load new reference data

The migrations create empty tables for `land_use_categories` and `bls_establishments`. These need to be populated. Both ingest scripts are idempotent (upsert on conflict) and safe to re-run.

```bash
cd /home/ec2-user/Agricultural_Data_Analysis
source backend/venv/bin/activate

# ERS Major Land Uses (downloads 6 xlsx files from ers.usda.gov, ~1.5 MB total)
python -m backend.etl.ingest_ers_mlu
# Expected: "Completed: 4608 rows upserted into land_use_categories"

# BLS QCEW (downloads 22 CSVs from data.bls.gov, ~12 MB total)
python -m backend.etl.ingest_bls_qcew
# Expected: "Completed: 1152 rows upserted into bls_establishments"
#          (pre-2014 years skip gracefully — BLS API coverage starts 2014)

# ERS production costs, now 9 commodities (3 existing + 6 new)
python -m backend.etl.load_ers_costs
# Expected: "Completed: 217 rows upserted into ers_production_costs"
```

If any of these fail on download (ERS occasionally rotates media URLs), check the error message — `load_ers_costs.py` falls back to any cached copy in `backend/etl/data/`. Caches are not committed to git, so the first EC2 run downloads fresh.

---

## Step 5 — Restart the service

```bash
sudo systemctl restart ag-prediction
sudo systemctl status ag-prediction  # should show active (running)
sudo journalctl -u ag-prediction -n 50 --no-pager
# Look for: "Uvicorn running on http://0.0.0.0:8000"
# Look for: "Loaded 18 price forecast models" / "Loaded 4 acreage models"
# Look for: no ImportError from any of the new modules
```

The lifespan hook in `main.py` will attempt to load acreage ensembles. If signed-pickle verification fails (`MODEL_REQUIRE_SIGNED=1` and no sig file found), the service will 503 on acreage endpoints but still start. For this session the two retrained ensembles (corn and soybean) were uploaded to S3 with fresh `.sig` sidecars — verify:

```bash
aws s3 ls s3://usda-analysis-datasets/models/acreage/corn/
# Expect: ensemble.pkl and ensemble.pkl.sig if MODEL_SIGNING_KEY is set
```

If signatures are missing and `MODEL_REQUIRE_SIGNED=1` is set on the server, either (a) set `MODEL_REQUIRE_SIGNED=0` in `.env` temporarily, or (b) re-run local training with `MODEL_SIGNING_KEY` set to generate fresh sidecars.

---

## Step 6 — Smoke test the new endpoints

From any terminal:

```bash
# Wheat export pace — new in this deploy
curl -s 'https://agri-intel.rvedire.com/api/v1/market/exports?commodity=wheat' | python -m json.tool

# Model metadata — new in this deploy
curl -s 'https://agri-intel.rvedire.com/api/v1/meta/models' | python -c "import sys,json;d=json.load(sys.stdin);print('total:',d['summary']['total_models'])"
# Expected: 16

# Crops profit history — new in this deploy
curl -s 'https://agri-intel.rvedire.com/api/v1/crops/profit-history?commodity=rice&state=AR' | python -c "import sys,json;d=json.load(sys.stdin);p=d['points'][-1];print(f'{p[\"year\"]}: profit/acre=\${p[\"profit_per_acre\"]}')"
# Expected: a recent year with a negative profit near -$100 to -$200/acre

# Price ratio — flipped convention (should now be ~2.6, not ~0.38)
curl -s 'https://agri-intel.rvedire.com/api/v1/predict/acreage/price-ratio' | python -c "import sys,json;d=json.load(sys.stdin);print('ratio:',d['corn_soy_ratio'],'zone:',d['implication'])"
# Expected: ratio around 2.5-2.7, implication neutral or corn_favored

# Soybeans plural acceptance — was 422 before, should be 200 now
curl -s -o /dev/null -w '%{http_code}\n' 'https://agri-intel.rvedire.com/api/v1/market/futures?commodity=soybeans&start=2025-01-01'
# Expected: 200
```

---

## Step 7 — Verify frontend cutover

Vercel auto-deploys from `main`. Wait a minute for the build, then:

```bash
# Open the live site
open https://fieldpulse.app  # or whatever the Vercel URL resolves to

# Visit the Overview tab, select Indiana
# Expected hero: Total Farm Sales $14.1B, rank #10, top crop CORN $4.3B
# Map: Indiana counties should render in green shades, with a "back to U.S." pill
```

If the browser still shows old numbers (e.g. $448B), it's a cache issue — hard-reload with Ctrl+Shift+R or bust the S3 CDN.

---

## Rollback plan

If anything goes wrong mid-deploy:

```bash
# On EC2
cd /home/ec2-user/Agricultural_Data_Analysis
git log --oneline -5  # find the previous-known-good commit (should be 24ebfaa)
git checkout 24ebfaa
cd backend && alembic downgrade 007  # rolls back the 4 new migrations
sudo systemctl restart ag-prediction
```

The S3 parquet rebuild is reversible too: originals were copied to `s3://usda-analysis-datasets/survey_datasets/backups/20260417T030112Z_pre_rebuild/` before the overwrite. Restore by copying that prefix back to `survey_datasets/partitioned_states/`:

```bash
aws s3 sync \
  s3://usda-analysis-datasets/survey_datasets/backups/20260417T030112Z_pre_rebuild/ \
  s3://usda-analysis-datasets/survey_datasets/partitioned_states/
```

---

## What is NOT changing in this deploy

- Trained price-forecast models (unchanged artifacts, same `metrics.json`).
- Yield-forecast models (unchanged; gate policy still "surface with annotation").
- `NATIONAL.parquet` schema (only the DERIVED rows got replaced; consumers that never used DERIVED rows are unaffected).
- Cron schedule in `pipeline/cron_runner.sh` (no new cron jobs required this round; the new ingest scripts are annual/one-off, not on the daily/weekly cadence).

If you want to add the new ingest scripts to the cron (ERS MLU annually, BLS QCEW annually in Q2), edit `pipeline/cron_runner.sh` to add `--annual-mlu` and `--annual-qcew` modes. Not required for this deploy — the initial backfill is already done.

---

## After deploy

Cross off these items from `docs/progress-reports/PENDING_FRONTEND_2026-04-17.md`:
- Section 0 ("Infrastructure already in place") — all items should now respond in production.

The remaining pending work in that handoff doc is frontend-only and deploys via Vercel on `main` push, so subsequent tab rewires will not need another EC2 touch unless a new backend endpoint is added.
