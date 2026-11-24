# QueueSense --- Technical Architecture

**Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge  
**Author:** J Nikhil (`JNikhil11`)  
**Target AWS Region:** `ap-southeast-2` (Sydney)  

---

## 1. System Architecture Overview

QueueSense employs a cloud-native, serverless architecture that minimizes cloud operational costs, auto-scales during intense mealtime rushes, and adheres strictly to AWS Free Tier boundaries.

```
                           +---------------------------+
                           |   Student Mobile Client   |
                           |   (React 18 + TypeScript) |
                           +-------------+-------------+
                                         |
                                         v
                           +---------------------------+
                           |  AWS Amplify / S3 Hosting |
                           |  (Static Web Assets)      |
                           +-------------+-------------+
                                         |
                                         v
                           +---------------------------+
                           |  Amazon API Gateway       |
                           |  (HTTP API v2 with CORS)  |
                           +-------------+-------------+
                                         |
       +---------------------------------+---------------------------------+
       |                 |               |               |                 |
       v                 v               v               v                 v
+--------------+  +--------------+  +--------------+  +--------------+  +--------------+
|   Health     |  | GetLocations |  |   GetQueue   |  | SubmitReport |  | Recommend    |
|   Lambda     |  |   Lambda     |  |   Lambda     |  |   Lambda     |  |   Lambda     |
+--------------+  +--------------+  +--------------+  +--------------+  +--------------+
                                         |
                                         v
                           +---------------------------+
                           |   Amazon DynamoDB         |
                           |   Single-Table Storage    |
                           |   (Pay-Per-Request Mode)  |
                           +---------------------------+
                                         |
                                         v
                           +---------------------------+
                           |   Amazon CloudWatch       |
                           |   (Structured Logs)       |
                           +---------------------------+
```

---

## 2. Component Details

### 2.1 Frontend Tier
- **Framework:** React 18 with TypeScript in strict mode.
- **Build System:** Vite 5 for fast builds.
- **Styling:** Tailwind CSS with custom neon accents (`#39F58A`, `#20C8FF`, `#761D43`), dark obsidian canvas, and Space Grotesk / Inter / IBM Plex Mono typography.
- **State Management:** Reactive component state with dual-mode API client (switches seamlessly between live AWS API and offline mock fixtures).

### 2.2 API Tier: Amazon API Gateway HTTP API
- **Protocol:** HTTP API (v2) provides lower latency (sub-10ms) and ~70% lower cost than REST APIs.
- **CORS:** Configured for cross-origin access with scoped HTTP methods (`GET`, `POST`, `OPTIONS`), allowing `Content-Type`, `Authorization`, `X-Idempotency-Key`, `X-Device-ID`, and `X-Client-Instance-ID`.
- **Throttling:** Default route burst 100, rate 50 req/sec; sensitive submission route (`POST /locations/{id}/reports`) throttled to burst 20, rate 10 req/sec.
- **Access Logging:** Dedicated CloudWatch LogGroup (`/aws/apigateway/queuesense-api-${Environment}`) with structured JSON logging of operational metrics (`requestId`, `ip`, `latency`, `integrationLatency`, `status`) with 30-day retention.
- **Payload Validation:** Handled within Lambda to keep API configuration simple and portable.

### 2.3 Compute Tier: AWS Lambda
- **Runtime:** Python 3.12 (AWS Lambda standard).
- **Architecture:** x86_64.
- **Memory:** 256 MB per function (optimized for low cold-start latency under 150ms).
- **Concurrency Ceilings:** Strict `ReservedConcurrentExecutions` configured per function (10 to 50, totaling 190 across the stack), reserving > 800 unreserved concurrent executions for account safety.
- **Observability:** Dedicated `AWS::Logs::LogGroup` per function with strict 30-day retention (`RetentionInDays: 30`).
- **Execution Roles:** Scoped least-privilege IAM policies without wildcard permissions; KMS decryption strictly conditioned on caller account, SSM service principal, and parameter encryption context.

### 2.4 Storage Tier: Amazon DynamoDB
- **Billing Mode:** `PAY_PER_REQUEST` (On-Demand), incurring zero idle charges.
- **Single-Table Design (`QueueSense-Main`):**
  - **Location Metadata:** `PK: LOCATION#<id>`, `SK: METADATA`
  - **Queue Reports:** `PK: LOCATION#<id>`, `SK: REPORT#<timestamp>#<reportId>`
  - **Current Estimate:** `PK: LOCATION#<id>`, `SK: ESTIMATE#CURRENT`
- **Data Safety & Persistence:**
  - `PointInTimeRecoveryEnabled: true` providing 35-day continuous recovery.
  - `DeletionProtectionEnabled: true` preventing accidental table drops.
  - `SSESpecification: { SSEEnabled: true }` enforcing server-side encryption at rest.
  - `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain` guarding against accidental stack teardowns.
- **TTL Enabled:** Attribute `ttl` automatically purges raw reports older than 7 days; application logic enforces independent logical cutoffs ($\le 60$ min for estimates, $\le 14$ days for historical trends).

### 2.5 Frontend Delivery: Amazon S3 & CloudFront
- **Private S3 Bucket:** Sealed with `BlockPublicAcls`, `BlockPublicPolicy`, `IgnorePublicAcls`, `RestrictPublicBuckets`, and `BucketOwnerEnforced`.
- **Versioning & Lifecycle:** Object versioning enabled with a 30-day non-current version expiration lifecycle rule.
- **Origin Access Control (OAC):** SigV4-authenticated read-only access strictly restricted to the CloudFront distribution ARN.
- **Security Headers:** Managed `ResponseHeadersPolicy` injects HSTS (`max-age=63072000; includeSubdomains; preload`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and Content Security Policy (CSP).

### 2.6 Observability & Incident Detection: Amazon CloudWatch
- Centralized, structured JSON log streams per Lambda function and API Gateway stage with finite 30-day retention.
- Automated CloudWatch alarms for operational anomaly detection:
  - `Api5xxAlarm`: HTTP 5xx error rate monitoring.
  - `SubmitReportErrorsAlarm`: Ingestion pipeline error monitoring.
  - `DynamoDBThrottledRequestsAlarm`: On-demand capacity throttle detection.
  - `QueueReadLatencyAlarm`: Read-path degradation detection (> 3000ms duration).

---

## 3. Regional Deployment & Latency Considerations

QueueSense infrastructure is authored with dynamic CloudFormation intrinsics (`${AWS::Region}`, `${AWS::AccountId}`) and contains zero hardcoded regions or account numbers.

- **Configured Target Region:** `ap-southeast-2` (Sydney, Australia) — Default Challenge submission region.
- **Alternative Regional Target:** `ap-south-1` (Mumbai, India) — Recommended for live physical campus deployment at IIT Bombay.
- **Latency & Performance Comparison:**
  - Static Frontend Assets: Sub-10ms globally due to CloudFront edge points of presence in Mumbai, Pune, Delhi, Bangalore, and Chennai.
  - API Gateway RTT from IIT Bombay:
    - `ap-south-1` (Mumbai): ~15–30ms network round-trip.
    - `ap-southeast-2` (Sydney): ~120–150ms network round-trip.
  - Service Availability & Cost: Both regions support all required serverless primitives (HTTP API v2, Python 3.12 Lambda, DynamoDB on-demand, Cognito User Pools, CloudWatch Alarms) at identical AWS Free Tier terms. Re-targeting between regions is a zero-code parameter change during deployment.

