# USDA Agricultural Dashboard

A Dash web application for visualizing and analyzing USDA agricultural data including crops, land use, and economic trends across US states.

## Features

- **Interactive Hex Map**: US state-level visualization with hexagonal tiles for better visibility
- **Multi-View Dashboard**: Overview, Land & Area, Labor & Operations, Economics & Profitability
- **Time Series Analysis**: Trend charts for area, revenue, operations, and more
- **Crop Comparison**: Side-by-side analysis of different crops and regions
- **Large Dataset Support**: Loads data from public S3 bucket with memory-efficient streaming

## Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- pip

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd Agricultural_Data_Analysis

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Open your browser to: http://localhost:8050

### Environment Variables

- `USE_S3`: Set to `True` to load data from S3, `False` for local files (default: `True`)
- `S3_BUCKET_URL`: Base URL for S3 data (default: `https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets`)
- `USE_SAMPLE_DATA`: Set to `True` in `app.py` for faster development with smaller dataset

## Local Docker Run

### Build the Docker image

```bash
docker build -t usda-dashboard:latest .
```

### Run the container

```bash
docker run -p 8080:8080 usda-dashboard:latest
```

Access the app at: http://localhost:8080

### Run with custom environment variables

```bash
docker run -p 8080:8080 \
  -e S3_BUCKET_URL="https://your-bucket.s3.region.amazonaws.com/path" \
  -e USE_S3=True \
  usda-dashboard:latest
```

### Test locally before deploying

```bash
# Build
docker build -t usda-dashboard:latest .

# Run
docker run -p 8080:8080 usda-dashboard:latest

# In another terminal, test the endpoint
curl http://localhost:8080
```

## Deploying to AWS (ECR + EC2 t2.micro - Free Tier)

### Recommended: Free Deployment on t2.micro

For the best free option, deploy on **AWS EC2 t2.micro** (free for 12 months):

- **No credit card charges** for 12 months
- **Built-in caching** optimizes for 1 GB RAM
- **Complete guide**: See `EC2_DEPLOYMENT.md`

```bash
# Quick summary:
1. Deploy Docker image to ECR (see below)
2. Launch t2.micro EC2 instance (free tier)
3. Pull image and run with caching enabled
4. Access at http://your-ec2-public-ip
```

**Cost**: $0/month for 12 months, then ~$13/month after free tier expires

### Alternative: AWS App Runner (Paid)

If you prefer a fully managed service (costs money):

- Setup: Follow "Deploying to AWS (ECR + App Runner)" section below
- Cost: ~$50-100/month
- No infrastructure management

---

## Deploying to AWS (ECR + App Runner)
- **Amazon ECR**: Container registry for storing Docker images
- **AWS App Runner**: Managed service for running containers

### Prerequisites

1. AWS account with CLI configured (`aws configure`)
2. AWS region (e.g., `us-east-1`)
3. Permissions for ECR and App Runner
4. **S3 bucket with public read access** for data files
   - The app reads data via public HTTPS URLs
   - No IAM role or AWS credentials needed by the app itself

### Step 1: Create ECR Repository

```bash
# Set your variables
export AWS_REGION="us-east-1"
export REPO_NAME="usda-dashboard"

# Create ECR repository
aws ecr create-repository \
  --repository-name ${REPO_NAME} \
  --region ${AWS_REGION}
```

### Step 2: Authenticate Docker to ECR

```bash
# Get your AWS account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Log in to ECR
aws ecr get-login-password --region ${AWS_REGION} \
  | docker login \
    --username AWS \
    --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

### Step 3: Build, Tag, and Push Image

```bash
# Build the image
docker build -t ${REPO_NAME}:latest .

# Tag for ECR
docker tag ${REPO_NAME}:latest \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:latest

# Push to ECR
docker push \
  ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:latest
