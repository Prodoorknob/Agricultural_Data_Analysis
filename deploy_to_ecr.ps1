# deploy_to_ecr.ps1 - Build and push Docker image to Amazon ECR
#
# Usage:
#   1. Edit the variables below (AWS_ACCOUNT_ID, AWS_REGION, REPO_NAME)
#   2. Run in PowerShell: .\deploy_to_ecr.ps1
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker Desktop installed and running
#   - ECR repository created
#   - Permissions for ECR operations

# Exit on error
$ErrorActionPreference = "Stop"

# ============================================================================
# CONFIGURATION - Edit these values
# ============================================================================

# Your AWS account ID (12-digit number)
# Get it with: aws sts get-caller-identity --query Account --output text
$AWS_ACCOUNT_ID = "123456789012"

# AWS region where ECR repository exists
$AWS_REGION = "us-east-1"

# ECR repository name
$REPO_NAME = "usda-dashboard"

# Docker image tag
$IMAGE_TAG = "latest"

# ============================================================================
# SCRIPT START
# ============================================================================

Write-Host "=========================================="
Write-Host "Deploying to Amazon ECR"
Write-Host "=========================================="
Write-Host "Account ID: $AWS_ACCOUNT_ID"
Write-Host "Region: $AWS_REGION"
Write-Host "Repository: $REPO_NAME"
Write-Host "Tag: $IMAGE_TAG"
Write-Host "=========================================="
Write-Host ""

# Step 1: Authenticate Docker to ECR
Write-Host "Step 1: Authenticating Docker to ECR..."
try {
    $loginCommand = aws ecr get-login-password --region $AWS_REGION
    $loginCommand | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
    Write-Host "✓ Authentication successful" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to authenticate to ECR" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
Write-Host ""

# Step 2: Build Docker image
Write-Host "Step 2: Building Docker image..."
try {
    docker build -t "${REPO_NAME}:${IMAGE_TAG}" .
    if ($LASTEXITCODE -ne 0) { throw "Docker build failed" }
    Write-Host "✓ Build successful" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Docker build failed" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
Write-Host ""

# Step 3: Tag image for ECR
Write-Host "Step 3: Tagging image for ECR..."
try {
    $ECR_IMAGE = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}"
    docker tag "${REPO_NAME}:${IMAGE_TAG}" $ECR_IMAGE
    if ($LASTEXITCODE -ne 0) { throw "Docker tag failed" }
    Write-Host "✓ Tagged as: $ECR_IMAGE" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to tag image" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
Write-Host ""

# Step 4: Push to ECR
Write-Host "Step 4: Pushing image to ECR..."
try {
    docker push $ECR_IMAGE
    if ($LASTEXITCODE -ne 0) { throw "Docker push failed" }
    Write-Host "✓ Push successful" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to push image to ECR" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
Write-Host ""

# Success message
Write-Host "=========================================="
Write-Host "✓ Deployment to ECR complete!" -ForegroundColor Green
Write-Host "=========================================="
Write-Host "Image URI: $ECR_IMAGE"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Go to AWS Console → App Runner → Create service"
Write-Host "  2. Select ECR repository: $REPO_NAME"
Write-Host "  3. Select tag: $IMAGE_TAG"
Write-Host "  4. Configure service settings (port 8080, 2-4 GB RAM)"
Write-Host "  5. Deploy!"
Write-Host ""
Write-Host "Or update existing App Runner service:"
Write-Host "  aws apprunner start-deployment --service-arn <your-service-arn>"
Write-Host "=========================================="
