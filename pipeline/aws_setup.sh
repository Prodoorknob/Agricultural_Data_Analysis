#!/bin/bash
# aws_setup.sh - Set up AWS infrastructure for Athena SQL layer and pipeline
#
# Prerequisites:
#   - AWS CLI v2 installed and configured
#   - Appropriate IAM permissions
#
# Usage:
#   chmod +x aws_setup.sh
#   ./aws_setup.sh

set -euo pipefail

AWS_REGION="us-east-2"
AWS_ACCOUNT_ID="294733692749"
S3_BUCKET="usda-analysis-datasets"

echo "=============================================="
echo "AWS Infrastructure Setup"
echo "Region: ${AWS_REGION}"
echo "Account: ${AWS_ACCOUNT_ID}"
echo "=============================================="

# ─── 1. Create Athena results directory in S3 ───
echo ""
echo "Step 1: Creating Athena results directory..."
aws s3api put-object \
    --bucket "${S3_BUCKET}" \
    --key "athena-results/" \
    --region "${AWS_REGION}" 2>/dev/null && \
    echo "  Created athena-results/ prefix" || \
    echo "  athena-results/ already exists"

# ─── 2. Create Glue Database ───
echo ""
echo "Step 2: Creating Glue database..."
aws glue create-database \
    --database-input '{"Name":"usda_agricultural","Description":"USDA QuickStats agricultural data"}' \
    --region "${AWS_REGION}" 2>/dev/null && \
    echo "  Created database: usda_agricultural" || \
    echo "  Database usda_agricultural already exists"

# ─── 3. Create Glue Table with Partition Projection ───
echo ""
echo "Step 3: Creating Glue table with partition projection..."

# State codes for partition projection
STATE_CODES="AL,AK,AZ,AR,CA,CO,CT,DE,FL,GA,HI,ID,IL,IN,IA,KS,KY,LA,ME,MD,MA,MI,MN,MS,MO,MT,NE,NV,NH,NJ,NM,NY,NC,ND,OH,OK,OR,PA,RI,SC,SD,TN,TX,UT,VT,VA,WA,WV,WI,WY,US"

