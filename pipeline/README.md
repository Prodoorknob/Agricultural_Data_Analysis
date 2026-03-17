# Ingestion Pipeline

Automated data ingestion from the USDA QuickStats API, with cleaning, partitioning, and S3 upload.

## Architecture

```
Cron (EC2, monthly on 15th)
  |
  v
incremental_check.py  --> exit 0 (no new data) --> stop
  |
  v (exit 1 = new data)
quickstats_ingest.py  --> pipeline/output/{STATE}.parquet + athena_optimized/
  |
  v
upload_to_s3.py       --> s3://usda-analysis-datasets/survey_datasets/
  |                         partitioned_states/{STATE}.parquet  (browser)
  |                         athena_optimized/state_alpha={STATE}/data.parquet (Athena)
  v
SNS notification      --> email alert on success/failure
```

## Quick Start

### 1. Install dependencies
```bash
cd pipeline
pip install -r requirements.txt
```

### 2. Set your API key
```bash
# Option A: Environment variable
export USDA_QUICKSTATS_API_KEY="your-key-here"

# Option B: AWS SSM (recommended for EC2)
aws ssm put-parameter --name /usda/quickstats-api-key --value "your-key" --type SecureString --region us-east-2
```

### 3. Test with a single state
```bash
python quickstats_ingest.py --states IN --year-start 2023 --year-end 2023
```

### 4. Run full ingestion
```bash
python quickstats_ingest.py
```

### 5. Upload to S3
```bash
# Dry run first
python upload_to_s3.py --dry-run

# Actual upload
python upload_to_s3.py
```

## AWS Infrastructure Setup

Run the setup script to create Glue database, Athena workgroup, SNS topic, and IAM policies:

```bash
chmod +x aws_setup.sh
./aws_setup.sh
```

Then:
1. Store your API key in SSM
2. Attach IAM policies to your EC2 instance role
3. Subscribe to SNS alerts
4. Set up cron: `0 6 15 * * /path/to/pipeline/cron_runner.sh`

## Files

| File | Purpose |
|------|---------|
| `quickstats_ingest.py` | Core ingestion: API -> clean -> partition -> parquet |
| `incremental_check.py` | Check for new data (compare API counts vs manifest) |
| `upload_to_s3.py` | Upload parquet to S3 (both layouts) with backup |
| `cron_runner.sh` | Cron orchestrator: check -> ingest -> upload -> notify |
| `aws_setup.sh` | One-time AWS infrastructure setup |
| `manifest.json` | Tracks last run and record counts |
| `requirements.txt` | Python dependencies |

## Cost

| Component | Monthly |
|-----------|---------|
| EC2 (existing) | $0 |
| S3 storage (~1.5GB) | ~$0.04 |
| QuickStats API | Free |
| SNS | Free tier |
| Athena queries | ~$0.05 |
| **Total** | **~$0.09** |
