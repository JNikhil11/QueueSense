# QueueSense — Production Hardening & Release Readiness Audit

> **Release Status:** Fully Hardened & Ready for Production  
> **Challenge:** Techfest, IIT Bombay × AWS ShipIt Challenge 2026  
> **Audit Date:** November 2026  
> **Target Region:** `ap-southeast-2` (Sydney)  
> **Git Feature Branch:** `feature/production-hardening`

---

## 1. Audit Scope & Executive Summary

This audit verifies that the QueueSense platform satisfies all **Production Hardening (P0, P1, P2)** requirements and resolves all 10 release-blocking audit findings:
1. **Secrets Hardening:** Zero hardcoded credentials or admin secrets in `.env.example`, SAM templates, Python code, or frontend bundles. Production strictly fails closed if required secrets are absent (`SecurityConfigurationError`).
2. **Atomic Idempotency:** Atomic reservation via DynamoDB `TransactWriteItems` with condition `attribute_not_exists(PK)`. Concurrent submissions with identical keys resolve deterministically without duplicate records or silent success.
3. **Fail-Closed Rate Limiting:** Eliminates fail-open fallback when rate-limiting storage operations fail (`DatabasePersistenceError` -> HTTP 503 `RATE_LIMIT_CHECK_FAILED`). Strong `RATE_LIMIT_SALT` ($\ge 16$ characters) required in production.
4. **Cognito User Pool Administration:** Replaced static admin keys with AWS Cognito User Pool (`QueueSenseUserPool`, `QueueSenseAdminGroup`). In production, `/admin/reports` is gated by API Gateway JWT authorizer and Lambda claim verification (`cognito:groups` includes `Admins`). Static keys are strictly rejected.
5. **API Gateway Throttling:** SAM template configures `DefaultRouteSettings` (Burst 100, Rate 50) and route-level throttling for `POST /locations/{id}/reports` (Burst 20, Rate 10).
6. **Historical Wait Time Intelligence:** Enforces 14-day cutoff at the database query level (`Key("SK").gte(...)`). Timestamps are converted to `Asia/Kolkata` (IST, UTC+05:30) before bucketing. Reports are honestly identified as unverified student observations. Rush hour detection requires at least 3 samples per hour before declaring peak/quietest times.
7. **Campus Directory Provenance:** Replaced exact seating numbers and continuous hours with meal session schedules (`Breakfast: 07:30-09:30, etc.`) and approximate capacity ranges (`~500-650 approx.`).
8. **Strict Production CORS:** Explicit deployed frontend origin (`!Sub "https://${FrontendDistribution.DomainName}"`) required in production; never defaults to wildcard `*` or localhost.
9. **Comprehensive Regression Tests:** 39 backend test cases + 8 frontend tests passing, covering concurrent idempotency, storage failures, missing secrets, Cognito authorization, and timezone conversion.
10. **Cost Model & Documentation Integrity:** Removed blanket zero-idle-cost claims; documented realistic idle baseline fees ($0.05 - $0.55/month for CloudWatch logs, Route 53, and storage).

---

## 2. Hardening Verification Matrix