TABLE_INPUT=$(cat <<'TABLEEOF'
{
  "Name": "quickstats_data",
  "Description": "USDA QuickStats agricultural data partitioned by state (SURVEY + CENSUS)",
  "StorageDescriptor": {
    "Columns": [
      {"Name": "source_desc", "Type": "string", "Comment": "SURVEY, CENSUS, or DERIVED"},
      {"Name": "sector_desc", "Type": "string", "Comment": "CROPS, ANIMALS & PRODUCTS, ECONOMICS"},
      {"Name": "group_desc", "Type": "string", "Comment": "Sub-group within sector"},
      {"Name": "commodity_desc", "Type": "string", "Comment": "Commodity name (CORN, SOYBEANS, etc.)"},
      {"Name": "class_desc", "Type": "string", "Comment": "Commodity class"},
      {"Name": "prodn_practice_desc", "Type": "string", "Comment": "Production practice"},
      {"Name": "util_practice_desc", "Type": "string", "Comment": "Utilization practice"},
      {"Name": "statisticcat_desc", "Type": "string", "Comment": "Statistical category (AREA HARVESTED, YIELD, etc.)"},
      {"Name": "unit_desc", "Type": "string", "Comment": "Unit of measurement"},
      {"Name": "short_desc", "Type": "string", "Comment": "Short description"},
      {"Name": "domain_desc", "Type": "string", "Comment": "Domain (TOTAL, ORGANIC STATUS, etc.)"},
      {"Name": "domaincat_desc", "Type": "string", "Comment": "Domain category"},
      {"Name": "agg_level_desc", "Type": "string", "Comment": "Aggregation level (STATE, NATIONAL)"},
      {"Name": "state_fips_code", "Type": "string", "Comment": "State FIPS code"},
      {"Name": "state_name", "Type": "string", "Comment": "Full state name"},
      {"Name": "county_code", "Type": "string", "Comment": "County FIPS code"},
      {"Name": "county_name", "Type": "string", "Comment": "County name"},
      {"Name": "year", "Type": "int", "Comment": "Survey year"},
      {"Name": "Value", "Type": "string", "Comment": "Raw value string"},
      {"Name": "CV (%)", "Type": "string", "Comment": "Coefficient of variation"},
      {"Name": "value_num", "Type": "double", "Comment": "Cleaned numeric value"},
      {"Name": "dataset_source", "Type": "string", "Comment": "Source dataset identifier"},
      {"Name": "freq_desc", "Type": "string", "Comment": "Frequency: ANNUAL, WEEKLY, MONTHLY"},
      {"Name": "reference_period_desc", "Type": "string", "Comment": "Period: YEAR, WEEK #12, MAR"},
      {"Name": "begin_code", "Type": "string", "Comment": "Begin period code"},
      {"Name": "end_code", "Type": "string", "Comment": "End period code"},
      {"Name": "fips", "Type": "string", "Comment": "Combined state+county FIPS code"}
    ],
    "Location": "s3://usda-analysis-datasets/survey_datasets/athena_optimized/",
    "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
    "SerdeInfo": {
      "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    },
    "Compressed": true
  },
  "PartitionKeys": [
    {"Name": "state_alpha", "Type": "string", "Comment": "State code partition key"}
  ],
  "TableType": "EXTERNAL_TABLE",
  "Parameters": {
    "classification": "parquet",
    "projection.enabled": "true",
    "projection.state_alpha.type": "enum",
    "projection.state_alpha.values": "AL,AK,AZ,AR,CA,CO,CT,DE,FL,GA,HI,ID,IL,IN,IA,KS,KY,LA,ME,MD,MA,MI,MN,MS,MO,MT,NE,NV,NH,NJ,NM,NY,NC,ND,OH,OK,OR,PA,RI,SC,SD,TN,TX,UT,VT,VA,WA,WV,WI,WY,US",
    "storage.location.template": "s3://usda-analysis-datasets/survey_datasets/athena_optimized/state_alpha=${state_alpha}/"
  }
}
TABLEEOF
)

aws glue create-table \
    --database-name usda_agricultural \
    --table-input "${TABLE_INPUT}" \
    --region "${AWS_REGION}" 2>/dev/null && \
    echo "  Created table: quickstats_data" || \
    echo "  Table quickstats_data already exists (delete and recreate if schema changed)"

# ─── 4. Create Athena Workgroup ───
echo ""
echo "Step 4: Creating Athena workgroup..."
aws athena create-work-group \
    --name usda-dashboard \
    --configuration "{
        \"ResultConfiguration\":{
            \"OutputLocation\":\"s3://${S3_BUCKET}/athena-results/\"
        },
        \"EnforceWorkGroupConfiguration\":true,
        \"BytesScannedCutoffPerQuery\":104857600
    }" \
    --description "USDA Dashboard query workgroup (100MB scan limit)" \
    --region "${AWS_REGION}" 2>/dev/null && \
    echo "  Created workgroup: usda-dashboard" || \
    echo "  Workgroup usda-dashboard already exists"

# ─── 5. Create SNS Topic for Pipeline Alerts ───
echo ""
echo "Step 5: Creating SNS topic for pipeline alerts..."
SNS_ARN=$(aws sns create-topic \
    --name usda-pipeline-alerts \
    --region "${AWS_REGION}" \
    --output text --query 'TopicArn' 2>/dev/null) && \
    echo "  Created SNS topic: ${SNS_ARN}" || \
    echo "  SNS topic may already exist"

echo ""
echo "  To subscribe to alerts, run:"
echo "  aws sns subscribe --topic-arn ${SNS_ARN:-arn:aws:sns:us-east-2:294733692749:usda-pipeline-alerts} --protocol email --notification-endpoint YOUR_EMAIL"

# ─── 6. Create IAM Policies ───
echo ""
echo "Step 6: Creating IAM policies..."

