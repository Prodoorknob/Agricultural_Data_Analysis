# Quick Start Guide for Windows (PowerShell)

## Local Development Setup

### 1. Install Prerequisites

```powershell
# Check Python version (should be 3.11+)
python --version

# Check Docker Desktop is running
docker --version
```

### 2. Install Python Dependencies

```powershell
# Navigate to project directory
cd "c:\path\to\Agricultural_Data_Analysis"

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Run Locally (Python)

```powershell
# Run with Flask dev server
python app.py

# Open browser to: http://localhost:8050
```

### 4. Run Locally (Docker)

```powershell
# Build Docker image
docker build -t usda-dashboard:latest .

# Run container
docker run -p 8080:8080 usda-dashboard:latest

# Open browser to: http://localhost:8080

# Stop container (Ctrl+C or in another PowerShell):
docker ps  # Get container ID
docker stop <container-id>
```

## AWS Deployment (Windows)

### 1. Install AWS CLI

Download from: https://aws.amazon.com/cli/

```powershell
# Verify installation
aws --version

# Configure AWS credentials
aws configure
# Enter:
#   AWS Access Key ID: (your key)
#   AWS Secret Access Key: (your secret)
#   Default region name: us-east-1
#   Default output format: json
```

### 2. Create ECR Repository

```powershell
# Set variables
$AWS_REGION = "us-east-1"
$REPO_NAME = "usda-dashboard"

# Create repository
aws ecr create-repository `
  --repository-name $REPO_NAME `
  --region $AWS_REGION
```

### 3. Deploy to ECR (PowerShell Version)

**Note**: The provided `deploy_to_ecr.sh` is a bash script. Here's the PowerShell equivalent:

```powershell
# Set variables (EDIT THESE)
$AWS_ACCOUNT_ID = "123456789012"  # Your 12-digit AWS account ID
$AWS_REGION = "us-east-1"
$REPO_NAME = "usda-dashboard"
$IMAGE_TAG = "latest"

# Get AWS account ID automatically
$AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)

Write-Host "=========================================="
Write-Host "Deploying to Amazon ECR"
Write-Host "=========================================="
Write-Host "Account ID: $AWS_ACCOUNT_ID"
Write-Host "Region: $AWS_REGION"
Write-Host "Repository: $REPO_NAME"
Write-Host "=========================================="

# Step 1: Authenticate Docker to ECR
Write-Host "`nStep 1: Authenticating Docker to ECR..."
aws ecr get-login-password --region $AWS_REGION | `
  docker login --username AWS --password-stdin `
  "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

# Step 2: Build Docker image
Write-Host "`nStep 2: Building Docker image..."
docker build -t "${REPO_NAME}:${IMAGE_TAG}" .

# Step 3: Tag image for ECR
Write-Host "`nStep 3: Tagging image for ECR..."
$ECR_IMAGE = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}"
docker tag "${REPO_NAME}:${IMAGE_TAG}" $ECR_IMAGE

# Step 4: Push to ECR
Write-Host "`nStep 4: Pushing image to ECR..."
docker push $ECR_IMAGE

Write-Host "`n=========================================="
Write-Host "✓ Deployment to ECR complete!"
Write-Host "=========================================="
Write-Host "Image URI: $ECR_IMAGE"
Write-Host "`nNext steps:"
Write-Host "  1. Go to AWS Console → App Runner → Create service"
Write-Host "  2. Select ECR repository: $REPO_NAME"
Write-Host "  3. Select tag: $IMAGE_TAG"
Write-Host "  4. Configure service settings (port 8080, 2-4 GB RAM)"
Write-Host "=========================================="
```

Save this as `deploy_to_ecr.ps1` and run:

```powershell
.\deploy_to_ecr.ps1
```

### 4. Create App Runner Service

**Via AWS Console:**

1. Open AWS Console → App Runner → "Create service"
2. **Source**: 
   - Container registry: Amazon ECR
   - Repository: `usda-dashboard`
   - Tag: `latest`
3. **Service settings**:
   - Service name: `usda-dashboard`
   - Port: `8080`
   - CPU: 1-2 vCPU
   - Memory: 2-4 GB
4. **Environment variables**:
   - (Optional) `S3_BUCKET_URL`: Your S3 URL if different
5. **Create service** and wait for deployment (~3-5 minutes)

**Via AWS CLI:**

```powershell
# Create apprunner.json config file first (see README.md for details)
aws apprunner create-service `
  --cli-input-json file://apprunner.json `
  --region us-east-1
```

## Troubleshooting (Windows)

### Docker Desktop not running
```powershell
# Start Docker Desktop manually or:
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

### Permission issues with virtual environment
```powershell
# If you get execution policy error:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then activate again:
.\venv\Scripts\Activate.ps1
```

### AWS CLI not found
```powershell
# Check if installed
Get-Command aws

# If not found, add to PATH or reinstall
# https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
```

### Port already in use
```powershell
# Find process using port 8080
netstat -ano | findstr :8080

# Kill process (use PID from above)
Stop-Process -Id <PID> -Force

# Or use different port:
docker run -p 8081:8080 usda-dashboard:latest
```

### Docker build fails
```powershell
# Clean Docker cache and rebuild
docker system prune -a
docker build --no-cache -t usda-dashboard:latest .
```

## Environment Variables (Windows)

### Set for current PowerShell session:
```powershell
$env:USE_S3 = "True"
$env:S3_BUCKET_URL = "https://your-bucket.s3.region.amazonaws.com/path"
python app.py
```

### Set for Docker run:
```powershell
docker run -p 8080:8080 `
  -e USE_S3=True `
  -e S3_BUCKET_URL="https://your-bucket.s3.region.amazonaws.com/path" `
  usda-dashboard:latest
```

## Quick Test Commands

```powershell
# Test app is running (Python)
Invoke-WebRequest -Uri http://localhost:8050 -UseBasicParsing

# Test app is running (Docker)
Invoke-WebRequest -Uri http://localhost:8080 -UseBasicParsing

# Check Docker logs
docker logs <container-id>

# Check AWS ECR repositories
aws ecr describe-repositories --region us-east-1

# Check App Runner services
aws apprunner list-services --region us-east-1
```

## File Paths (Windows)

Windows uses backslashes in paths. When working with WSL or bash scripts:

```powershell
# Convert Windows path to WSL path
wsl wslpath "C:\Users\rajas\Documents\ADS\Desktop\Applied Data Science\Agricultural_Data_Analysis"

# Run bash script from PowerShell (if WSL installed)
wsl bash ./deploy_to_ecr.sh

# Or use Git Bash
& "C:\Program Files\Git\bin\bash.exe" ./deploy_to_ecr.sh
```

## Additional Resources

- **AWS Console**: https://console.aws.amazon.com/
- **Docker Desktop**: https://www.docker.com/products/docker-desktop/
- **AWS CLI Windows Install**: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
- **Python Windows**: https://www.python.org/downloads/windows/
- **Git for Windows**: https://git-scm.com/download/win (includes Git Bash for bash scripts)

## Next Steps

1. ✅ Install prerequisites (Python, Docker, AWS CLI)
2. ✅ Clone/download repository
3. ✅ Install Python dependencies (`pip install -r requirements.txt`)
4. ✅ Test locally with Python (`python app.py`)
5. ✅ Test locally with Docker (`docker run...`)
6. ✅ Configure AWS CLI (`aws configure`)
7. ✅ Create ECR repository
8. ✅ Deploy to ECR (use PowerShell script above)
9. ✅ Create App Runner service
10. ✅ Access your deployed app!

For detailed instructions, see `README.md` and `DEPLOYMENT_SUMMARY.md`.
