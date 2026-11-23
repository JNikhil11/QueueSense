#!/usr/bin/env bash
set -euo pipefail

# ==========================================================
# QueueSense Frontend Deployment Script (Bash)
# Target AWS Region: ap-southeast-2 (Sydney)
# ==========================================================

BUCKET_NAME="${1:-${FRONTEND_BUCKET_NAME:-}}"
DISTRIBUTION_ID="${2:-${CLOUDFRONT_DISTRIBUTION_ID:-}}"
AWS_REGION="${AWS_REGION:-ap-southeast-2}"

if [ -z "$BUCKET_NAME" ]; then
    echo "Error: BUCKET_NAME is required as argument 1 or FRONTEND_BUCKET_NAME env var." >&2
    echo "Usage: ./scripts/deploy-frontend.sh <bucket-name> [distribution-id]" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"
DIST_DIR="$FRONTEND_DIR/dist"

echo "=== [1/3] Building production assets ==="
cd "$FRONTEND_DIR"
npm run build

echo "=== [2/3] Syncing dist/ to s3://$BUCKET_NAME/ ==="
aws s3 sync "$DIST_DIR" "s3://$BUCKET_NAME/" --delete --region "$AWS_REGION"

if [ -n "$DISTRIBUTION_ID" ]; then
    echo "=== [3/3] Invalidating CloudFront cache ($DISTRIBUTION_ID) ==="
    aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*"
else
    echo "=== [3/3] Skipped cache invalidation (no distribution ID provided) ==="
fi

echo "Deployment complete!"
