# Pre-Deployment Checklist

Use this checklist to ensure everything is ready before deploying to AWS.

## Local Development Tests

### Python Environment
- [ ] Python 3.11+ installed (`python --version`)
- [ ] Virtual environment created (optional but recommended)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] No import errors when running `python test_server.py`

### Local Application Testing
- [ ] App runs locally: `python app.py`
- [ ] App accessible at http://localhost:8050
- [ ] Dashboard loads without errors
- [ ] Hex map displays correctly
- [ ] State selection works (click on state)
- [ ] Charts update when filters change
- [ ] Data loads from S3 (check console logs)
- [ ] No error messages in browser console

### Server Object Verification
- [ ] Run `python test_server.py` - all checks pass
- [ ] `app` object exists at module level
- [ ] `server` object exists at module level
- [ ] Server is a Flask instance

### Gunicorn Testing
- [ ] Install gunicorn: `pip install gunicorn`
- [ ] Run: `gunicorn app:server --bind 0.0.0.0:8050 --timeout 120`
- [ ] App accessible at http://localhost:8050
- [ ] No import errors
- [ ] Workers start successfully

## Docker Tests

### Docker Setup
- [ ] Docker Desktop installed and running
- [ ] Docker version check: `docker --version`
- [ ] Docker daemon running: `docker info`

### Docker Build
- [ ] Build command succeeds: `docker build -t usda-dashboard:latest .`
- [ ] Build completes without errors
- [ ] Image size reasonable (< 1 GB): `docker images usda-dashboard`
- [ ] No obvious warnings in build output

### Docker Run
- [ ] Container starts: `docker run -p 8080:8080 usda-dashboard:latest`
- [ ] App accessible at http://localhost:8080
- [ ] S3 data loads correctly
- [ ] No crashes or memory issues
- [ ] Container logs look clean: `docker logs <container-id>`
- [ ] Can stop cleanly: `docker stop <container-id>`

### Docker Health Check
- [ ] Health check passes after ~40 seconds
- [ ] Check with: `docker inspect <container-id> | grep Health -A 10`

## AWS Prerequisites

### AWS CLI
- [ ] AWS CLI installed: `aws --version`
- [ ] AWS credentials configured: `aws configure list`
- [ ] Can authenticate: `aws sts get-caller-identity`
- [ ] Correct region set (e.g., us-east-1)

### AWS Permissions
- [ ] IAM user/role has ECR permissions
- [ ] IAM user/role has App Runner permissions
- [ ] Can list ECR repos: `aws ecr describe-repositories`
- [ ] Can list App Runner services: `aws apprunner list-services`

### ECR Repository
- [ ] ECR repository created: `aws ecr describe-repositories --repository-names usda-dashboard`
- [ ] Repository exists in correct region
- [ ] Repository name matches deployment scripts

## S3 Data Access

### S3 Bucket Configuration
- [ ] S3 bucket exists and is accessible
- [ ] Bucket has public read permissions (for data files)
- [ ] S3 bucket URL correct in `data_prep.py`
- [ ] Test URL in browser: Should download CSV file
- [ ] Environment variable `S3_BUCKET_URL` set (if needed)

### Data Files
- [ ] All required CSV files present in S3
- [ ] Files are publicly readable (no 403 errors)
- [ ] File sizes reasonable (can be streamed)
- [ ] No authentication required to read

## Deployment Scripts

### Bash Script (Linux/Mac/WSL)
- [ ] `deploy_to_ecr.sh` exists
- [ ] Script is executable: `chmod +x deploy_to_ecr.sh`
- [ ] AWS_ACCOUNT_ID updated in script
- [ ] AWS_REGION updated in script
- [ ] REPO_NAME matches ECR repository

