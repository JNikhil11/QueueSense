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
- **Access Logging:** Dedicated CloudWatch LogGroup (`/aws/apigateway/queuesense-api-${Environment}`) with structured JSON logging of operational metrics (`requestId`, `requestTime`, `httpMethod`, `routeKey`, `status`, `latency`, `integrationLatency`) with 30-day retention. Raw client IP addresses are strictly excluded in accordance with the project's zero-PII privacy architecture.
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
- **Edge SPA Routing Function:** A CloudFront Function (`SpaRoutingFunction` on `viewer-request`) intercepts incoming requests:
  - Extensionless route paths (`/`, `/admin`, `/locations/123`) are rewritten to `/index.html` with zero origin roundtrip, ensuring seamless client-side route navigation and page refresh.
  - Requests containing file extensions (`.js`, `.css`, `.png`, `.mp4`) are passed directly to S3 without rewriting; missing assets return genuine HTTP 404 responses instead of masking errors with HTML.
  - S3 authorization failures return genuine HTTP 403 responses.
- **Security Headers:** Managed `ResponseHeadersPolicy` injects HSTS (`max-age=63072000; includeSubdomains; preload`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and Content Security Policy (CSP Level 3).

### 2.6 Identity & Administration: Amazon Cognito
- **User Pool:** Admin-only user creation (`AllowAdminCreateUserOnly: true`) prevents public registration.
- **Mandatory MFA:** `MfaConfiguration: "ON"` with `SOFTWARE_TOKEN_MFA` (TOTP), enforcing two-factor authentication for all administrative accounts.
- **Account Protection:** `PreventUserExistenceErrors: ENABLED` masks user existence to defend against user enumeration attacks.
- **Token Hygiene:** Explicit 1-hour access/ID token validity and 30-day refresh token validity.

### 2.7 Observability & Incident Detection: Amazon CloudWatch
- Centralized, structured JSON log streams per Lambda function and API Gateway stage with finite 30-day retention.
- Automated CloudWatch alarms for operational anomaly detection, wired to an SNS topic (`OperationalAlertsTopic`):
  - `Api5xxAlarm`: HTTP 5xx error rate monitoring ($\ge 5$ errors in 5 min).
  - `SubmitReportErrorsAlarm`: Ingestion pipeline error monitoring ($\ge 3$ errors in 5 min).
  - `DynamoDBThrottledRequestsAlarm`: On-demand capacity throttle detection ($\ge 1$ throttled request in 5 min).
  - `QueueReadLatencyAlarm`: Read-path degradation detection (> 3000ms duration).
- Conditional email subscription (`OperationalAlertsSubscription`) automatically created when `AlarmNotificationEmail` is supplied at deployment time.

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

---

## 4. FinOps & Operational Cost Modeling

### 4.1 Low-Traffic Baseline Model (Normal Campus Dining Operations)
*Assumptions: 1,500 active campus diners; 15,000 reports submitted/month; 120,000 read requests/month; 50 MB total DynamoDB storage; 30-day log retention.*

| Service | Usage Metric & Pricing Formula | Free Tier Allowance | Estimated Monthly Cost |
|---|---|---|---|
| **AWS Lambda** | 135,000 invocations @ 150ms avg, 256 MB = 5,184 GB-sec | 1,000,000 invocations & 400,000 GB-sec free | **$0.00** (Within Free Tier) |
| **Amazon API Gateway** | 135,000 HTTP API calls ($1.00/million calls) | 1,000,000 calls free for first 12 months | **$0.00** ($0.14/mo after Year 1) |
| **Amazon DynamoDB** | 120,000 RRUs ($0.25/M) + 15,000 WRUs ($1.25/M) + PITR (50 MB @ $0.20/GB) | 25 GB storage & 2.5M reads/writes free/mo | **$0.01** (PITR continuous backup) |
| **Amazon S3** | 100 MB static assets, 1,000 PUTs/month | 5 GB standard storage & 20,000 GETs free | **$0.00** (Within Free Tier) |
| **Amazon CloudFront** | 15 GB data transfer out + 150,000 requests | 1 TB data transfer & 10M requests free perpetually | **$0.00** (Within Free Tier) |
| **CloudFront Functions** | 150,000 viewer-request routing calls ($0.10/M) | 2,000,000 function invocations free/mo | **$0.00** (Within Free Tier) |
| **Amazon CloudWatch** | 8 log groups (~200 MB ingestion, 30-day retention) + 4 alarms | 5 GB ingestion & 10 custom alarms free | **$0.00** (Within Free Tier) |
| **Amazon Cognito** | 10 administrator accounts | 50,000 MAU free perpetually | **$0.00** (Within Free Tier) |
| **Total Baseline Monthly Cost** | — | — | **$0.01 / month** (under Free Tier); **~$0.15 - $0.30 / month** (standard pricing) |

### 4.2 High-Traffic & Sustained Abuse Scenario
*Attack Scenario: An adversary attempts 10,000,000 requests over 48 hours (~58 req/sec) targeting `POST /locations/{id}/reports`.*

* **Layer 1 Mitigation — API Gateway Throttling:**
  - Route throttle (Burst 20, Rate 10 req/s) caps admitted requests to $10 \text{ req/s} \times 172,800 \text{ s} \approx 1,728,000$ requests.
  - The remaining ~8,272,000 requests are rejected with HTTP 429 at the API Gateway edge.
  - **Billing Impact:** API Gateway bills for all evaluated requests (admitted and throttled) at $1.00 per million: $10\text{M} \times \$1.00/\text{M} = \mathbf{\$10.00}$.
* **Layer 2 Mitigation — Lambda Concurrency Ceilings:**
  - `SubmitReportFunction` has `ReservedConcurrentExecutions: 20`, capping maximum parallel compute and protecting account-wide capacity.
  - The 1,728,000 admitted requests execute in Lambda. The application-tier rate limiter rejects non-compliant requests within 5ms.
  - **Billing Impact:** $1,728,000 \times 0.005\text{s} \times 0.256\text{GB} = 2,211\text{ GB-seconds} \approx \$0.04$. Invocation fee: $1.728\text{M} \times \$0.20/\text{M} = \$0.35$. Total Lambda: $\mathbf{\$0.39}$.
* **Layer 3 Mitigation — Dual-Budget Database Protection:**
  - Campus NAT ceiling (30 req / 5 min = 0.1 req/s per subnet) limits DynamoDB write transactions to a maximum of ~17,280 writes: $17,280 \times \$1.25/\text{M} \approx \mathbf{\$0.02}$.
* **CloudWatch Ingestion:**
  - 1.728M log entries (~300 bytes each) = ~500 MB = $\mathbf{\$0.25}$.
* **Total Calculated Abuse Exposure:** $\mathbf{\approx \$10.66}$ over 48 hours.

### 4.3 Operational Cost Governance Caveats
1. **Concurrency vs Billing:** Reserved concurrency bounds *simultaneous parallel execution instances* to protect account quotas and prevent cascading system failure; it does *not* cap cumulative invocation counts over a calendar month.
2. **API Gateway Throttled Request Fees:** While HTTP 429 throttling prevents Lambda execution and database writes, API Gateway bills for evaluating incoming HTTP requests ($1.00/million).
3. **Account-Level Budget Enforcement:** A hard account-level financial cap requires configuring an AWS Budget in the AWS Billing Console with automated SNS alerts and IAM stop-actions, which must be provisioned in the live AWS account.

