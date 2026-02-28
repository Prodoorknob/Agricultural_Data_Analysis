#!/bin/bash
# cron_runner.sh - Orchestration script for USDA QuickStats ingestion pipeline
#
# This script is designed to be run via cron on an EC2 instance.
# Cron entry:  0 6 15 * * /home/ec2-user/Agricultural_Data_Analysis/pipeline/cron_runner.sh
#
# Flow:
#   1. Activate virtual environment
#   2. Run incremental_check.py to detect new data
#   3. If new data found, run quickstats_ingest.py
#   4. Upload results to S3 via upload_to_s3.py
#   5. Send SNS notification on success or failure

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration - Edit these for your EC2 setup
# ---------------------------------------------------------------------------
PIPELINE_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="${PIPELINE_DIR}/../.venv/bin/activate"
LOG_DIR="${PIPELINE_DIR}/logs"
SNS_TOPIC_ARN="arn:aws:sns:us-east-2:294733692749:usda-pipeline-alerts"
AWS_REGION="us-east-2"

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
mkdir -p "${LOG_DIR}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOGFILE="${LOG_DIR}/cron_${TIMESTAMP}.log"

exec > >(tee -a "${LOGFILE}") 2>&1

echo "=============================================="
echo "USDA Pipeline Cron Runner"
echo "Started: $(date)"
echo "=============================================="

# Activate virtual environment if it exists
if [ -f "${VENV_PATH}" ]; then
    source "${VENV_PATH}"
    echo "Activated virtual environment: ${VENV_PATH}"
else
    echo "No virtual environment found at ${VENV_PATH}, using system Python"
fi

cd "${PIPELINE_DIR}"

# ---------------------------------------------------------------------------
# Step 1: Check for new data
# ---------------------------------------------------------------------------
echo ""
echo "Step 1: Checking for new data..."

set +e
python incremental_check.py
CHECK_EXIT=$?
set -e

if [ ${CHECK_EXIT} -eq 0 ]; then
    echo "No new data detected. Exiting."

    # Optional: send "no update needed" notification
    aws sns publish \
        --topic-arn "${SNS_TOPIC_ARN}" \
        --subject "USDA Pipeline: No Update Needed" \
        --message "Incremental check completed at $(date). No new data detected." \
        --region "${AWS_REGION}" 2>/dev/null || true

    exit 0
elif [ ${CHECK_EXIT} -eq 2 ]; then
    echo "Error during incremental check. Sending alert..."

    aws sns publish \
        --topic-arn "${SNS_TOPIC_ARN}" \
        --subject "USDA Pipeline: Check FAILED" \
        --message "Incremental check failed at $(date). See log: ${LOGFILE}" \
        --region "${AWS_REGION}" 2>/dev/null || true

    exit 1
fi

# Exit code 1 means new data detected
echo "New data detected! Proceeding with ingestion..."

# ---------------------------------------------------------------------------
# Step 2: Run full ingestion
# ---------------------------------------------------------------------------
echo ""
echo "Step 2: Running ingestion pipeline..."

set +e
python quickstats_ingest.py
INGEST_EXIT=$?
set -e

if [ ${INGEST_EXIT} -ne 0 ]; then
    echo "Ingestion failed with exit code ${INGEST_EXIT}"

    aws sns publish \
        --topic-arn "${SNS_TOPIC_ARN}" \
        --subject "USDA Pipeline: Ingestion FAILED" \
        --message "Ingestion failed at $(date) with exit code ${INGEST_EXIT}. See log: ${LOGFILE}" \
        --region "${AWS_REGION}" 2>/dev/null || true

    exit 1
fi

echo "Ingestion completed successfully."

# ---------------------------------------------------------------------------
# Step 3: Upload to S3
# ---------------------------------------------------------------------------
echo ""
echo "Step 3: Uploading to S3..."

set +e
python upload_to_s3.py --source-dir "${PIPELINE_DIR}/output"
UPLOAD_EXIT=$?
set -e

if [ ${UPLOAD_EXIT} -ne 0 ]; then
    echo "S3 upload failed with exit code ${UPLOAD_EXIT}"

    aws sns publish \
        --topic-arn "${SNS_TOPIC_ARN}" \
        --subject "USDA Pipeline: Upload FAILED" \
        --message "S3 upload failed at $(date) with exit code ${UPLOAD_EXIT}. Data was ingested but NOT uploaded. See log: ${LOGFILE}" \
        --region "${AWS_REGION}" 2>/dev/null || true

    exit 1
fi

# ---------------------------------------------------------------------------
# Step 4: Success notification
# ---------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "Pipeline completed successfully at $(date)"
echo "=============================================="

aws sns publish \
    --topic-arn "${SNS_TOPIC_ARN}" \
    --subject "USDA Pipeline: SUCCESS" \
    --message "Pipeline completed successfully at $(date). Data has been updated in S3. See log: ${LOGFILE}" \
    --region "${AWS_REGION}" 2>/dev/null || true

exit 0