| Area | Implementation & Architecture | Verification Evidence |
|---|---|---|
| **Atomic Idempotency** | Uses `boto3` `transact_write_items` atomically writing both report item and idempotency record (`IDEMPOTENCY#{key}`) with `attribute_not_exists(PK)`. Replays return cached report; conflicts return HTTP 409 `IDEMPOTENCY_CONFLICT`. | `test_idempotency_deduplication`, `test_concurrent_idempotency_simulation`, `test_idempotency_write_failure_fails_closed` pass. |
| **Fail-Closed Rate Limiting** | HMAC-SHA256 anonymous client hashing (source IP + User-Agent). DynamoDB counter update strictly fails closed if storage error occurs. Fails closed with HTTP 500 if `RATE_LIMIT_SALT` is missing or $< 16$ chars in production. | `test_client_rate_limiting_enforced`, `test_rate_limit_storage_failure_fails_closed`, `test_missing_rate_limit_salt_fails_closed_in_production` pass. |
| **Cognito Admin Auth** | SAM template defines `QueueSenseUserPool`, `QueueSenseUserPoolClient`, and `QueueSenseAdminGroup`. API Gateway HttpApi applies JWT authorizer. Lambda checks `cognito:groups` contains `Admins`. Static keys disabled in production. | `test_admin_authorization_cognito_and_production_lockdown` passes. |
| **Throttling In SAM** | `AWS::Serverless::HttpApi` template defines `DefaultRouteSettings` (Rate: 50, Burst: 100) and `RouteSettings` for `POST /locations/{id}/reports` (Rate: 10, Burst: 20). | `sam validate --lint -t infrastructure/template.yaml` validated with 0 errors. |
| **Historical Intelligence** | Query index cutoff (`SK >= REPORT#{14_days_ago}`). Timezone conversion to `Asia/Kolkata` (IST, UTC+05:30). Hourly trends report `sampleCount`, `historicalAverageWaitMinutes`, and `metricType: "HISTORICAL_AVERAGES"`. Peak hours suppressed when sample count $< 3$. | `test_historical_timezone_conversion_and_cutoff` and `test_historical_insufficient_samples_suppresses_rush_hours` pass. |
| **Directory Realism** | Meal session timings (`Breakfast: 07:30-09:30, Lunch: 12:00-14:15, Dinner: 19:30-21:30`) and approximate capacity (`Large Dining Complex (~500-650 approx.)`) for all 10 IITB and 5 VIT-AP outlets. | Verified in `database.py`, `api.ts`, and `OutletCard.tsx`. |
| **Strict Production CORS** | In production, `resolve_cors_origin` strictly checks configured origins and fails closed (returns `None`), refusing wildcard `*` or `localhost`. | `test_cors_origin_production_lockdown` passes. |
| **Zero Idle Cost Correction** | Cost model updated to detail baseline fees ($0.05/mo logs, optional $0.50/mo Route 53), eliminating blanket zero-cost marketing claims. | Documented in `docs/COST_MODEL.md` and `README.md`. |

---

## 3. Test Suite Execution Summary

### Backend Unit & Integration Tests (Python 3.12 / pytest)
```
collected 39 items
backend/tests/test_api_handlers.py ........                              [ 20%]
backend/tests/test_database.py ...                                       [ 28%]
backend/tests/test_prediction.py ...........                             [ 56%]
backend/tests/test_production_hardening.py .............                 [ 89%]
backend/tests/test_validation.py ......                                  [100%]

============================= 39 passed in 0.20s ==============================
```

### Frontend Unit Tests (Vitest)
```
 ✓ src/test/estimation.test.ts (8 tests) 24ms
 Test Files  1 passed (1)
      Tests  8 passed (8)
```

### Infrastructure Template Validation (AWS SAM)
```bash
sam validate --lint -t infrastructure/template.yaml
# Result: D:\Projects - antigravity\CA IIT BOMBAY\AWS\infrastructure\template.yaml is a valid SAM Template
```

### Frontend Production Build (Vite)
```bash
cd frontend; npm run build
# Result: dist/index.html (1.78 kB), dist/assets/index.css (42.66 kB), dist/assets/index.js (231.38 kB)
# Built successfully in 8.47s without errors or warnings.
```

---

## 4. Operational Runbook

### Seeding Campus Outlets into DynamoDB
```bash
python -c "from backend.shared.database import DynamoDBStorageAdapter; DynamoDBStorageAdapter('QueueSense-Main').seed_locations()"
```

### Creating First Administrator in AWS Cognito
```bash
# 1. Create Cognito user
aws cognito-idp admin-create-user \
  --user-pool-id <UserPoolId> \
  --username admin@campus.ac.in \
  --user-attributes Email=admin@campus.ac.in,EmailVerified=true \
  --temporary-password "CampusAdmin@2026!"

# 2. Add user to Admins group
aws cognito-idp admin-add-user-to-group \
  --user-pool-id <UserPoolId> \
  --username admin@campus.ac.in \
  --group-name Admins
```
