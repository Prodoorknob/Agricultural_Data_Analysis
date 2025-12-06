# AWS Deployment Setup - Summary of Changes

This document summarizes all changes made to prepare the USDA Agricultural Dashboard for AWS deployment using Docker, ECR, and App Runner.

## Files Created

### 1. `Dockerfile`
Production-ready Docker container configuration:
- Base: `python:3.11-slim`
- Installs dependencies from `requirements.txt`
- Exposes port 8080 (App Runner default)
- Runs with gunicorn (2 workers, 120s timeout)
- Includes health check for App Runner

### 2. `requirements.txt` (updated)
Clean Python dependencies for production:
- Dash web framework
- Pandas, NumPy for data processing
- Plotly, Matplotlib, Seaborn for visualization
- Requests for HTTP (S3 data via HTTPS)
- Gunicorn for WSGI server
- **Removed**: boto3, s3fs (not needed for public S3 access)

### 3. `README.md`
Comprehensive documentation covering:
- Quick start for local development
- Docker build and run instructions
- Step-by-step AWS ECR + App Runner deployment
- Environment variables configuration
- Troubleshooting guide
- Notes on public S3 access (no IAM needed)

### 4. `deploy_to_ecr.sh`
Bash script to automate ECR deployment:
- Authenticates Docker to ECR
- Builds Docker image
- Tags for ECR
- Pushes to ECR
- Variables at top for easy configuration

### 5. `.github/workflows/deploy-to-ecr.yml`
GitHub Actions workflow for CI/CD:
- Triggers on push to main or manual dispatch
- Builds and pushes to ECR automatically
- Supports both OIDC and access key authentication
- Tags with git SHA and `latest`
- Optional: automatic App Runner deployment trigger

### 6. `GITHUB_ACTIONS_SETUP.md`
Detailed guide for GitHub Actions secrets:
- OIDC setup (recommended)
- Access key setup (alternative)
- IAM role/policy configuration
- Troubleshooting and security best practices

### 7. `.dockerignore`
Optimizes Docker build by excluding:
- Git files
- Python cache
- IDE files
- Local data directories
- Notebooks

### 8. `validate_setup.sh`
Validation script to check:
- Required files exist
- Docker is running
- AWS CLI is configured
- ECR repository exists
- App configuration is correct

## Files Modified

### 1. `app.py`
**Key changes:**
- Moved app creation to module level: `app = create_app(...)`
- Exposed WSGI server object: `server = app.server`
- Updated `if __name__ == "__main__"` block to bind to `0.0.0.0:8050`
- App can now be imported by gunicorn: `gunicorn app:server`

**Before:**
```python
if __name__ == "__main__":
    app = create_app(use_sample=USE_SAMPLE_DATA)
    app.run(debug=True)
```

**After:**
```python
app = create_app(use_sample=USE_SAMPLE_DATA)
server = app.server

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=True)
```

### 2. `data_prep.py`
**Key changes:**
- Enhanced comments explaining public S3 access
- Clarified that NO AWS credentials are required
- Documented memory-conscious streaming via pandas
- Emphasized use of HTTPS URLs for public S3 objects

**Key sections updated:**
- `S3_BUCKET_URL`: Now clearly documented as public access
- `get_file_path()`: Explains HTTPS URL construction
- `read_csv_file()`: Details memory-conscious streaming, no boto3

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        GitHub Repository                     │
│  ┌──────────────┐  ┌────────────┐  ┌──────────────────┐    │
│  │   app.py     │  │ data_prep  │  │   visuals.py     │    │
│  │ (server obj) │  │    .py     │  │                  │    │
│  └──────────────┘  └────────────┘  └──────────────────┘    │
│                                                              │
│  ┌──────────────┐  ┌────────────┐  ┌──────────────────┐    │
│  │ Dockerfile   │  │requirements│  │ deploy_to_ecr.sh │    │
│  └──────────────┘  └────────────┘  └──────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ git push
                            ▼
         ┌──────────────────────────────────┐
         │    GitHub Actions Workflow       │
         │  ┌────────────────────────────┐  │
         │  │ 1. Checkout code           │  │
         │  │ 2. Configure AWS creds     │  │
         │  │ 3. Build Docker image      │  │
         │  │ 4. Push to ECR             │  │
         │  └────────────────────────────┘  │
         └──────────────────────────────────┘
                            │
                            ▼
              ┌──────────────────────┐
              │   Amazon ECR         │
              │  ┌────────────────┐  │
              │  │ usda-dashboard │  │
              │  │   :latest      │  │
              │  │   :git-sha     │  │
              │  └────────────────┘  │
              └──────────────────────┘
                            │
                            │ Pull image
                            ▼
              ┌──────────────────────┐
              │  AWS App Runner      │
              │  ┌────────────────┐  │
              │  │  Container     │  │
              │  │  Port: 8080    │  │
              │  │  2-4 GB RAM    │  │
              │  └────────────────┘  │
              │         │            │
              │         ▼            │
              │  Public HTTPS URL    │
              └──────────────────────┘
                            │
                            │ Reads data from
                            ▼
              ┌──────────────────────┐
              │   Amazon S3 (PUBLIC) │
              │  ┌────────────────┐  │
              │  │  CSV datasets  │  │
              │  │ (public read)  │  │
              │  └────────────────┘  │
              └──────────────────────┘
