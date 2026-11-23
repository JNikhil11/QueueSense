# QueueSense --- Security & Privacy Architecture

**Project:** QueueSense  
**Author:** J Nikhil (`JNikhil11`)  
**Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge  

---

## 1. Threat Model & Security Posture

QueueSense is architected around the core principle of **Zero Trust & Zero PII (Personally Identifiable Information)**. Because it serves university students in a public campus setting, security and privacy protections are embedded at every layer.

---

## 2. Security Boundaries & Protections

### 2.1 Complete Privacy by Design (No PII)
- **Zero Student Credentials:** Students do not log in or register to submit reports or view queue states.
- **No Personal Identifiers:** Student names, phone numbers, registration numbers, academic years, and device IDs are neither requested nor recorded in DynamoDB.
- **Server-Generated Tokens:** Report identifiers (`rep_<12-hex>`) are randomly generated on the server using UUIDv4, eliminating reporter traceability.

### 2.2 AWS IAM Least Privilege
- **No Shared Keys:** No AWS access keys or long-lived secret tokens are embedded in frontend source bundles, environment files, or repository commits.
- **Scoped Execution Roles:** Each Lambda function is granted the absolute minimum IAM permissions required:
  - `GetLocationsFunction`, `GetQueueFunction`, `SubmitReportFunction`: Scoped `DynamoDBCrudPolicy` strictly on the single table `QueueSense-Main-{Stage}`.
  - `AdminReportsFunction`: Scoped `DynamoDBReadPolicy`.
  - `HealthFunction`: Zero DynamoDB permissions.

### 2.3 Strict Input Validation & Boundary Enforcement
Every incoming submission is validated before persistence:
1. **Location Identifier:** Validated against alphanumeric regex pattern `^[a-zA-Z0-9_-]{2,40}$`.
2. **Numeric Boundaries:**
   - `reportedWaitMinutes`: Must be numeric, $0.0 \le \text{wait} \le 120.0$.
   - `queueLength`: Must be integer, $0 \le \text{length} \le 300$.
3. **Note Sanitization:**
   - Stripped of angle brackets (`<`, `>`), curly braces (`{`, `}`), backslashes (`\`), and control characters to eliminate Cross-Site Scripting (XSS).
   - Hard truncated at 140 characters.

### 2.4 Statistical Outlier Rejection (Abuse Mitigation)
- Incoming reports with extreme deviations ($> 3.0 \times \text{MAD}$ from the recent median) are automatically segregated into an audit feed and excluded from public estimations.
- This mitigates intentional sabotage or "queue gaming" by bad actors.

### 2.5 HTTP Security & CORS Policies
- **Strict Headers:** All Lambda responses include:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Cache-Control: no-store, max-age=0`
- **Method Whitelisting:** API Gateway explicitly restricts accepted verbs to `GET`, `POST`, and `OPTIONS`.

### 2.6 Serverless Free-Tier Cost Protection
- DynamoDB configured in `PAY_PER_REQUEST` on-demand billing mode to prevent provisioned capacity burn.
- Point-In-Time-Recovery (PITR) and NAT Gateways omitted to eliminate hourly baseline charges.
- DynamoDB TTL enabled on raw observations to prevent unbounded data accumulation.
