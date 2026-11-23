# QueueSense — Real-Time Campus Food Queue Intelligence

> **Know the queue before you join it.**  
> A lightweight, privacy-preserving campus food-queue intelligence system powered by AWS serverless technologies.

**Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge  
**Author:** J Nikhil ([@JNikhil11](https://github.com/JNikhil11))  
**Target Region:** `ap-southeast-2` (Sydney)  
**Campus Context:** IIT Bombay (Hostel Messes & Campus Canteens)  

---

## 1. Problem Statement

At university campuses during peak lunch and dinner hours, hundreds of students converge simultaneously on dining halls and food courts. Students routinely walk across campus without knowing whether a mess has a 2-minute line or a 25-minute bottleneck, resulting in lost study time, severe dining congestion, and frustration.

**QueueSense** addresses this challenge through crowdsourced queue observations, mathematical time-decay estimation, statistical outlier filtering, and transparent evidence scoring.

---

## 2. Key Capabilities

- **Real-Time Congestion Visibility:** Instant access to estimated waiting times and queue sizes across 10 student-sourced IIT Bombay messes and canteens (and configurable for VIT-AP).
- **Evidence-First Transparency:** Estimates display exact data freshness (`LIVE <7m`, `RECENT <20m`, `AGING DATA`), report count, and confidence levels.
- **Cold-Start Recommendation Protection:** Recommends less crowded dining outlets only when supported by at least 3 fresh reports (within 20m) and 50%+ confidence.
- **Historical Best-Time-To-Go Intelligence:** Synthesizes past 14 days of crowdsourced data into 24-hour curves, highlighting peak rush and quietest meal hours.
- **Durable Fail-Closed Persistence:** Eliminates silent mock fallbacks in production. If DynamoDB is unreachable, fails closed with HTTP 500 `PERSISTENCE_FAILED`.
- **Server-Side Idempotency & Throttling:** Client `X-Idempotency-Key` deduplication and privacy-preserving anonymous rate limiting (HMAC-SHA256 client hash).
- **Zero Personal Data Collected:** No student registration, student IDs, phone numbers, or IP logging.
- **Dual-Mode Architecture:** Explicit separation between `production` (strictly cloud-backed) and `demo` (local browser simulation).
- **Protected Administrator Audit Stream:** Secured with API key / bearer token authorization and automated statistical outlier flagging.

---

## 3. Architecture

```
[ Student Browser / Mobile ] 
           │
           ▼
[ Amazon CloudFront (CDN + HTTPS) ] ──(OAC)──► [ Amazon S3 Private Bucket ]
           │
           ▼
[ Amazon API Gateway (HTTP API v2) ]
           │
     ┌─────┴───────────────┬─────────────────────┬─────────────────────┐
     ▼                     ▼                     ▼                     ▼
[ Health & Outlets ]   [ Report Submission ]  [ Recommendations ]   [ Historical Trends ]
(Python 3.12 Lambda)   (Python 3.12 Lambda)   (Python 3.12 Lambda)  (Python 3.12 Lambda)
     │                     │                     │                     │
     └─────────────────────┼─────────────────────┴─────────────────────┘
                           ▼
              [ Amazon DynamoDB Single-Table ]
              (Pay-Per-Request Mode + 7-Day TTL)
                           │
                           ▼
               [ Amazon CloudWatch Logs ]
```

### AWS Services Used
- **Amazon CloudFront & Amazon S3:** Static web hosting with Origin Access Control (OAC), HTTPS redirection, and SPA client routing.
- **Amazon API Gateway (HTTP API v2):** Low-latency, cost-effective serverless API routing with configured CORS and route-level throttling.
- **AWS Lambda (Python 3.12):** Microservices for queue calculation, report submission, recommendation scoring, historical trend aggregation, and admin auditing.
- **Amazon DynamoDB:** Single-table storage design (`QueueSense-Main`) using on-demand capacity and 7-day TTL on raw observations.
- **Amazon CloudWatch:** Real-time log capture, sanitized error tracing, and operational metrics.
- **AWS SAM:** Infrastructure as code for reproducible, least-privilege cloud deployments.

---

## 4. Documentation & Verification Registers

- [Outlet Data Provenance Register](file:///d:/Projects%20-%20antigravity/CA%20IIT%20BOMBAY/AWS/docs/OUTLET_DATA_PROVENANCE.md): Full register of outlets, student-sourced citations, and ethical disclosures.
- [Production Hardening & Release Audit](file:///d:/Projects%20-%20antigravity/CA%20IIT%20BOMBAY/AWS/docs/RELEASE_READINESS.md): Verification matrix covering P0, P1, and P2 security, data integrity, and test results.
- [Production Cost Model](file:///d:/Projects%20-%20antigravity/CA%20IIT%20BOMBAY/AWS/docs/COST_MODEL.md): Pay-per-request pricing analysis for `ap-southeast-2` (Sydney) with zero idle cost.
- [API Specification](file:///d:/Projects%20-%20antigravity/CA%20IIT%20BOMBAY/AWS/docs/API.md): Detailed schemas for all HTTP API endpoints.

## 4. Mathematical Estimation Model

QueueSense uses a pure, explainable time-decay algorithm rather than opaque black-box models:

1. **Exponential Freshness Weighting:**  
   $$w_i = \exp\left(-\frac{t_i}{15\text{ min}}\right)$$  
   Reports older than 60 minutes decay to weight 0.

2. **Statistical Outlier Rejection:**  
   Calculates Median Absolute Deviation (MAD) for reports. Observations deviating by more than $3 \times \text{MAD}$ from the median are excluded from public estimates and flagged for administrator review.

3. **Multi-Factor Confidence Index:**  
   Combines report volume (up to 45%), recency of newest report (up to 35%), and agreement between reporting students (up to 20%).

4. **Honest Recommendation Policy:**  
   If all campus outlets have stale or insufficient observations, the engine honestly returns *"Not enough recent queue reports across campus to make a reliable recommendation yet."*

---

## 5. Repository Structure

```
.
├── backend/
│   ├── functions/
│   │   ├── admin/                # Audit feed handler
│   │   ├── get_locations/        # List outlets & estimates
│   │   ├── get_queue/            # Detailed outlet queue & history
│   │   ├── get_recommendations/  # Smart recommendation engine
│   │   ├── health/               # API health check
│   │   └── submit_report/        # Observation ingestion & validation
│   ├── shared/
│   │   ├── database.py           # DynamoDB access & memory fallback
│   │   ├── prediction.py         # Pure mathematical queue engine
│   │   ├── response.py           # HTTP API JSON envelopes & CORS
│   │   └── validation.py         # Input sanitization & bounds checking
│   └── tests/                    # 23 automated Python test cases
├── frontend/
│   ├── src/
│   │   ├── components/           # Navbar, Hero, Cards, Modals, Badges
│   │   ├── services/             # API client with dual live/mock support
│   │   ├── styles/               # Tailwind CSS & custom design tokens
│   │   └── types/                # TypeScript schemas
│   └── dist/                     # Optimized production web bundle
├── infrastructure/
│   └── template.yaml             # AWS SAM Serverless Infrastructure Template
└── docs/                         # PRD, Architecture, API, Security, Design System
```

---

## 6. Getting Started

### Local Frontend Development
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000`. The frontend runs in offline simulation mode out-of-the-box with preloaded seed observations.

### Running Backend Tests
```bash
python -m pytest backend/tests -v
```

### Running Frontend Tests & Production Build
```bash
cd frontend
npm run test
npm run build
```

---

## 7. Cloud Deployment via AWS SAM

```bash
# 1. Validate SAM template
sam validate --template infrastructure/template.yaml

# 2. Build deployment package
sam build --template infrastructure/template.yaml

# 3. Deploy to AWS ap-southeast-2
sam deploy --guided \
  --stack-name queuesense-prod \
  --region ap-southeast-2 \
  --capabilities CAPABILITY_IAM
```

Update `frontend/.env.production` with the resulting `HttpApiUrl` and build the frontend for deployment to AWS Amplify Hosting or S3 static hosting.

---

## 8. License

This project is released under the MIT Open Source License.