```

## Key Design Decisions

### 1. Public S3 Access (No IAM Credentials)
- **Why**: Simplifies deployment, no secret management
- **How**: Pandas reads HTTPS URLs directly
- **Benefit**: Container doesn't need AWS credentials at runtime

### 2. Gunicorn with 2 Workers
- **Why**: Balance between concurrency and memory usage
- **Alternative**: Can increase for higher traffic
- **Consideration**: Large datasets mean memory-intensive workers

### 3. Port 8080
- **Why**: App Runner's default, cloud-native standard
- **Local dev**: Still uses 8050 (doesn't conflict)

### 4. Memory-Conscious Loading
- **Why**: Datasets are large (hundreds of MB)
- **How**: Data loaded in functions, not at module import
- **Future**: Consider caching with `@lru_cache`

### 5. GitHub Actions with OIDC
- **Why**: More secure than long-lived access keys
- **Fallback**: Access keys documented as alternative
- **Benefit**: No credential rotation needed

## Deployment Workflow

### Option 1: Manual Deployment (Script)

```bash
# 1. Edit deploy_to_ecr.sh with your AWS account ID and region
vim deploy_to_ecr.sh

# 2. Make executable
chmod +x deploy_to_ecr.sh

# 3. Run
./deploy_to_ecr.sh

# 4. Go to App Runner console and deploy
```

### Option 2: GitHub Actions (Automated)

```bash
# 1. Set up GitHub secrets (see GITHUB_ACTIONS_SETUP.md)
# 2. Push to main branch
git add .
git commit -m "Setup AWS deployment"
git push origin main

# 3. Image automatically pushed to ECR
# 4. Optionally triggers App Runner deployment
```

## Environment Variables

The app respects these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_S3` | `True` | Load data from S3 (vs local) |
| `S3_BUCKET_URL` | (hardcoded) | Base HTTPS URL for S3 data |
| `USE_SAMPLE_DATA` | Set in code | Use smaller dataset for dev |
| `PORT` | `8080` | Port for web server |

Set in App Runner service configuration:
```bash
S3_BUCKET_URL=https://your-bucket.s3.region.amazonaws.com/path
USE_S3=True
```

## Cost Estimates (AWS)

Based on 2 vCPU, 4 GB RAM configuration:

- **App Runner**: ~$50-100/month for continuous running
  - Can reduce by setting min instances to 0 (pay per request)
  
- **ECR**: ~$0.10/GB/month for storage
  - Image size: ~500 MB after build

- **S3 (Public)**: ~$0.023/GB/month + data transfer
  - Data transfer OUT is free for first 100 GB/month

- **Data Transfer**: Mostly free (S3 to App Runner in same region)

**Total estimate**: $50-150/month depending on traffic

## Testing Checklist

Before deploying to production:

- [ ] Local Python run works: `python app.py`
- [ ] Local Docker build succeeds: `docker build -t usda-dashboard .`
- [ ] Local Docker run works: `docker run -p 8080:8080 usda-dashboard`
- [ ] App accessible at `http://localhost:8080`
- [ ] S3 data loads correctly
- [ ] No AWS credentials needed
- [ ] Gunicorn serves properly: `gunicorn app:server --bind 0.0.0.0:8080`
- [ ] ECR repository created
- [ ] deploy_to_ecr.sh configured with correct account ID
- [ ] GitHub secrets configured (if using Actions)

## Troubleshooting

### Docker build fails
```bash
# Check Dockerfile syntax
docker build --no-cache -t usda-dashboard .

# Check requirements.txt
pip install -r requirements.txt
```

### Can't connect to ECR
```bash
# Re-authenticate
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com
```

### App crashes on App Runner
- Check CloudWatch Logs in App Runner console
- Verify environment variables are set
- Check memory allocation (increase to 4 GB)
- Test locally with same config

### S3 data doesn't load
- Verify bucket URL is correct
- Check S3 bucket has public read permissions
- Test URL in browser: should download CSV
- Check CloudWatch Logs for error messages

## Next Steps

1. **Test locally**: Build and run Docker container
2. **Create ECR repo**: `aws ecr create-repository --repository-name usda-dashboard`
3. **Push first image**: Run `./deploy_to_ecr.sh`
4. **Create App Runner service**: Follow README instructions
5. **Configure environment variables**: Set S3_BUCKET_URL if different
6. **Monitor**: Check CloudWatch Logs for any issues
7. **Optimize**: Tune workers, memory based on traffic
8. **Set up CI/CD**: Configure GitHub Actions for automatic deployments

## References

- [AWS App Runner Documentation](https://docs.aws.amazon.com/apprunner/)
- [Amazon ECR Documentation](https://docs.aws.amazon.com/ecr/)
- [Gunicorn Documentation](https://docs.gunicorn.org/)
- [Dash Deployment Guide](https://dash.plotly.com/deployment)
- [GitHub Actions AWS Integration](https://github.com/aws-actions)

## Support

For issues or questions:
1. Check CloudWatch Logs in App Runner
2. Review README.md and GITHUB_ACTIONS_SETUP.md
3. Run `./validate_setup.sh` for local checks
4. Check GitHub Issues (if repo is public)

---

**Created**: December 2025  
**Last Updated**: December 2025  
**Deployment Target**: AWS App Runner with ECR  
**Status**: Ready for deployment
