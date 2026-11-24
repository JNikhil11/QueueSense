# QueueSense — Production Cost Model & Capacity Analysis

> **Target AWS Region:** `ap-southeast-2` (Sydney)  
> **Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge 2026  
> **Pricing Baseline:** AWS Published Rates (USD) as of Q4 2026

---

## 1. Executive Summary & Honest Pricing Policy

A common pitfall in student hackathons is claiming serverless architectures are "100% Free Forever with guaranteed $0.00 under all conditions."  
**QueueSense rejects this misleading claim.**

QueueSense is architected for **minimal near-zero idle baseline cost (~$0.05 - $0.55/month depending on Route 53 hosted zones and CloudWatch log ingestion)** by relying on AWS On-Demand pay-per-request serverless primitives rather than continuously provisioned EC2 instances, containers, or RDS clusters. Under judge evaluation and initial campus pilot usage, request-based compute and storage stay comfortably within the **AWS Always-Free Tier**. Workload estimates for standard traffic scenarios range from **~$0.03 to ~$4.42 per month** based on published rates.

However, serverless costs are inherently consumption-based and depend on actual traffic; costs do not automatically remain below any fixed dollar threshold without active account-level budget monitoring and governance.

---

## 2. Component Pricing Breakdown (`ap-southeast-2`)

### 2.1 Amazon DynamoDB (Single-Table, On-Demand Mode)
- **Write Request Units (WRU):** $1.25 per million write units
- **Read Request Units (RRU):** $0.25 per million read units
- **Storage:** 25 GB free tier, then $0.25 per GB-month
- **TTL Deletions:** $0.00 (Free of charge)
- *QueueSense Footprint:* Each report write consumes 2 WRU (one REPORT item, one current ESTIMATE item). Each reading call consumes 1-3 RRU. Single-table storage with 30-day TTL occupies under 50 MB for the entire campus.

### 2.2 AWS Lambda (Python 3.12, 256MB Architecture)
- **Always-Free Tier:** 1,000,000 free requests per month + 3,200,000 seconds of compute time (400,000 GB-seconds).
- **Invocations:** $0.20 per million requests beyond free tier.
- **Compute Duration:** $0.0000166667 per GB-second.
- *QueueSense Footprint:* Lambda average execution duration is **45ms** (cold start ~350ms, warm duration ~25ms). 1,000,000 invocations at 256MB consume only ~11,500 GB-seconds, completely covered by the 400,000 GB-second free tier.

### 2.3 Amazon API Gateway (HTTP API v2)
- **Price:** $1.00 per million requests for the first 300 million requests.
- **12-Month Free Tier:** 1,000,000 HTTP API calls/month free for the first 12 months of an AWS account.
- **Latency / Bandwidth:** HTTP API v2 provides ~60% latency reduction compared to REST APIs and has no minimum monthly fee.

### 2.4 Amazon CloudFront & Private S3 (Frontend Hosting)
- **CloudFront Free Tier:** 1 TB data transfer out per month + 10,000,000 HTTP/HTTPS requests per month (Always Free).
- **Amazon S3 (Standard Storage):** $0.025 per GB-month (bundle dist size: ~300 KB).
- **CloudFront Invalidation:** First 1,000 path invalidations per month are free ($0.00).

### 2.5 Baseline & Auxiliary Services (Idle Cost Reality)
- **Amazon Cognito User Pool:** First 50,000 monthly active users (MAUs) are free ($0.00). Administrator operator auth incurs $0.00/mo.
- **Amazon CloudWatch Logs:** Ingestion ($0.50/GB in `ap-southeast-2`) and storage ($0.03/GB-month). With QueueSense's 30-day retention policy and structured JSON logging, baseline idle logging is ~$0.02 to $0.05/month.
- **Amazon Route 53 (Optional Custom Domain):** $0.50 per hosted zone per month. If using the default CloudFront/API Gateway domains (`*.cloudfront.net`, `*.execute-api.ap-southeast-2.amazonaws.com`), this fee is $0.00.
- **Estimated Net Baseline at Zero Traffic:** **~$0.05/month** (without custom domain) to **~$0.55/month** (with custom domain).

---

## 3. Projected Monthly Workload Scenario Estimates

> [!NOTE]
> The figures below represent **illustrative workload scenario estimates** based on nominal traffic assumptions and standard published AWS pricing. They do not constitute guaranteed financial limits or spending caps.