### PowerShell Script (Windows)
- [ ] `deploy_to_ecr.ps1` exists
- [ ] AWS_ACCOUNT_ID updated in script
- [ ] AWS_REGION updated in script
- [ ] REPO_NAME matches ECR repository
- [ ] Execution policy allows script: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`

## ECR Deployment

### Authentication
- [ ] Can log in to ECR:
  ```bash
  aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin \
    <account-id>.dkr.ecr.us-east-1.amazonaws.com
  ```

### Image Push
- [ ] Image tagged for ECR
- [ ] Push succeeds: `docker push <ecr-uri>:latest`
- [ ] Image visible in ECR console
- [ ] Image size reasonable (< 1 GB)

## App Runner Configuration

### Service Creation
- [ ] App Runner service created
- [ ] Service name: `usda-dashboard` (or your choice)
- [ ] Source: ECR, repository: `usda-dashboard`, tag: `latest`
- [ ] Port: `8080` configured
- [ ] CPU: 1-2 vCPU allocated
- [ ] Memory: 2-4 GB allocated
- [ ] Auto-scaling configured (if desired)

### Environment Variables
- [ ] `S3_BUCKET_URL` set (if different from default)
- [ ] `USE_S3` set to `True`
- [ ] Any other custom variables set

### Networking
- [ ] VPC configuration reviewed (optional)
- [ ] Outbound internet access allowed (for S3)
- [ ] No IAM role needed (data is public)

## Deployment Verification

### App Runner Status
- [ ] Service status: "Running"
- [ ] Last deployment: "Successful"
- [ ] No error events in events log
- [ ] Health check passing

### Application Access
- [ ] App Runner URL accessible (e.g., https://xxxxx.us-east-1.awsapprunner.com)
- [ ] Dashboard loads without errors
- [ ] S3 data loads correctly
- [ ] All features work (filters, charts, state selection)
- [ ] Page load time reasonable (< 10 seconds)

### CloudWatch Logs
- [ ] Logs stream created
- [ ] No error messages in logs
- [ ] Gunicorn workers starting successfully
- [ ] HTTP requests logged (200 status codes)

### Performance
- [ ] First load time acceptable
- [ ] Subsequent loads fast (if caching enabled)
- [ ] No memory warnings
- [ ] No timeout errors

## GitHub Actions (Optional)

### Secrets Configuration
- [ ] GitHub repository exists
- [ ] Secrets added to repository settings
- [ ] `AWS_ROLE_TO_ASSUME` or access keys configured
- [ ] Secrets are correct (test workflow)

### Workflow File
- [ ] `.github/workflows/deploy-to-ecr.yml` exists
- [ ] AWS_REGION in workflow matches actual region
- [ ] ECR_REPOSITORY in workflow matches actual repo
- [ ] Workflow triggers configured (push to main, manual)

### Workflow Testing
- [ ] Push to main triggers workflow
- [ ] Workflow completes successfully
- [ ] Image pushed to ECR
- [ ] GitHub Actions logs clean

## Documentation

### README.md
- [ ] README.md exists and is complete
- [ ] Local development instructions clear
- [ ] Docker instructions tested
- [ ] AWS deployment steps accurate
- [ ] Troubleshooting section helpful

### Additional Docs
- [ ] DEPLOYMENT_SUMMARY.md reviewed
- [ ] GITHUB_ACTIONS_SETUP.md complete (if using)
- [ ] WINDOWS_QUICKSTART.md accurate (if on Windows)

## Final Pre-Flight Checks

### Code Quality
- [ ] No hardcoded credentials in code
- [ ] No sensitive data in repository
- [ ] .gitignore configured properly
- [ ] .dockerignore optimizes build

### Cost Considerations
- [ ] Understand App Runner costs (~$50-100/month)
- [ ] Understand ECR storage costs (~$0.10/GB/month)
- [ ] Auto-scaling configured to minimize costs
- [ ] Consider min instances = 0 for low-traffic periods

### Monitoring Plan
- [ ] CloudWatch Logs enabled
- [ ] Plan to check logs regularly
- [ ] Plan to monitor App Runner metrics
- [ ] Plan to monitor costs

### Rollback Plan
- [ ] Know how to redeploy previous image
- [ ] Can quickly pause/stop App Runner service
- [ ] Have local backup of working code

## Post-Deployment

### Immediate (Within 1 hour)
- [ ] Verify app is accessible
- [ ] Test all major features
- [ ] Check CloudWatch Logs for errors
- [ ] Monitor memory usage

### Short-term (Within 24 hours)
- [ ] Test under load (if expecting traffic)
- [ ] Verify S3 data refresh works (if applicable)
- [ ] Check App Runner metrics
- [ ] Review any error logs

### Long-term (Within 1 week)
- [ ] Monitor costs vs. estimates
- [ ] Optimize worker count if needed
- [ ] Optimize memory if needed
- [ ] Set up alerts for errors/downtime

## Troubleshooting Resources

If something goes wrong:
1. **Check CloudWatch Logs** in App Runner console
2. **Review README.md** troubleshooting section
3. **Test locally** with Docker to isolate issues
4. **Verify environment variables** in App Runner
5. **Check S3 access** - test URLs in browser
6. **Run validation script**: `./validate_setup.sh` (bash) or review WINDOWS_QUICKSTART.md
7. **Review DEPLOYMENT_SUMMARY.md** for architecture overview

## Sign-Off

Date: ________________

Tested by: ________________

Notes:
_______________________________________________________________
_______________________________________________________________
_______________________________________________________________

Ready for production deployment: YES / NO
