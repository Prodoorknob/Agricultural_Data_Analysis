#!/bin/bash
# cron_runner.sh - Orchestration script for USDA data pipelines
#
# This script is designed to be run via cron on an EC2 instance.
#
# Cron entries:
#   0 6 15 * *  /home/ec2-user/Agricultural_Data_Analysis/pipeline/cron_runner.sh              # Monthly NASS
#   0 12 * * 1-5 /home/ec2-user/Agricultural_Data_Analysis/pipeline/cron_runner.sh --daily      # Daily market data
#   0 14 12 * * /home/ec2-user/Agricultural_Data_Analysis/pipeline/cron_runner.sh --monthly-wasde  # Monthly WASDE
#   0 10 15 1 * /home/ec2-user/Agricultural_Data_Analysis/pipeline/cron_runner.sh --annual-ers  # Annual ERS costs
#   0 12 1 2 *  /home/ec2-user/Agricultural_Data_Analysis/pipeline/cron_runner.sh --annual-acreage  # Annual acreage forecast
#   0 12 1 1,4,7,10 * /home/ec2-user/Agricultural_Data_Analysis/pipeline/cron_runner.sh --quarterly-fertilizer  # Quarterly fertilizer prices
#   0 10 * * 4  /home/ec2-user/Agricultural_Data_Analysis/pipeline/cron_runner.sh --weekly-yield   # Weekly yield pipeline (Thursday 10 AM)
#
# Modes:
#   (default)              NASS QuickStats ingestion pipeline
#   --daily                CME futures + FRED DXY daily ingest
#   --monthly-wasde        WASDE supply/demand + price model inference
#   --annual-ers           ERS production costs (January only)
#   --annual-acreage       Acreage model inference + publish (February only)
#   --quarterly-fertilizer ERS fertilizer price update (Jan, Apr, Jul, Oct)
#   --weekly-yield         Yield pipeline: weather/drought ETL + features + inference (Thursdays)
#
# Flow (default mode):
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
PROJECT_ROOT="${PIPELINE_DIR}/.."
BACKEND_DIR="${PROJECT_ROOT}/backend"
VENV_PATH="${PROJECT_ROOT}/.venv/bin/activate"
BACKEND_VENV_PATH="${BACKEND_DIR}/venv/bin/activate"
LOG_DIR="${PIPELINE_DIR}/logs"
SNS_TOPIC_ARN="arn:aws:sns:us-east-2:294733692749:usda-pipeline-alerts"
AWS_REGION="us-east-2"
RUN_MODE="${1:---nass}"  # default to NASS pipeline

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
# Helper: activate backend venv for prediction ETL scripts
# ---------------------------------------------------------------------------
activate_backend_venv() {
    if [ -f "${BACKEND_VENV_PATH}" ]; then
        source "${BACKEND_VENV_PATH}"
        echo "Activated backend virtual environment: ${BACKEND_VENV_PATH}"
    else
        echo "WARNING: Backend venv not found at ${BACKEND_VENV_PATH}"
    fi
}

# ---------------------------------------------------------------------------
# Mode: --daily  (CME futures + FRED DXY)
# ---------------------------------------------------------------------------
if [ "${RUN_MODE}" = "--daily" ]; then
    echo "Running DAILY market data ingest..."
    activate_backend_venv
    cd "${PROJECT_ROOT}"

    set +e
    python -m backend.etl.ingest_futures
    FUTURES_EXIT=$?
    python -m backend.etl.ingest_fred
    FRED_EXIT=$?
    set -e

    if [ ${FUTURES_EXIT} -ne 0 ] || [ ${FRED_EXIT} -ne 0 ]; then
        echo "Daily ETL failed (futures=${FUTURES_EXIT}, fred=${FRED_EXIT})"
        aws sns publish \
            --topic-arn "${SNS_TOPIC_ARN}" \
            --subject "Price ETL: Daily Ingest FAILED" \
            --message "Daily market data ingest failed at $(date). futures_exit=${FUTURES_EXIT}, fred_exit=${FRED_EXIT}. See log: ${LOGFILE}" \
            --region "${AWS_REGION}" 2>/dev/null || true
        exit 1
    fi

    echo "Daily market data ingest completed successfully at $(date)"
    aws sns publish \
        --topic-arn "${SNS_TOPIC_ARN}" \
        --subject "Price ETL: Daily Ingest SUCCESS" \
        --message "Daily futures + DXY ingest completed at $(date)." \
        --region "${AWS_REGION}" 2>/dev/null || true
    exit 0
fi

