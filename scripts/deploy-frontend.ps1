<#
.SYNOPSIS
    QueueSense Frontend Deployment Script (PowerShell)
    Target AWS Region: ap-southeast-2 (Sydney)
.DESCRIPTION
    Builds the production Vite bundle and syncs static assets to the private S3 bucket,
    followed by a CloudFront cache invalidation.
    Prerequisites:
    - AWS CLI installed and configured (`aws configure`)
    - Node.js & npm installed
#>

param (
    [string]$BucketName = $env:FRONTEND_BUCKET_NAME,
    [string]$DistributionId = $env:CLOUDFRONT_DISTRIBUTION_ID,
    [string]$AwsRegion = "ap-southeast-2"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "QueueSense Frontend Deployment — Production Hardening" -ForegroundColor Green
Write-Host "Target AWS Region: $AwsRegion" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

if (-not $BucketName) {
    Write-Host "Error: FRONTEND_BUCKET_NAME parameter or environment variable is required." -ForegroundColor Red
    Write-Host "Example usage: .\scripts\deploy-frontend.ps1 -BucketName 'queuesense-frontend-prod-123456789' -DistributionId 'E12345EXAMPLE'" -ForegroundColor Yellow
    exit 1
}

# 1. Verify build artifacts
$DistPath = Join-Path $PSScriptRoot "..\frontend\dist"
$FrontendDir = Join-Path $PSScriptRoot "..\frontend"

Write-Host "`n[1/3] Building production bundle (tsc && vite build)..." -ForegroundColor Yellow
Push-Location $FrontendDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Build failed! Please resolve TypeScript / build errors before deploying." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

# 2. Sync to S3
Write-Host "`n[2/3] Syncing dist/ assets to s3://$BucketName/ in region $AwsRegion..." -ForegroundColor Yellow
aws s3 sync $DistPath "s3://$BucketName/" --delete --region $AwsRegion

if ($LASTEXITCODE -ne 0) {
    Write-Host "S3 sync failed. Check AWS credentials and bucket permissions." -ForegroundColor Red
    exit 1
}

# 3. Invalidate CloudFront Cache (if DistributionId provided)
if ($DistributionId) {
    Write-Host "`n[3/3] Invalidating CloudFront cache on distribution $DistributionId..." -ForegroundColor Yellow
    aws cloudfront create-invalidation --distribution-id $DistributionId --paths "/*"
} else {
    Write-Host "`n[3/3] CloudFront distribution ID not provided. Skipped cache invalidation." -ForegroundColor Gray
}

Write-Host "`nFrontend deployment completed successfully!" -ForegroundColor Green

