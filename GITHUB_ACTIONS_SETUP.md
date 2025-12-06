# GitHub Actions Setup Guide

This guide explains how to configure GitHub Secrets for the automated ECR deployment workflow.

## Required GitHub Secrets

Before the GitHub Actions workflow can deploy to ECR, you need to configure authentication secrets in your GitHub repository.

### Option 1: OIDC Authentication (Recommended)

OIDC (OpenID Connect) is more secure as it doesn't require long-lived credentials.

**Required Secret:**
- `AWS_ROLE_TO_ASSUME`: ARN of the IAM role that GitHub Actions will assume

**Setup Steps:**

1. **Create an OIDC Provider in AWS:**
   ```bash
   aws iam create-open-id-connect-provider \
     --url https://token.actions.githubusercontent.com \
     --client-id-list sts.amazonaws.com \
     --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
   ```

2. **Create an IAM Role for GitHub Actions:**
   
   Create a trust policy file `github-trust-policy.json`:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_USERNAME/YOUR_REPO_NAME:*"
           }
         }
       }
     ]
   }
   ```
   
   Replace:
   - `YOUR_ACCOUNT_ID` with your AWS account ID
   - `YOUR_GITHUB_USERNAME` with your GitHub username
   - `YOUR_REPO_NAME` with your repository name (e.g., `Agricultural_Data_Analysis`)

   Create the role:
   ```bash
   aws iam create-role \
     --role-name GitHubActionsECRRole \
     --assume-role-policy-document file://github-trust-policy.json
   ```

3. **Attach ECR Permissions:**
   
   Create a policy file `ecr-permissions.json`:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": [
           "ecr:GetAuthorizationToken",
           "ecr:BatchCheckLayerAvailability",
           "ecr:GetDownloadUrlForLayer",
           "ecr:BatchGetImage",
           "ecr:PutImage",
           "ecr:InitiateLayerUpload",
           "ecr:UploadLayerPart",
           "ecr:CompleteLayerUpload"
         ],
         "Resource": "*"
       }
     ]
   }
   ```
   
   Attach the policy:
   ```bash
   aws iam put-role-policy \
     --role-name GitHubActionsECRRole \
     --policy-name ECRPushPolicy \
     --policy-document file://ecr-permissions.json
   ```

4. **Add Secret to GitHub:**
   
   - Go to your GitHub repository → Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `AWS_ROLE_TO_ASSUME`
   - Value: `arn:aws:iam::YOUR_ACCOUNT_ID:role/GitHubActionsECRRole`
   - Click "Add secret"

### Option 2: Access Keys (Alternative)

If you can't use OIDC, you can use access keys (less secure, requires credential rotation).

**Required Secrets:**
- `AWS_ACCESS_KEY_ID`: Your AWS access key ID
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret access key

**Setup Steps:**

1. **Create an IAM User:**
   ```bash
   aws iam create-user --user-name github-actions-ecr
   ```

2. **Attach ECR Policy:**
   ```bash
   aws iam attach-user-policy \
     --user-name github-actions-ecr \
     --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser
   ```

3. **Create Access Keys:**
   ```bash
   aws iam create-access-key --user-name github-actions-ecr
   ```
   
   Save the `AccessKeyId` and `SecretAccessKey` from the output.

4. **Add Secrets to GitHub:**
   
   - Go to your GitHub repository → Settings → Secrets and variables → Actions
   - Add two secrets:
     - Name: `AWS_ACCESS_KEY_ID`, Value: (your access key ID)
     - Name: `AWS_SECRET_ACCESS_KEY`, Value: (your secret access key)

5. **Update the Workflow:**
   
   In `.github/workflows/deploy-to-ecr.yml`, comment out the OIDC lines and uncomment the access key lines:
   
   ```yaml
   # Comment out:
   # role-to-assume: ${{ secrets.AWS_ROLE_TO_ASSUME }}
   
   # Uncomment:
   aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
   aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
   ```

## Optional Secrets

### Automatic App Runner Deployment

If you want the workflow to automatically trigger App Runner deployments:

1. **Get your App Runner service ARN:**
   ```bash
   aws apprunner list-services --region us-east-1
   ```

2. **Add the ARN as a secret:**
   - Name: `APP_RUNNER_SERVICE_ARN`
   - Value: `arn:aws:apprunner:us-east-1:123456789012:service/usda-dashboard/abc123`

3. **Uncomment the deployment step** in `.github/workflows/deploy-to-ecr.yml`

4. **Ensure your IAM role/user has App Runner permissions:**
   ```json
   {
     "Effect": "Allow",
     "Action": [
       "apprunner:StartDeployment",
       "apprunner:DescribeService"
     ],
     "Resource": "arn:aws:apprunner:*:*:service/usda-dashboard/*"
   }
   ```

## Testing the Workflow

1. Push to the `main` branch or trigger manually from the Actions tab
2. Go to your repository → Actions → "Deploy to Amazon ECR"
3. Watch the workflow run and check for errors
4. If successful, the image will be in ECR with both the git SHA tag and `latest` tag

## Troubleshooting

### "Error: Not authorized to perform sts:AssumeRoleWithWebIdentity"
- Check that the trust policy in your IAM role matches your repository name exactly
- Verify the OIDC provider is configured correctly

### "Error: Failed to push image to ECR"
- Ensure your IAM role/user has ECR push permissions
- Check that the ECR repository exists in the correct region

### "Error: Cannot access secrets"
- Verify secrets are named exactly as referenced in the workflow
- Secrets are case-sensitive

## Security Best Practices

1. **Use OIDC over access keys** whenever possible
2. **Limit IAM permissions** to only what's needed (ECR push, optionally App Runner)
3. **Use specific resource ARNs** in IAM policies instead of wildcards when possible
4. **Rotate access keys regularly** if using Option 2
5. **Don't commit secrets** to the repository - always use GitHub Secrets
6. **Review GitHub Actions logs** carefully - secrets are masked but still be cautious

## References

- [GitHub Actions OIDC with AWS](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [AWS ECR Push Permissions](https://docs.aws.amazon.com/AmazonECR/latest/userguide/security_iam_id-based-policy-examples.html)
- [AWS App Runner Deployment](https://docs.aws.amazon.com/apprunner/latest/dg/manage-deploy.html)