# Pipeline S3 Access Policy
PIPELINE_POLICY=$(cat <<'POLICYEOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "S3DataAccess",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:CopyObject",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::usda-analysis-datasets",
                "arn:aws:s3:::usda-analysis-datasets/*"
            ]
        },
        {
            "Sid": "SNSAlerts",
            "Effect": "Allow",
            "Action": ["sns:Publish"],
            "Resource": "arn:aws:sns:us-east-2:294733692749:usda-pipeline-alerts"
        },
        {
            "Sid": "SSMParameterRead",
            "Effect": "Allow",
            "Action": ["ssm:GetParameter"],
            "Resource": "arn:aws:ssm:us-east-2:294733692749:parameter/usda/*"
        }
    ]
}
POLICYEOF
)

aws iam create-policy \
    --policy-name USDA-Pipeline-S3-Access \
    --policy-document "${PIPELINE_POLICY}" \
    --description "S3, SNS, SSM access for USDA data pipeline" 2>/dev/null && \
    echo "  Created policy: USDA-Pipeline-S3-Access" || \
    echo "  Policy USDA-Pipeline-S3-Access already exists"

# Athena Query Policy
ATHENA_POLICY=$(cat <<'ATHENAPOLICYEOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AthenaAccess",
            "Effect": "Allow",
            "Action": [
                "athena:StartQueryExecution",
                "athena:GetQueryExecution",
                "athena:GetQueryResults",
                "athena:StopQueryExecution"
            ],
            "Resource": "arn:aws:athena:us-east-2:294733692749:workgroup/usda-dashboard"
        },
        {
            "Sid": "S3DataRead",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:ListBucket",
                "s3:PutObject",
                "s3:GetBucketLocation"
            ],
            "Resource": [
                "arn:aws:s3:::usda-analysis-datasets",
                "arn:aws:s3:::usda-analysis-datasets/*"
            ]
        },
        {
            "Sid": "GlueCatalog",
            "Effect": "Allow",
            "Action": [
                "glue:GetTable",
                "glue:GetPartitions",
                "glue:GetDatabase"
            ],
            "Resource": [
                "arn:aws:glue:us-east-2:294733692749:catalog",
                "arn:aws:glue:us-east-2:294733692749:database/usda_agricultural",
                "arn:aws:glue:us-east-2:294733692749:table/usda_agricultural/*"
            ]
        }
    ]
}
ATHENAPOLICYEOF
)

aws iam create-policy \
    --policy-name USDA-Athena-Query-Access \
    --policy-document "${ATHENA_POLICY}" \
    --description "Athena, S3, Glue access for USDA dashboard queries" 2>/dev/null && \
    echo "  Created policy: USDA-Athena-Query-Access" || \
    echo "  Policy USDA-Athena-Query-Access already exists"

# ─── Summary ───
echo ""
echo "=============================================="
echo "Infrastructure setup complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Store your QuickStats API key:"
echo "     aws ssm put-parameter --name /usda/quickstats-api-key --value 'YOUR_KEY' --type SecureString --region ${AWS_REGION}"
echo ""
echo "  2. Attach policies to your EC2 instance role:"
echo "     - USDA-Pipeline-S3-Access"
echo "     - USDA-Athena-Query-Access"
echo ""
echo "  3. Run the pipeline manually first:"
echo "     cd pipeline && python quickstats_ingest.py --states IN --year-start 2023 --year-end 2023"
echo ""
echo "  4. Upload data to S3:"
echo "     python upload_to_s3.py"
echo ""
echo "  5. Test Athena query in AWS Console:"
echo "     SELECT COUNT(*), state_alpha FROM usda_agricultural.quickstats_data GROUP BY state_alpha"
echo ""
echo "  6. Set up cron job on EC2:"
echo "     crontab -e"
echo "     0 6 15 * * $(pwd)/pipeline/cron_runner.sh >> /var/log/usda-pipeline.log 2>&1"
echo ""
