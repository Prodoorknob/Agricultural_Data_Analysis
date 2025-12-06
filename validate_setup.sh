#!/usr/bin/env bash
#
# validate_setup.sh - Validate Docker and AWS deployment setup
#
# Usage: ./validate_setup.sh
#
# This script checks:
#   1. Required files exist
#   2. Docker is working
#   3. AWS CLI is configured
#   4. ECR repository exists (optional)

set -e

echo "=========================================="
echo "Validating AWS Deployment Setup"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check function
check() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
    else
        echo -e "${RED}✗${NC} $1"
        return 1
    fi
}

# Warning function
warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Info function
info() {
    echo -e "${NC}ℹ${NC} $1"
}

# Check required files
echo "Checking required files..."
[ -f "app.py" ] && check "app.py exists" || warn "app.py not found"
[ -f "data_prep.py" ] && check "data_prep.py exists" || warn "data_prep.py not found"
[ -f "visuals.py" ] && check "visuals.py exists" || warn "visuals.py not found"
[ -f "requirements.txt" ] && check "requirements.txt exists" || warn "requirements.txt not found"
[ -f "Dockerfile" ] && check "Dockerfile exists" || warn "Dockerfile not found"
[ -f "deploy_to_ecr.sh" ] && check "deploy_to_ecr.sh exists" || warn "deploy_to_ecr.sh not found"
[ -f "README.md" ] && check "README.md exists" || warn "README.md not found"
echo ""

# Check app.py for server object
echo "Checking app.py configuration..."
if grep -q "server = app.server" app.py; then
    check "app.py exposes server object for gunicorn"
else
    warn "app.py might not expose server object correctly"
fi
echo ""

# Check Docker
echo "Checking Docker..."
if command -v docker &> /dev/null; then
    check "Docker is installed"
    if docker info &> /dev/null; then
        check "Docker daemon is running"
    else
        warn "Docker daemon is not running - start Docker Desktop"
    fi
else
    warn "Docker is not installed"
fi
echo ""

# Check AWS CLI
echo "Checking AWS CLI..."
if command -v aws &> /dev/null; then
    check "AWS CLI is installed"
    
    # Check AWS configuration
    if aws sts get-caller-identity &> /dev/null; then
        check "AWS CLI is configured"
        AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        info "AWS Account ID: ${AWS_ACCOUNT_ID}"
        
        # Check AWS region
        AWS_REGION=$(aws configure get region)
        if [ -z "$AWS_REGION" ]; then
            warn "AWS region not configured - set with: aws configure set region us-east-1"
        else
            check "AWS region configured: ${AWS_REGION}"
        fi
    else
        warn "AWS CLI not configured - run: aws configure"
    fi
else
    warn "AWS CLI not installed - install from: https://aws.amazon.com/cli/"
fi
echo ""

# Check Python
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    check "Python 3 is installed: ${PYTHON_VERSION}"
else
    warn "Python 3 not found"
fi
echo ""

# Check S3 access (if data_prep.py has S3_BUCKET_URL)
echo "Checking S3 configuration..."
if grep -q "S3_BUCKET_URL" data_prep.py; then
    check "data_prep.py configured for S3"
    S3_URL=$(grep "S3_BUCKET_URL" data_prep.py | grep -o 'https://[^"]*' | head -1)
    if [ ! -z "$S3_URL" ]; then
        info "S3 bucket URL: ${S3_URL}"
    fi
else
    warn "S3 configuration not found in data_prep.py"
fi
echo ""

# Check ECR repository (optional)
if [ ! -z "$AWS_ACCOUNT_ID" ] && [ ! -z "$AWS_REGION" ]; then
    echo "Checking ECR repository (optional)..."
    REPO_NAME="usda-dashboard"
    
    if aws ecr describe-repositories --repository-names $REPO_NAME --region $AWS_REGION &> /dev/null; then
        check "ECR repository '${REPO_NAME}' exists"
    else
        warn "ECR repository '${REPO_NAME}' not found - create with: aws ecr create-repository --repository-name ${REPO_NAME}"
    fi
    echo ""
fi

# Summary
echo "=========================================="
echo "Validation Summary"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. If Docker is not running: Start Docker Desktop"
echo "2. If AWS CLI is not configured: Run 'aws configure'"
echo "3. Test local build: docker build -t usda-dashboard:latest ."
echo "4. Test local run: docker run -p 8080:8080 usda-dashboard:latest"
echo "5. Create ECR repository: aws ecr create-repository --repository-name usda-dashboard"
echo "6. Deploy to ECR: ./deploy_to_ecr.sh (edit AWS_ACCOUNT_ID first)"
echo ""
echo "See README.md for detailed instructions."
echo "=========================================="
