# QueueSense --- Deployment Guide

**Target AWS Region:** `ap-southeast-2` (Sydney)  
**Author:** J Nikhil (`JNikhil11`)  
**Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge  

---

## 1. Prerequisites

1. **AWS CLI:** Authenticated via `aws configure` or `aws login` (SSO/IAM).
2. **AWS SAM CLI:** Version 1.120+ installed (`sam --version`).
3. **Node.js & npm:** Node v20+ / v24+ and npm v10+.
4. **Python:** Version 3.12 (`python --version`).

---

## 2. Backend Deployment via AWS SAM

The backend infrastructure is defined in `infrastructure/template.yaml`.

### Step 2.1: Validate SAM Template
```bash
sam validate --template infrastructure/template.yaml
```

### Step 2.2: Build SAM Artifacts
```bash
sam build --template infrastructure/template.yaml
```

### Step 2.3: Guided Deployment (First Time)
Run guided deployment to set stack name and region parameters:
```bash
sam deploy --guided \
  --stack-name queuesense-backend-prod \
  --region ap-southeast-2 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=prod TableName=QueueSense-Main
```

When prompted:
- Allow SAM CLI to create IAM roles: `Y`
- Confirm changes before deploy: `Y`
- Allow unauthenticated HTTP API access to `/health`, `/locations`, `/recommendations`: `Y`

### Step 2.4: Capture Outputs
Upon completion, the terminal displays the CloudFormation outputs:
- `HttpApiUrl`: `https://{api-id}.execute-api.ap-southeast-2.amazonaws.com`
- `DynamoDBTableName`: `QueueSense-Main-prod`

---

## 3. Frontend Deployment via AWS Amplify or S3 Static Hosting

### Step 3.1: Configure API URL
Create `frontend/.env.production` containing the HTTP API Gateway URL from Step 2.4:
```bash
VITE_API_URL=https://{api-id}.execute-api.ap-southeast-2.amazonaws.com
```

### Step 3.2: Build Production Assets
```bash
cd frontend
npm run build
```
This generates the optimized bundle in `frontend/dist/`.

### Step 3.3: Deploy to AWS Amplify Hosting
Option A (Amplify CLI / Console):
1. Connect GitHub repository `https://github.com/JNikhil11/QueueSense`.
2. Configure build settings:
   - App root: `frontend`
   - Build command: `npm run build`
   - Base directory: `dist`
3. Deploy to production branch `master` or `main`.

Option B (S3 + CloudFront Static Hosting):
```bash
aws s3 sync frontend/dist/ s3://queuesense-frontend-prod-ap-southeast-2/ --delete
```

---

## 4. Local Testing & Offline Simulation

QueueSense includes a dual-mode API client that runs completely offline with seed fixtures if AWS credentials expire or during offline evaluation:
```bash
cd frontend
npm run dev
```
Open `http://localhost:3000` in your browser. The UI indicates `OFFLINE SIMULATION • DEMO FIXTURES` with full report-submission and real-time calculation functionality.