### Scenario A — Judge Evaluation & Hackathon Demonstration (Light Volume)
- **Active Outlets:** 10 dining halls
- **Submissions:** 500 reports/month
- **API Read Requests:** 25,000 requests/month
- **Estimated Monthly Cost:** **$0.00** (under Year 1 Free Tier) / **~$0.03 / month** (under Standard Rates)

| Service | Volume | Free Tier Allowance | Billed Quantity | Standard Rate | Estimated Cost |
|---|---|---|---|---|---|
| DynamoDB Writes | 1,000 WRU | 25 GB & 25 WCU always free | 0 WRU | $1.25 / M | $0.00 |
| DynamoDB Reads | 30,000 RRU | 25 RCU always free | 0 RRU | $0.25 / M | $0.00 |
| Lambda Invocations | 26,000 calls | 1,000,000 calls always free | 0 calls | $0.20 / M | $0.00 |
| HTTP API Gateway | 26,000 calls | 1,000,000 calls free (12-mo) | 0.026 M (post-free-tier) | $1.00 / M | $0.00 (Year 1) / $0.03 (Standard) |
| CloudFront Data Transfer | 2 GB | 1,000 GB always free | 0 GB | $0.085 / GB | $0.00 |
| **Total Net Cost** | — | — | — | — | **$0.00 / month (Year 1 Free Tier); ~$0.03 / month (Standard Rates)** |

---

### Scenario B — Active Campus Pilot (1,000 Students, 2-Week Pilot)
- **Daily Active Students:** ~300 students
- **Observations:** 600 reports/day (18,000 reports/month)
- **API Reads (Polling & Detail Views):** 150,000 requests/month
- **Estimated Monthly Cost:** **~$0.27 / month** (under Standard Rates; **~$0.10 / month** under Year 1 Free Tier)

| Service | Volume | Free Tier Allowance | Billed Quantity (Standard) | Standard Rate | Cost (Standard) | Cost (Year 1 Free Tier) |
|---|---|---|---|---|---|---|
| DynamoDB WRU | 36,000 writes | 25 GB storage free (On-Demand WRUs billed) | 0.036 M | $1.25 / M | $0.045 | $0.045 |
| DynamoDB RRU | 220,000 reads | 25 GB storage free (On-Demand RRUs billed) | 0.220 M | $0.25 / M | $0.055 | $0.055 |
| Lambda Invocations | 168,000 calls | 1,000,000 calls & 400,000 GB-s Always-Free | 0 calls | $0.20 / M | $0.000 | $0.000 |
| HTTP API Gateway | 168,000 calls | 1,000,000 calls/mo free (first 12 months) | 0.168 M | $1.00 / M | $0.168 | $0.000 |
| CloudFront & S3 | 15 GB transfer | 1,000 GB transfer out Always-Free | 0 GB | $0.085 / GB | $0.000 | $0.000 |
| **Total Net Cost** | — | — | — | — | **~$0.27 / month** | **~$0.10 / month** |

*Arithmetic Verification:*
- **Standard Rates Total:**
  $$\$0.045 \text{ (DynamoDB WRU)} + \$0.055 \text{ (DynamoDB RRU)} + \$0.168 \text{ (API Gateway)} = \$0.268 \approx \mathbf{\$0.27 / \text{month}}$$
  *(Rounding to two decimal places: \$0.268 rounds to \$0.27, not \$0.28).*
- **Year 1 Free Tier Total:**
  $$\$0.045 \text{ (DynamoDB WRU)} + \$0.055 \text{ (DynamoDB RRU)} + \$0.000 \text{ (Lambda free)} + \$0.000 \text{ (API Gateway free)} = \$0.100 = \mathbf{\$0.10 / \text{month}}.$$
  *(Under the 12-Month AWS Free Tier, HTTP API Gateway [1M free], Lambda [1M free], and CloudFront [1TB free] allowances reduce their charges to \$0.00; the remaining \$0.10 arises solely from DynamoDB on-demand WRU [\$0.045] and RRU [\$0.055] pay-per-request consumption).*

---

### Scenario C — Full Campus Scale (10,000 Students, Semester-Long Operation)
- **Daily Active Students:** ~4,500 students
- **Observations:** 6,000 reports/day (180,000 reports/month)
- **API Reads:** 2,500,000 requests/month
- **Estimated Monthly Cost:** **~$4.42 / month**