```

**OR** use the provided script:

```bash
# Edit deploy_to_ecr.sh with your AWS_ACCOUNT_ID and AWS_REGION
chmod +x deploy_to_ecr.sh
./deploy_to_ecr.sh
```

### Step 4: Create App Runner Service

1. Go to AWS Console → **App Runner** → **Create service**

2. **Source**: 
   - Select "Container registry" → "Amazon ECR"
   - Choose your repository: `usda-dashboard`
   - Image tag: `latest`
   - Deployment trigger: Manual or Automatic

3. **Service settings**:
   - Service name: `usda-dashboard`
   - Port: `8080`
   - CPU: 1 vCPU (or 2 vCPU for better performance)
   - Memory: 2 GB (or 4 GB for large datasets)

4. **Environment variables** (optional):
   - `S3_BUCKET_URL`: Your S3 bucket URL if different from default
   - `USE_S3`: `True`

5. **Security**:
   - **Instance role**: NOT REQUIRED (S3 data is public)
   - The app uses public HTTPS URLs to read S3 data
   - No AWS credentials or IAM policies needed for data access

6. **Review and Create**

7. Wait for deployment (2-5 minutes)

8. Access your app at the provided App Runner URL (e.g., `https://xxxxx.us-east-1.awsapprunner.com`)

### Important Notes

- **S3 Public Access**: The S3 bucket containing data files must have public read access enabled. The app does NOT use IAM credentials to read data - it uses standard HTTPS requests to public S3 URLs.

- **IAM for Deployment**: You need IAM permissions to push to ECR and create App Runner services, but the running app itself doesn't need any IAM role for S3.

- **Cost Considerations**: 
  - App Runner charges for vCPU/memory provisioned and requests
  - Recommended: 1-2 vCPU, 2-4 GB RAM
  - Set auto-scaling min instances to 1 for cost savings during low traffic

- **Updates**: To deploy new versions:
  ```bash
  # Rebuild and push
  docker build -t ${REPO_NAME}:latest .
  docker tag ${REPO_NAME}:latest ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:latest
  docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:latest
  
  # Trigger deployment in App Runner console or use CLI:
  aws apprunner start-deployment --service-arn <your-service-arn>
  ```

## Project Structure

```
Agricultural_Data_Analysis/
├── app.py                 # Main Dash application (exposes server for gunicorn)
├── data_prep.py          # Data loading and preprocessing (S3 or local)
├── visuals.py            # Plotly chart generation functions
├── requirements.txt      # Python dependencies
├── Dockerfile            # Production container image
├── deploy_to_ecr.sh      # Helper script for ECR deployment
└── README.md             # This file
```

## Data Sources

- **USDA NASS Quick Stats**: Crop area, production, revenue, operations
- **USDA ERS Major Land Uses**: Land use composition by state
- **BLS OEWS**: Labor and wage statistics

All data is loaded from a public S3 bucket via HTTPS URLs (no authentication required).

## Development

### Using Sample Data

For faster development, set `USE_SAMPLE_DATA = True` in `app.py` to load a smaller subset of data.

### Local Files

To use local data files instead of S3:

1. Set `USE_S3 = False` in `data_prep.py` (or via environment variable)
2. Place CSV files in `./survey_datasets/` directory

### Running with Flask Dev Server

```bash
python app.py
# Opens on http://0.0.0.0:8050 with debug mode
```

### Running with Gunicorn (Production-like)

```bash
gunicorn app:server --bind 0.0.0.0:8050 --workers 2 --timeout 120
```

## Troubleshooting

### Memory Issues

If the app crashes due to memory:
- Increase Docker memory limit: `docker run -m 4g ...`
- Increase App Runner memory to 4 GB
- Set `USE_SAMPLE_DATA = True` for development

### S3 Connection Issues

If data fails to load:
- Verify S3 bucket URL is correct
- Ensure S3 objects have public read permissions
- Check network connectivity from container

### Port Issues

- Local dev: Uses port 8050
- Docker/App Runner: Uses port 8080
- Make sure the correct port is exposed and bound

## License

[Your License Here]

## Contact

[Your Contact Info Here]
