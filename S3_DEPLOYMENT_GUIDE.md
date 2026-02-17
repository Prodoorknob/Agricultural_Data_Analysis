# S3 Deployment Guide

## Overview

The Agricultural Data Analysis dashboard now uses a **three-tier fallback strategy** for data fetching:

1. **Primary**: AWS S3 bucket (public, CORS-enabled)
2. **Fallback**: Local API proxy (`/api/data`)
3. **Fallback**: Return empty data (graceful degradation)

This guide explains what files need to be uploaded to S3 and how to configure CORS.

---

## S3 Bucket Configuration

### Bucket Details
- **Bucket Name**: `usda-analysis-datasets`
- **Region**: `us-east-2`
- **URL Pattern**: `https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets/partitioned_states/{FILENAME}`

### Bucket Settings Required

#### 1. **Public Access Configuration**
The bucket must allow public read access for browser-based fetches (CORS):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::usda-analysis-datasets/survey_datasets/partitioned_states/*"
    }
  ]
}
```

#### 2. **CORS Configuration**
Enable CORS to allow cross-origin requests from your domain:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<CORSConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <CORSRule>
    <AllowedOrigin>*</AllowedOrigin>
    <AllowedMethod>GET</AllowedMethod>
    <AllowedMethod>HEAD</AllowedMethod>
    <MaxAgeSeconds>3000</MaxAgeSeconds>
    <ExposedHeader>ETag</ExposedHeader>
    <AllowedHeader>*</AllowedHeader>
  </CORSRule>
</CORSConfiguration>
```

Or via AWS CLI:
```bash
aws s3api put-bucket-cors \
  --bucket usda-analysis-datasets \
  --cors-configuration file://cors.json
```

Where `cors.json` contains:
```json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedMethods": ["GET", "HEAD"],
      "AllowedHeaders": ["*"],
      "MaxAgeSeconds": 3000,
      "ExposeHeaders": ["ETag"]
    }
  ]
}
```

---

## Files to Upload to S3

### Path Structure
```
s3://usda-analysis-datasets/survey_datasets/partitioned_states/
├── AL.parquet
├── AK.parquet
├── AZ.parquet
├── ...
├── IN.parquet
├── ...
├── WY.parquet
└── NATIONAL.parquet
```

### Required State Parquet Files
Upload all state parquet files from `final_data/` directory:

```bash
# From the Agricultural_Data_Analysis directory
aws s3 cp final_data/ s3://usda-analysis-datasets/survey_datasets/partitioned_states/ \
  --recursive \
  --include "*.parquet" \
  --exclude "partitioned_*"
```

### File Details
- **File Format**: Apache Parquet (binary columnar format)
- **File Naming**: `{STATE_CODE}.parquet` (e.g., `IN.parquet`, `CA.parquet`)
- **Source Directory**: `/final_data/`
- **Total Files**: 51 (50 states + NATIONAL)

### Recommended S3 Upload Commands

#### Using AWS CLI
```bash
# Single file upload
aws s3 cp final_data/IN.parquet s3://usda-analysis-datasets/survey_datasets/partitioned_states/IN.parquet

# Batch upload all parquet files
for file in final_data/*.parquet; do
  filename=$(basename "$file")
  aws s3 cp "$file" "s3://usda-analysis-datasets/survey_datasets/partitioned_states/$filename"
done

# Bulk upload with AWS CLI
aws s3 sync final_data s3://usda-analysis-datasets/survey_datasets/partitioned_states/ \
  --exclude "*" \
  --include "*.parquet"
```

#### Using PowerShell (Windows)
```powershell
# Set AWS credentials first
Set-AWSCredential -AccessKey YOUR_ACCESS_KEY -SecretKey YOUR_SECRET_KEY -StoreAs default

$bucketName = "usda-analysis-datasets"
$s3Path = "survey_datasets/partitioned_states/"
$localDir = "final_data"

Get-ChildItem "$localDir" -Filter "*.parquet" | ForEach-Object {
    Write-S3Object -BucketName $bucketName `
        -Key "$s3Path$($_.Name)" `
        -File $_.FullName `
        -PublicReadOnly
}
```

---

## Deployment Checklist

- [ ] **AWS Account Setup**
  - [ ] AWS credentials configured locally
  - [ ] Appropriate IAM permissions (s3:PutObject, s3:PutBucketPolicy, s3:PutBucketCors)

- [ ] **S3 Bucket Configuration**
  - [ ] Bucket exists and is in `us-east-2` region
  - [ ] Bucket policy allows public read access
  - [ ] CORS configuration enabled
  - [ ] Block Public Access settings properly configured

- [ ] **File Upload**
  - [ ] All 51 parquet files uploaded to `partitioned_states/` folder
  - [ ] Files use correct naming: `{STATE_CODE}.parquet`
  - [ ] NATIONAL.parquet included for national-level data
  - [ ] Verify file count: `aws s3 ls s3://usda-analysis-datasets/survey_datasets/partitioned_states/ | grep parquet | wc -l`

- [ ] **Testing**
  - [ ] Test S3 fetch from browser console: `fetch('https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets/partitioned_states/IN.parquet')`
  - [ ] Verify CORS headers in response: Check for `Access-Control-Allow-Origin` header
  - [ ] Test dashboard loads data from S3
  - [ ] Check browser console for `[S3] ✓ Successfully fetched` messages
  - [ ] Verify fallback works: Temporarily break S3 URL and confirm API proxy kicks in

---

## Application Code Changes

The application has been updated to implement the S3-first fetch strategy:

### Key File: `web_app/src/utils/serviceData.ts`

**Changes Made:**
- Added S3 bucket URL constant: `https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets/partitioned_states`
- Refactored `fetchParquet()` to implement three-tier strategy
- Extracted `parseParquetBuffer()` for shared parsing logic
- Added detailed console logging with `[S3]`, `[Local API]`, `[Fetch]` prefixes for debugging

**Fetch Strategy:**
```typescript
// 1. Try S3 (primary)
//    → Success: Parse and return data
//    → Failure: Continue to fallback

// 2. Try Local API Proxy (fallback)
//    → Success: Parse and return data
//    → Failure: Continue to fallback

// 3. Return empty array (graceful degradation)
```

**Console Logging Examples:**
```
[S3] Attempting to fetch IN.parquet from S3...
[S3] ✓ Successfully fetched IN.parquet from S3

[S3] Attempting to fetch CA.parquet from S3...
[S3] File not found or access denied (404): CA.parquet
[Local API] Attempting to fetch partitioned_states/CA.parquet from local API...
[Local API] ✓ Successfully fetched partitioned_states/CA.parquet from local API
```

---

## Monitoring & Debugging

### S3 Fetch Success Indicators
- Browser console shows: `[S3] ✓ Successfully fetched {STATE}.parquet from S3`
- Network tab shows requests to `https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/`
- Response status: `200 OK`
- Response headers include: `Access-Control-Allow-Origin: *`

### Fallback Indicators
- Browser console shows: `[Local API] ✓ Successfully fetched...`
- Requests go to `/api/data?file=partitioned_states/{STATE}.parquet`
- Indicates S3 unreachable but local service restored functionality

### Failure Indicators
- Console error: `[Fetch] Failed to retrieve {FILE} from all sources`
- Dashboard shows "No data available" message
- Check S3 bucket configuration and CORS settings

---

## Cost Estimation

### S3 Storage
- ~51 parquet files × ~5-15 MB each ≈ 250-750 MB
- AWS S3 standard storage: ~$0.023 per GB/month
- **Monthly cost**: ~$0.01-0.02

### Data Transfer (Egress)
- First 1 GB free per month
- After: $0.09 per GB
- For ~5,000 users × 50 states = 250 GB/month → ~$22.50
- **Recommendation**: CloudFront CDN to reduce egress costs (~$0.085/GB)

### CloudFront Distribution (Optional but Recommended)
- Provides caching and reduces S3 egress costs
- Distribution cost: ~$0.085 per 10K requests (~$0.0085 per 1K requests)
- For 250K daily dashboard opens: ~$21 per month

---

## AWS Security Best Practices

1. **IAM Permissions**
   - Use least-privilege principle
   - Create specific IAM user for deployment with only s3:PutObject permission
   - Do NOT use root credentials

2. **Bucket Versioning**
   - Enable versioning to track file changes
   - Allows rollback if data is corrupted

3. **Server-Side Encryption**
   - Enable S3 default encryption (AES-256)
   - No additional cost for default encryption

4. **CloudTrail Logging**
   - Enable S3 data events to monitor access patterns
   - Helpful for debugging and security audits

---

## Rollback Strategy

If issues occur with S3:

1. **Temporary**: Delete CORS configuration or update bucket policy to require authentication
   - Dashboard automatically falls back to local API
   - No service disruption

2. **Permanent**: Revert `serviceData.ts` to old local-only implementation
   - Comment out S3 fetch, go directly to local API

```typescript
// Skip S3, use local API only
// async function fetchParquet(filename: string): Promise<any[]> {
//     const apiUrl = `/api/data?file=${encodeURIComponent(filename)}&t=${Date.now()}`;
//     ...
// }
```

---

## Support & Troubleshooting

### Common Issues

**Issue**: `[S3] File not found or access denied (403)`
- **Solution**: Verify S3 bucket policy allows public read access
- **Check**: AWS Console → S3 → Bucket → Permissions → Bucket Policy

**Issue**: CORS errors in browser console
- **Solution**: Update CORS configuration as shown above
- **Check**: AWS Console → S3 → Bucket → Permissions → CORS

**Issue**: Files missing in S3
- **Solution**: Re-upload missing parquet files
- **Verify**: `aws s3 ls s3://usda-analysis-datasets/survey_datasets/partitioned_states/`

**Issue**: Dashboard slow with S3 fetches
- **Solution**: Deploy CloudFront distribution in front of S3
- **Benefit**: Caching + CDN = faster loads + lower egress costs

---

## Next Steps

1. Configure S3 bucket (policy + CORS)
2. Upload all parquet files
3. Test fetch from browser DevTools
4. Monitor console logs during dashboard usage
5. (Optional) Set up CloudFront for production
