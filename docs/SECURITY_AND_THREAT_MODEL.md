# QueueSense — Security Architecture & Threat Model

**Project:** QueueSense — Real-Time Campus Queue Intelligence  
**Target Standard:** Commercial Application Security & Cloud Hardening Standard  
**Date:** November 24, 2026  
**Status:** Active Production Threat Model  

---

## 1. System Assets & Sensitivity Classification

| Asset | Description | Sensitivity | Storage / Transit Location | Protection Mechanism |
| :--- | :--- | :---: | :--- | :--- |
| **Anonymous Queue Observations** | Student-submitted wait times (0–120 min), queue counts (0–300), and optional notes. | Public / Low | DynamoDB `MainTable` | Validated at boundary, sanitized notes, 30-day TTL. |
| **Rate-Limit Tokens** | 16-character HMAC-SHA256 digests of client source IP. | Internal / Low | DynamoDB `MainTable` (TTL: 300s) | One-way irreversible hash, 5-minute physical retention. |
| **SSM HMAC Salt (`RATE_LIMIT_SALT`)** | 256-bit cryptographically secure string used for HMAC digests. | Confidential / High | AWS SSM Parameter Store (`SecureString`, KMS encrypted) | Least-privilege IAM, cached in Lambda volatile memory, never logged. |
| **Admin Cognito User Pool** | User pool credentials, JWT tokens, and Admin group memberships. | Confidential / High | AWS Cognito User Pool | OAuth2 / OIDC JWT, HTTPS transit, RS256 token verification. |
| **API Gateway Ingress** | HTTP API endpoints routing campus traffic to Lambda functions. | Public / High Availability | AWS API Gateway (v2) | Route throttling (Burst 20, Rate 10), payload validation. |
| **Frontend Static Assets** | Single-page application bundle (HTML, JS, CSS, video background). | Public / Integrity | AWS S3 + CloudFront CDN | S3 Public Access Blocked, CloudFront Origin Access Control (OAC). |

---

## 2. Threat Actors & Capabilities

1. **Prankster / Dishonest Student:**
   - *Motivation:* Artificially inflate wait times at a rival hostel mess or deflate wait times at their favorite canteen.
   - *Capabilities:* Web browser, curl, network scripting, rotating `User-Agent` headers.
   - *Mitigation:* Source-IP-based HMAC rate limiting (5 req / 5 min), MAD statistical outlier rejection with 25m floor, API Gateway throttling.

2. **Spam / Automated Flooding Script:**
   - *Motivation:* Exhaust Lambda concurrency, flood DynamoDB write capacity, or trigger denial-of-wallet.
   - *Capabilities:* High-frequency HTTP request generators, headless browsers.
   - *Mitigation:* API Gateway route throttling (Burst 20, Rate 10 on report route; Burst 100, Rate 50 globally), 429 Too Many Requests responses before Lambda invocation.

3. **Adversary on Campus Shared Wi-Fi (NAT / Egress):**
   - *Motivation:* Exploit shared egress IP addresses to either bypass rate limits or exhaust quotas for innocent students.
   - *Capabilities:* Shared public NAT IP with hundreds of campus users.
   - *Mitigation:* Bounded sliding window (5 submissions per 5 minutes per IP); independent route throttling; low false-positive impact due to 5-minute window expiration.

4. **Malicious Actor Probing Admin Interface:**
   - *Motivation:* Access student observation audit logs or modify catalog records without authorization.
   - *Capabilities:* Credential stuffing, token tampering, path traversal.
   - *Mitigation:* AWS Cognito User Pool JWT Authorizer with mandatory `Admins` group membership check (`cognito:groups`); static admin API keys strictly forbidden in production.

---

## 3. Attack Surface Decomposition

```
[Student Device / Browser]
         |
         | HTTPS (TLS 1.2 / 1.3)
         v
[CloudFront CDN] ---------------------> [Private S3 Bucket (OAC Only)]
         | (Static Bundle)
         v
[API Gateway HTTP API]
    |-- Default Throttling: Rate 50, Burst 100
    |-- Route Throttling (POST /locations/{id}/reports): Rate 10, Burst 20
    |-- JWT Authorizer (/admin/reports): Cognito User Pool (Admins Group)
         |
         +--> [GetLocationsFunction] ----> DynamoDB (Query on MainTable)
         +--> [GetQueueFunction] --------> DynamoDB (Query on MainTable)
         +--> [SubmitReportFunction] ----> SSM Parameter Store (SecureString Salt)
         |                                 DynamoDB (TransactWriteItems: Report + Idempotency)
         +--> [GetRecommendationsFunction] DynamoDB (Query on MainTable)
         +--> [GetHistoricalFunction] ---> DynamoDB (14-day Query on MainTable, Asia/Kolkata)
         +--> [AdminReportsFunction] ----> DynamoDB (Scan on MainTable, Admins Only)
```