# ---------------------------------------------------------------------------
# Mode: --monthly-wasde  (WASDE ingest + price model inference)
# ---------------------------------------------------------------------------
if [ "${RUN_MODE}" = "--monthly-wasde" ]; then
    echo "Running MONTHLY WASDE ingest..."
    activate_backend_venv
    cd "${PROJECT_ROOT}"

    set +e
    python -m backend.etl.ingest_wasde
    WASDE_EXIT=$?
    set -e

    if [ ${WASDE_EXIT} -ne 0 ]; then
        echo "WASDE ingest failed with exit code ${WASDE_EXIT}"
        aws sns publish \
            --topic-arn "${SNS_TOPIC_ARN}" \
            --subject "Price ETL: WASDE Ingest FAILED" \
            --message "WASDE ingest failed at $(date) with exit code ${WASDE_EXIT}. See log: ${LOGFILE}" \
            --region "${AWS_REGION}" 2>/dev/null || true
        exit 1
    fi

    # Run price model inference with refreshed WASDE data
    echo "Running price model inference..."
    set +e
    python -m backend.models.inference
    INFERENCE_EXIT=$?
    set -e

    if [ ${INFERENCE_EXIT} -ne 0 ]; then
        echo "WARNING: Inference failed (exit=${INFERENCE_EXIT}), WASDE ingest was successful"
        aws sns publish \
            --topic-arn "${SNS_TOPIC_ARN}" \
            --subject "Price ETL: Inference FAILED (WASDE OK)" \
            --message "WASDE ingest succeeded but inference failed at $(date). exit=${INFERENCE_EXIT}. See log: ${LOGFILE}" \
            --region "${AWS_REGION}" 2>/dev/null || true
    fi

    # Restart FastAPI to reload any new model artifacts
    sudo systemctl restart ag-prediction 2>/dev/null || true

    echo "Monthly WASDE ingest + inference completed at $(date)"
    aws sns publish \
        --topic-arn "${SNS_TOPIC_ARN}" \
        --subject "Price ETL: WASDE Ingest SUCCESS" \
        --message "WASDE supply/demand ingest completed at $(date)." \
        --region "${AWS_REGION}" 2>/dev/null || true
    exit 0
fi

# ---------------------------------------------------------------------------
# Mode: --annual-ers  (ERS production costs)
# ---------------------------------------------------------------------------
if [ "${RUN_MODE}" = "--annual-ers" ]; then
    echo "Running ANNUAL ERS production costs load..."
    activate_backend_venv
    cd "${PROJECT_ROOT}"

    set +e
    python -m backend.etl.load_ers_costs
    ERS_EXIT=$?
    set -e

    if [ ${ERS_EXIT} -ne 0 ]; then
        echo "ERS costs load failed with exit code ${ERS_EXIT}"
        aws sns publish \
            --topic-arn "${SNS_TOPIC_ARN}" \
            --subject "Price ETL: ERS Costs FAILED" \
            --message "ERS production costs load failed at $(date). See log: ${LOGFILE}" \
            --region "${AWS_REGION}" 2>/dev/null || true
        exit 1
    fi

    echo "Annual ERS costs load completed successfully at $(date)"
    aws sns publish \
        --topic-arn "${SNS_TOPIC_ARN}" \
        --subject "Price ETL: ERS Costs SUCCESS" \
        --message "ERS production costs updated at $(date)." \
        --region "${AWS_REGION}" 2>/dev/null || true
    exit 0
fi

# ---------------------------------------------------------------------------
# Mode: --weekly-yield  (Weather/drought ETL + feature build + yield inference)
# ---------------------------------------------------------------------------
if [ "${RUN_MODE}" = "--weekly-yield" ]; then
    echo "Running WEEKLY yield pipeline..."
    activate_backend_venv
    cd "${PROJECT_ROOT}"

    set +e

    # Step 1: ETL - fetch latest data from all sources
    echo "Step 1a: NOAA weather data..."
    python -m backend.etl.ingest_noaa
    NOAA_EXIT=$?

    echo "Step 1b: NASA POWER solar/VPD..."
    python -m backend.etl.ingest_nasa_power
    NASA_EXIT=$?

    echo "Step 1c: US Drought Monitor..."
    python -m backend.etl.ingest_drought
    DROUGHT_EXIT=$?

    echo "Step 1d: NASS crop conditions..."
    python -m backend.etl.ingest_crop_conditions
    NASS_EXIT=$?

    # Step 2: Run yield inference
    echo "Step 2: Running yield inference..."
    python -m backend.models.yield_inference
    INFERENCE_EXIT=$?

    set -e

    # Check results
    FAILED=0
    [ ${NOAA_EXIT} -ne 0 ] && echo "WARNING: NOAA ingest failed" && FAILED=1
    [ ${NASA_EXIT} -ne 0 ] && echo "WARNING: NASA POWER ingest failed" && FAILED=1
    [ ${DROUGHT_EXIT} -ne 0 ] && echo "WARNING: Drought ingest failed" && FAILED=1
    [ ${NASS_EXIT} -ne 0 ] && echo "WARNING: NASS conditions ingest failed" && FAILED=1
    [ ${INFERENCE_EXIT} -ne 0 ] && echo "WARNING: Yield inference failed" && FAILED=1

    # Restart FastAPI to reload model cache
    sudo systemctl restart ag-prediction 2>/dev/null || true

    if [ ${FAILED} -ne 0 ]; then
        aws sns publish \
            --topic-arn "${SNS_TOPIC_ARN}" \
            --subject "Yield Pipeline: Partial FAILURE" \
            --message "Weekly yield pipeline completed with errors at $(date). NOAA=${NOAA_EXIT} NASA=${NASA_EXIT} Drought=${DROUGHT_EXIT} NASS=${NASS_EXIT} Inference=${INFERENCE_EXIT}. See log: ${LOGFILE}" \
            --region "${AWS_REGION}" 2>/dev/null || true
    else
        aws sns publish \
            --topic-arn "${SNS_TOPIC_ARN}" \
            --subject "Yield Pipeline: SUCCESS" \
            --message "Weekly yield pipeline completed successfully at $(date)." \
            --region "${AWS_REGION}" 2>/dev/null || true
    fi

    echo "Weekly yield pipeline completed at $(date)"
    exit 0
fi

# ===========================================================================
# Default Mode: NASS QuickStats Pipeline (original behavior)
# ===========================================================================

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
