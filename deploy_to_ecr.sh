#!/usr/bin/env bash
#
# deploy_to_ecr.sh - Build and push Docker image to Amazon ECR
#
# Usage:
#   1. Edit the variables below (AWS_ACCOUNT_ID, AWS_REGION, REPO_NAME)
#   2. Make executable: chmod +x deploy_to_ecr.sh
#   3. Run: ./deploy_to_ecr.sh
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - Docker installed and running
#   - ECR repository created (see README.md)
#   - Permissions for ECR operations

set -e  # Exit on any error

# ============================================================================
# CONFIGURATION - Edit these values
# ============================================================================

# Your AWS account ID (12-digit number)
# Get it with: aws sts get-caller-identity --query Account --output text
AWS_ACCOUNT_ID="123456789012"

# AWS region where ECR repository exists
AWS_REGION="us-east-1"

# ECR repository name
REPO_NAME="usda-dashboard"

# Docker image tag
IMAGE_TAG="latest"

# ============================================================================
# SCRIPT START
# ============================================================================

echo "=========================================="
echo "Deploying to Amazon ECR"
echo "=========================================="
echo "Account ID: ${AWS_ACCOUNT_ID}"
echo "Region: ${AWS_REGION}"
echo "Repository: ${REPO_NAME}"
echo "Tag: ${IMAGE_TAG}"
echo "=========================================="
echo ""

# Step 1: Authenticate Docker to ECR
echo "Step 1: Authenticating Docker to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin \
    "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to authenticate to ECR"
    exit 1
fi
echo "✓ Authentication successful"
echo ""

# Step 2: Build Docker image
echo "Step 2: Building Docker image..."
docker build -t "${REPO_NAME}:${IMAGE_TAG}" .

if [ $? -ne 0 ]; then
    echo "ERROR: Docker build failed"
    exit 1
fi
echo "✓ Build successful"
echo ""

# Step 3: Tag image for ECR
echo "Step 3: Tagging image for ECR..."
ECR_IMAGE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:${IMAGE_TAG}"
docker tag "${REPO_NAME}:${IMAGE_TAG}" "${ECR_IMAGE}"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to tag image"
    exit 1
fi
echo "✓ Tagged as: ${ECR_IMAGE}"
echo ""

# Step 4: Push to ECR
echo "Step 4: Pushing image to ECR..."
docker push "${ECR_IMAGE}"

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to push image to ECR"
    exit 1
fi
echo "✓ Push successful"
echo ""

# Success message
echo "=========================================="
echo "✓ Deployment to ECR complete!"
echo "=========================================="
echo "Image URI: ${ECR_IMAGE}"
echo ""
echo "Next steps:"
echo "  1. Go to AWS Console → App Runner → Create service"
echo "  2. Select ECR repository: ${REPO_NAME}"
echo "  3. Select tag: ${IMAGE_TAG}"
echo "  4. Configure service settings (port 8080, 2-4 GB RAM)"
echo "  5. Deploy!"
echo ""
echo "Or update existing App Runner service:"
echo "  aws apprunner start-deployment --service-arn <your-service-arn>"
echo "=========================================="
