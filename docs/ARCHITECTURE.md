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
- **CORS:** Configured for cross-origin access with scoped HTTP methods (`GET`, `POST`, `OPTIONS`).
- **Payload Validation:** Handled within Lambda to keep API configuration simple and portable.

### 2.3 Compute Tier: AWS Lambda
- **Runtime:** Python 3.12 (AWS Lambda standard).
- **Architecture:** x86_64.
- **Memory:** 256 MB per function (optimized for low cold-start latency under 150ms).
- **Execution Roles:** Scoped least-privilege IAM policies (`DynamoDBReadPolicy`, `DynamoDBCrudPolicy`).

### 2.4 Storage Tier: Amazon DynamoDB
- **Billing Mode:** `PAY_PER_REQUEST` (On-Demand), incurring zero idle charges.
- **Single-Table Design (`QueueSense-Main`):**
  - **Location Metadata:** `PK: LOCATION#<id>`, `SK: METADATA`
  - **Queue Reports:** `PK: LOCATION#<id>`, `SK: REPORT#<timestamp>#<reportId>`
  - **Current Estimate:** `PK: LOCATION#<id>`, `SK: ESTIMATE#CURRENT`
- **TTL Enabled:** Attribute `ttl` automatically purges raw reports older than 7 days, preventing database bloat while maintaining fresh history.

### 2.5 Observability: Amazon CloudWatch
- Centralized log streams per Lambda function.
- Structured JSON log entries without exposing student identifiers or authorization credentials.