| Service | Volume | Billed Quantity | Rate | Cost |
|---|---|---|---|---|
| DynamoDB WRU | 360,000 writes | 0.360 M | $1.25 / M | $0.450 |
| DynamoDB RRU | 3,800,000 reads | 3.800 M | $0.25 / M | $0.950 |
| Lambda Invocations | 2,680,000 calls | 1.680 M (above 1M free) | $0.20 / M | $0.336 (~$0.34) |
| HTTP API Gateway | 2,680,000 calls | 2.680 M | $1.00 / M | $2.680 |
| CloudFront & S3 | 80 GB transfer | 0 (Within 1TB always-free tier) | $0.00 | $0.00 |
| **Total Net Cost** | — | — | — | **~$4.42 / month** |

*Arithmetic Verification:* $\$0.450 \text{ (WRU)} + \$0.950 \text{ (RRU)} + \$0.336 \text{ (Lambda)} + \$2.680 \text{ (API Gateway)} = \$4.416 \approx \mathbf{\$4.42 / \text{month}}$.

---

## 4. Sustained Abuse Scenario & Best-Effort Throttling Reality

### 4.1 Illustrative Sustained 500 Req/Sec Abuse Scenario Estimate
*Illustrative Scenario: A hypothetical adversary continuously sends 500 requests/second targeting the API over an entire 30.9-day period ($30.9 \times 86,400\text{ s} \times 500\text{ req/s} \approx 1,335,360,000$ evaluated requests; or ~1,339,200,000 requests over 31 full days).*

* **Evaluated Request Charges:** $1,335.36\text{M requests} \times \$1.00/\text{M} \approx \mathbf{\$1,335.36}$ (or ~$1,339.20 for 31 full days).
* **Critical FinOps Classification:** This $1,335.36 figure is strictly an **illustrative workload scenario estimate** under an assumed sustained 500 req/sec load. It is **NOT** a guaranteed spending cap, maximum financial limit, or worst-case ceiling.
* **Best-Effort Throttling Reality:** Amazon API Gateway HTTP API throttling operates on a distributed token-bucket algorithm across regional fleets and is **best-effort**. It cannot establish a guaranteed hard request ceiling or absolute spending stop. In distributed bursts, retry storms, or DNS fan-outs, actual admitted requests and metered evaluation charges may exceed this scenario estimate.
* **Downstream Protection:** While API Gateway meters evaluated requests, downstream compute and database layers are decoupled:
  - Lambda `ReservedConcurrentExecutions` (190 total across the stack) caps maximum parallel execution workers.
  - Application-tier dual-budget rate limiting (5 req / 5 min per device within a 30 req / 5 min campus NAT ceiling) rejects unauthorized submissions within ~5ms, preventing runaway database write operations.

---

## 5. Account-Level Financial Governance with AWS Budgets

1. **CloudFormation Parameter Limitations:** CloudFormation template parameters, route throttling settings, and Lambda concurrency limits cannot enforce account-level financial ceilings.
2. **AWS Budgets Configuration:** Comprehensive cost governance requires configuring an AWS Budget in the AWS Billing Console for the target AWS account.
3. **No Automatic Hard Stop:** An AWS Budget does not automatically guarantee a hard stop on AWS charges; it provides automated alerting via Amazon SNS / email when actual or forecasted spend reaches defined thresholds (e.g., 50%, 80%, 100% of a monthly budget limit).
4. **Enforceable Spending Stops:** To enforce spending cutoffs, administrators must configure explicit AWS Budget Actions (e.g., triggering a custom Lambda or applying an SCP/IAM policy to restrict resource usage). These require operational deployment in a live AWS account.

---

## 6. Architectural Cost Optimization Safeguards

1. **Client-Side Cache & SWR Strategy:**  
   The web application caches outlet estimates for 25 seconds before re-fetching, eliminating redundant Lambda invocations.
2. **Aggregated Snapshot Caching:**  
   When calculating campus-wide recommendations, Lambda reads cached `ESTIMATE#CURRENT` records in a single batch rather than re-aggregating thousands of raw reports on every click.
3. **Automated DynamoDB TTL Cleanup:**  
   Individual observations expire automatically after 30 days (`ttl = epoch + 2592000`). Expired items are deleted by AWS internal background processes at zero write cost, preventing storage bloat while guaranteeing full retention for the 14-day rolling historical window.
4. **Origin Access Control (OAC):**  
   Private S3 bucket access is gated strictly behind CloudFront OAC. Malicious or direct scrapers cannot bypass CloudFront caching to induce S3 GET charges.
