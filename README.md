# QueueSense — Real-Time Campus Food Queue Intelligence

> **Know the queue before you join it.**  
> A lightweight, privacy-preserving campus food-queue intelligence system powered by AWS serverless technologies.

**Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge  
**Author:** J Nikhil ([@JNikhil11](https://github.com/JNikhil11))  
**Target Region:** `ap-southeast-2` (Sydney)  
**Campus Context:** VIT-AP University (Messes & Canteens)  

---

## 1. Problem Statement

At university campuses during peak lunch and dinner hours, hundreds of students converge simultaneously on dining halls and food courts. Students routinely walk across campus without knowing whether a mess has a 2-minute line or a 25-minute bottleneck, resulting in lost study time, severe dining congestion, and frustration.

**QueueSense** addresses this challenge through crowdsourced queue observations, mathematical time-decay estimation, statistical outlier filtering, and transparent evidence scoring.

---

## 2. Key Capabilities

- **Real-Time Congestion Visibility:** Instant access to estimated waiting times and queue sizes across 5 campus messes and canteens.
- **Evidence-First Transparency:** Estimates display exact data freshness (`LIVE <7m`, `RECENT <20m`, `AGING DATA`), report count, and confidence levels.
- **Smart Recommendations:** Recommends less crowded dining outlets only when supported by fresh, high-confidence evidence.
- **Sub-5-Second Reporting:** Streamlined observation flow with presets for wait time and queue length.
- **Zero Personal Data Collected:** No student registration, student IDs, phone numbers, or device tracking.
- **Dual-Mode Architecture:** Seamlessly switches between live AWS API Gateway and offline local mock fixtures.
- **Administrator Audit Stream:** Campus-wide activity feed with automated statistical outlier flagging.

---

## 3. Architecture

```
[ Student Browser / Mobile ] 
           │
           ▼
[ AWS Amplify / S3 Static Web Hosting ]
           │
           ▼
[ Amazon API Gateway (HTTP API v2) ]
           │
     ┌─────┴───────────────┬─────────────────────┐
     ▼                     ▼                     ▼
[ Health & Outlets ]   [ Report Submission ]  [ Recommendations ]
(Python 3.12 Lambda)   (Python 3.12 Lambda)   (Python 3.12 Lambda)
     │                     │                     │
     └─────────────────────┼─────────────────────┘
                           ▼
              [ Amazon DynamoDB Single-Table ]
              (Pay-Per-Request Mode + TTL)
                           │
                           ▼
               [ Amazon CloudWatch Logs ]
```

### AWS Services Used
- **Amazon API Gateway (HTTP API):** Low-latency, cost-effective serverless API routing with CORS support.
- **AWS Lambda (Python 3.12):** Microservices for queue calculation, report submission, and recommendation scoring.
- **Amazon DynamoDB:** Single-table storage design (`QueueSense-Main`) using on-demand capacity and 7-day TTL on raw observations.
- **Amazon CloudWatch:** Real-time log capture and operational metrics.
- **AWS SAM:** Infrastructure as code for reproducible, least-privilege cloud deployments.

---

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

