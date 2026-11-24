# QueueSense — Batch 6 Release Readiness & Pre-Deployment Evidence Assessment

**Project:** QueueSense — Real-Time Campus Queue Intelligence  
**Repository:** https://github.com/JNikhil11/QueueSense  
**Feature Branch:** `feature/production-hardening`  
**Batch 6 Starting Commit:** `879c2ac82c45ab135ecd21c6a514b2110ad391b6`  
**Protected Master Baseline:** `47d4ab0ac8c4ece6da7f481d86101c65f6026d4c`  
**Target AWS Region:** `ap-southeast-2` (Configured default) / Recommended `ap-south-1` (Campus target)  
**Audit Date:** November 25, 2026  
**Assessment Status:** **CONDITIONAL / PRE-DEPLOYMENT CHECKPOINT (OFFLINE SUITES PASSING; LIVE AWS & STAGING VERIFICATION PENDING)**  

---

## 1. Executive Summary & Evidence Boundaries

QueueSense has completed six engineering hardening and audit batches across fail-closed data handling, privacy-preserving rate limiting, queue estimation heuristics ($\tau = 15.0\text{ min}$ / $900\text{s}$), frontend WCAG 2.2 AA accessibility and schema validation, AWS SAM infrastructure definition, and cross-component integration testing.

To preserve technical accuracy prior to live AWS deployment, verification claims are separated strictly into what has been executed locally versus what awaits an AWS-backed environment:

- **Verified by Source Inspection:** CloudFormation / SAM resource policies, API Gateway `CognitoAuthorizer` issuer/audience/route attachments, on-demand DynamoDB billing, S3 Public Access Block + OAC, explicit 30-day CloudWatch log retention, 15.0-minute prediction decay constant across backend & frontend, and absence of GitHub Actions CI definitions (`.github/workflows/`).
- **Verified by Automated Tests (Offline / In-Memory / Simulated DynamoDB / Local Windows Chrome):**
  - **238 / 238 backend pytest tests** across 9 suites, separating in-memory handler tests (`STORAGE_BACKEND=memory`) from offline `DynamoDBStorageAdapter` protocol simulations (`FakeTransactionalTable`).
  - **177 / 177 frontend Vitest tests** across 14 suites, including unit schema/resolver tests and 7 Puppeteer browser suites run on `Microsoft Windows NT 10.0.26300.0` with Chrome `158.0.8127.88`.
  - Clean TypeScript check (`tsc --noEmit`), Vite production build (`dist/assets/index-DT6ri0Pj.js` 264.53 kB / gzip 75.78 kB), and AWS SAM lint validation (`sam validate -t infrastructure/template.yaml --lint`).
- **Verified Against a Real External Service:** **None.** Zero tests executed against live AWS DynamoDB, live API Gateway, live Cognito, live SSM Parameter Store, or remote CI runners.
- **Not Tested:** Native Chrome execution on macOS or Linux (only unit-simulated path resolution); GitHub Actions CI workflows; live load/latency benchmarking on AWS Lambda.
- **Blocked by Lack of External Evidence:** Live AWS DynamoDB `TransactWriteItems` behavior, 1 MB DynamoDB physical pagination splits, GSI1 eventual consistency lag, 48-hour background TTL reaper deletion, real API Gateway RS256 JWKS verification, runtime SSM decryption, and physical sensor ground-truth wait-time validation.

---

## 2. Test Execution & Verification Scorecard (Observed Final Run)

| Verification Gate | Environment / Mode | Scope & Limitations | Result | Duration / Size |
| :--- | :--- | :--- | :---: | :---: |
| **Python Compilation** | Python 3.12 / `py_compile` | Syntax compilation across all backend `.py` modules & tests | **Exit 0 (Clean)** | — |
| **Batch 6 Adversarial Integration** | Python 3.12 / `pytest 9.2.0` | In-memory handlers + offline DynamoDB simulator + static SAM + 15m decay | **32 / 32 passed (Exit 0)** | 1.25s |
| **Complete Backend Test Suite** | Python 3.12 / `pytest 9.2.0` | All 9 suites in `backend/tests/` (no live AWS / no `boto3` installed) | **238 / 238 passed (Exit 0)** | 14.40s |
| **TypeScript Type Check** | Node / `tsc --noEmit` | Full `frontend/src` strict type check | **Exit 0 (0 errors)** | — |
| **Frontend Production Build** | Vite 5.4.21 | JS/CSS production assets & source maps | **Exit 0 (Clean)** | 264.53 kB JS (75.78 kB gz) |
| **Complete Frontend Vitest Suite** | Windows 11 (`win32`) + Chrome `158.0.8127.88` | 14 suites (unit, estimation, resolver, data isolation, 7 Puppeteer browser suites) | **177 / 177 passed (Exit 0)** | 68.52s |
| **SAM Template Validation & Lint** | AWS SAM CLI (`sam validate --lint`) | Syntax, intrinsic references, cfn-lint rules (`infrastructure/template.yaml`) | **Valid SAM Template (Exit 0)** | — |

