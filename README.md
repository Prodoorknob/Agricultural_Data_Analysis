# Agricultural Data Analysis

Interactive dashboard for exploring long-term trends in U.S. agriculture using USDA QuickStats data. Built with Next.js and backed by an automated data ingestion pipeline on AWS.

## Architecture

```
┌──────────────────────────────────┐
│  Web App (Next.js + React + TS)  │
│  Recharts · Deck.gl · MapLibre   │
└──────────────┬───────────────────┘
               │
         S3 (primary) → Local API (fallback)
               │
┌──────────────┴───────────────────┐
│  Data Pipeline (AWS EC2 + Cron)  │
│  USDA API → Parquet → S3 Upload  │
└──────────────────────────────────┘
```

## Repository Structure

```
Agricultural_Data_Analysis/
├── web_app/                  # Next.js web application
│   ├── src/
│   │   ├── app/              # Pages and API routes
│   │   ├── components/       # Dashboard components
│   │   ├── hooks/            # Custom React hooks
│   │   ├── types/            # TypeScript definitions
│   │   └── utils/            # Data fetching, processing, design tokens
│   └── public/data/          # Static reference data
├── pipeline/                 # Data ingestion pipeline
│   ├── quickstats_ingest.py  # USDA API ingestion
│   ├── upload_to_s3.py       # S3 upload utility
│   ├── validate_data.py      # Data quality checks
│   ├── incremental_check.py  # Incremental processing
│   ├── cron_runner.sh        # EC2 cron scheduler
│   └── aws_setup.sh          # AWS environment setup
└── .gitignore
```

## Web App

**Stack:** Next.js 16, React 19, TypeScript, Recharts, Deck.gl, MapLibre GL

**Dashboards:**
- Crops — production, yield, and acreage trends
- Land — land use shifts and crop allocation
- Labor — employment, wages, and farm operations
- Animals — livestock inventory and production
- Economics — price, revenue, and market data

**Data layer:** Fetches partitioned Parquet files from S3 with fallback to a local API endpoint. AWS Athena integration available for advanced queries.

### Running locally

```bash
cd web_app
npm install
npm run dev
```

## Data Pipeline

Automated USDA QuickStats ingestion running on an EC2 instance via cron.

**Flow:** USDA API → transform/validate → Parquet (partitioned by state) → S3 upload

**S3 bucket:** `usda-analysis-datasets` (us-east-2)
**Path pattern:** `survey_datasets/partitioned_states/{STATE}.parquet`

### Running manually

```bash
cd pipeline
pip install -r requirements.txt
python quickstats_ingest.py
python upload_to_s3.py
```

## Data

- **Source:** USDA QuickStats
- **Coverage:** All 50 U.S. states, multi-year
- **Granularity:** State and county level
- **Storage:** AWS S3 (partitioned Parquet)