---

## 4. Abuse Scenarios & Engineering Mitigations

### 4.1 Replay & Duplicate Submissions (Idempotency)
- **Attack:** An attacker or mobile browser on a flaky network retries an observation submission multiple times.
- **Vulnerability:** Duplicate records could artificially skew the exponential decay average.
- **Mitigation:**
  - Client sends `X-Idempotency-Key` or body `idempotencyKey`.
  - Backend executes `transact_write_items` containing both the `REPORT` item and an `IDEMPOTENCY` reservation item with `attribute_not_exists(PK)`.
  - Retried requests detect the existing key and return the original report without creating duplicates.
  - Failures in the idempotency write strictly fail closed, never returning silent success.

### 4.2 Rate-Limit Evasion via Header Spoofing
- **Attack:** An attacker script rotates `User-Agent` or injects random `X-Forwarded-For` headers to generate distinct client fingerprints.
- **Vulnerability:** Earlier implementations included `User-Agent` in the client hash, enabling trivial rate-limit bypass.
- **Mitigation:**
  - `compute_anonymous_client_hash` derives client identity exclusively from `requestContext.http.sourceIp` (populated securely by API Gateway).
  - Client-controlled headers (`User-Agent`, `X-Forwarded-For`, `Forwarded`) are strictly ignored.
  - Test suite `test_user_agent_rotation_does_not_bypass_rate_limit` verifies that rotating headers yields identical rate-limit keys.

### 4.3 Database Storage Failure & Fail-Closed Guarantee
- **Attack:** An attacker causes database connection errors or capacity exhaustion.
- **Vulnerability:** Naive applications fall back to in-memory dictionaries or return success without persisting data.
- **Mitigation:**
  - In `database.py`, non-DynamoDB adapters are strictly forbidden when running inside AWS Lambda or production mode (`DatabasePersistenceError`).
  - When rate-limiting checks or report writes fail, Lambda handlers return controlled HTTP 500/503 errors (`RATE_LIMIT_CHECK_FAILED`, `PERSISTENCE_FAILED`).
  - The frontend fails closed and displays an honest "Live Data Temporarily Unavailable" notice rather than substituting mock fixtures.

### 4.4 Outlier Injection & Majority Poisoning
- **Attack:** An attacker reports extreme wait times (e.g. 110 minutes when the true wait is 5 minutes).
- **Vulnerability:** Arithmetic mean is highly vulnerable to extreme outliers.
- **Mitigation:**
  - Boundary filters reject impossible values outside $[0, 120]$ min wait and $[0, 300]$ queue length.
  - Median Absolute Deviation (MAD) outlier filtering with `cutoff = max(3.5 * mad, 25.0)` filters isolated extremes while preserving valid meal rush surges.
  - Mathematical breakdown point is $\approx 50\%$; coordinated majority poisoning is mitigated by rate limiting and API Gateway throttling.

---

## 5. Regulatory & Privacy Analysis (India DPDP Act Compliance)

### Data Minimization & PII Exclusion
QueueSense is explicitly architected around **Zero Personally Identifiable Student Data**:
1. **No Student Credentials:** Students do not log in, register, or provide names, email addresses, phone numbers, or IITB roll numbers.
2. **Ephemeral Network Identifiers:** Client IP addresses exist only in volatile Lambda execution memory for the duration of the request invocation (~30ms).
3. **Irreversible Pseudonymization:** Source IP is immediately hashed with a 256-bit cryptographically secure HMAC salt (`HMAC-SHA256(salt, "ip::" + source_ip)`), truncated to 16 characters, and used strictly as a short-lived rate-limiting key.
4. **Zero Raw IP Persistence:** Raw IP addresses are never written to disk, stored in DynamoDB, or emitted in CloudWatch logs.
5. **Short Data Retention:** Rate-limiting records in DynamoDB expire automatically via TTL in 300 seconds (5 minutes). Raw observation reports expire via TTL in 30 days.

---

## 6. Residual Risks & Accepted Engineering Trade-offs

1. **Campus NAT IP Collisions:**
   - *Risk:* In campus Wi-Fi networks where thousands of students share a common public NAT gateway, the 5-requests-per-5-minutes rate limit could momentarily rate-limit legitimate students.
   - *Accepted Trade-off:* 5 requests per 5 minutes allows one report every minute across the egress gateway. In practice, students report asynchronously across different mess timings. If a student is throttled, the UI shows a clear 429 message advising a brief wait. This trade-off is accepted to prevent automated flood attacks.

2. **Absence of Hardware Sensor Ground Truth:**
   - *Risk:* Estimates rely on human crowd observations without camera or turnstile verification.
   - *Accepted Trade-off:* Addressed by displaying transparent confidence scores (Volume, Recency, Agreement) and clear evidence explanations. The system never claims to provide sensor-verified ground truth.