---

## 3. Architectural Mechanics & Boundaries Verified

1. **Report Idempotency & Payload Conflict Enforcement:**
   - `DynamoDBStorageAdapter.record_report` issues `TransactWriteItems` writing both the `REPORT` item (30-day TTL) and an `IDEMPOTENCY#{key}` reservation item (24-hour TTL, `ConditionExpression="attribute_not_exists(PK)"`, SHA-256 `payloadHash`).
   - Replays with matching `payloadHash` return the cached original report; conflicting payloads (changed wait, queue, note, or `locationId`) raise `IdempotencyConflictError` mapped to HTTP `409 IDEMPOTENCY_CONFLICT` across both adapters.
   - *Limitation:* Concurrency and `TransactionCanceledException` paths were proven against `InMemoryStorageAdapter` (`threading.Lock`) and an offline Python simulator (`FakeTransactionalTable`); live AWS DynamoDB distributed transaction behavior has not been executed.
2. **Authentication Boundary (API Gateway vs. Lambda):**
   - `infrastructure/template.yaml` configures `CognitoAuthorizer` on `QueueSenseHttpApi` (`IdentitySource: "$request.header.Authorization"`, Cognito User Pool issuer, `QueueSenseUserPoolClient` audience) and attaches it exclusively to `GET /admin/reports`. Route-level `AuthorizationScopes` is not configured; authorization checks `cognito:groups` contains `'Admins'` inside Lambda (`AdminReportsFunction`).
   - Lambda evaluates already-decoded authorizer claims (`verify_cognito_jwt_claims`) and rejects static `X-Admin-Key` in production, rather than performing cryptographic RS256 signature verification (which rests in AWS API Gateway).
3. **Estimation Decay & Heuristic Scope:**
   - Both `backend/shared/prediction.py` (`DEFAULT_DECAY_CONSTANT_MINUTES = 15.0`) and `frontend/src/services/api.ts` (`TAU_MS = 15 * 60 * 1000`) implement exponential decay with $\tau = 15.0$ minutes ($900\text{s}$), half-life $t_{1/2} = 15 \cdot \ln(2) \approx 10.3972$ minutes, smooth cosine taper over 50–60 minutes, and hard cutoff beyond 60 minutes.
   - Without physical entrance sensors, predictions are crowdsourced heuristics.
4. **Cross-Platform Browser Resolution:**
   - `frontend/src/test/helpers/browser.ts` eliminates hardcoded machine-specific paths across all 7 Puppeteer files, checking `CHROME_BIN`, `PUPPETEER_EXECUTABLE_PATH`, and OS candidates. Unit tests verify resolution/error branches cleanly; real headless Chromium execution was verified on Windows 11 (`win32`) Chrome `158.0.8127.88` only.

---

## 4. Operational Prerequisites & Pre-Deployment Blockers

Before classifying an actual AWS environment as production-ready, complete and test the following on a live AWS staging stack:

1. **SSM Parameter Store Provisioning:**
   ```bash
   aws ssm put-parameter \
     --name "/queuesense/prod/rate_limit_salt" \
     --type "SecureString" \
     --value "$(openssl rand -hex 32)" \
     --region ap-southeast-2
   ```
2. **Cognito Administrator Account & Group Provisioning:**
   ```bash
   aws cognito-idp admin-create-user \
     --user-pool-id "<USER_POOL_ID>" \
     --username "admin@campus.ac.in" \
     --user-attributes Name=email,Value=admin@campus.ac.in Name=email_verified,Value=true
   aws cognito-idp admin-add-user-to-group \
     --user-pool-id "<USER_POOL_ID>" \
     --username "admin@campus.ac.in" \
     --group-name "Admins"
   ```
3. **Live AWS Deployment & Smoke Verification (Not Yet Executed):**
   ```bash
   sam build -t infrastructure/template.yaml
   sam deploy --config-file infrastructure/samconfig.toml
   ```
   After SAM deployment, verify against the live staging/prod API:
   - Real Cognito JWT signature enforcement (`401` on invalid signature, `403` on non-`Admins` group, `200` on `Admins` token).
   - Real DynamoDB `TransactWriteItems` replay (`201`) and conflicting payload (`409 IDEMPOTENCY_CONFLICT`).
   - Real SSM `SecureString` + KMS decryption inside `SubmitReportFunction`.
   - Frontend build with deployed API Gateway URL and S3/CloudFront sync.

---

## 5. Deployment Gate Verdict

### **GATE STATUS: READY FOR STAGING DEPLOYMENT — BLOCKED FROM UNCONDITIONAL PRODUCTION GO UNTIL LIVE AWS & STAGING SMOKE VERIFICATION**

The repository codebase on `feature/production-hardening` satisfies all offline unit, adversarial integration, static infrastructure, and Windows Chromium browser gates, subject to completing the AWS infrastructure bootstrapping and live external integration checks listed above.
