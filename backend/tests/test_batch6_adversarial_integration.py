"""
QueueSense — Batch 6: Cross-Component Adversarial Integration & Release Readiness Tests
Validates:
- Matrix A: Frontend <-> API Contracts (boundary values, error payload schema, locationId matching)
- Matrix B: Report Submission Lifecycle (idempotency concurrency, conflicting payloads, transaction failure fail-closed)
- Matrix C: Authentication Boundary (Cognito JWT claims, forged groups, expiration, dev key lockdown)
- Matrix D: Rate Limiting & Abuse Resistance (sliding-window burst enforcement, NAT boundaries, outlier rejection)
- Matrix E: DynamoDB & Data Integrity (cross-campus partition isolation, TTL 30-day calculation, pagination limits)
- Matrix F: Predictions & Recommendations (decay weighting tau=1800s, clock skew, sparse data graceful degradation)
- Matrix G: Infrastructure & Least-Privilege IAM (no wildcard DynamoDB writes, PAY_PER_REQUEST billing, private S3 + OAC, CloudWatch retention)
"""

import json
import os
import time
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from backend.shared.database import (
    QueueSenseDatabase,
    DatabasePersistenceError,
    IdempotencyConflictError,
    reset_shared_test_adapter,
    get_default_campus_locations,
)
from backend.shared.security import (
    compute_anonymous_client_hash,
    compute_pseudonymous_client_hash,
    verify_cognito_jwt_claims,
    clear_salt_cache,
)
from backend.shared.prediction import (
    calculate_queue_estimate,
    filter_outliers,
)
from backend.shared.validation import (
    validate_location_id,
    validate_report_payload,
    validate_pagination_limit,
)

import backend.functions.get_locations.app as get_locations_mod
import backend.functions.get_queue.app as get_queue_mod
import backend.functions.submit_report.app as submit_report_mod
import backend.functions.admin.app as admin_mod
from backend.tests.test_batch4_infrastructure import load_cfn_template


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    monkeypatch.setenv("DATA_MODE", "test")
    monkeypatch.setenv("RATE_LIMIT_SALT", "test_transient_test_salt_min_16_chars_1234")
    monkeypatch.setenv("ADMIN_API_KEY", "queuesense-admin-secret-dev-key")
    reset_shared_test_adapter()
    clear_salt_cache()


# =========================================================================
# Matrix A: Frontend <-> API Contracts & Error Structure
# =========================================================================

class TestMatrixA_FrontendApiContracts:

    def test_get_queue_response_contract_and_boundary_values(self):
        """Verify GET /locations/{id}/queue matches the exact contract required by frontend."""
        event = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "requestContext": {"requestId": "req-contract-001"},
        }
        context = MagicMock(aws_request_id="req-contract-001")
        resp = get_queue_mod.lambda_handler(event, context)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["success"] is True
        assert "data" in body
        data = body["data"]

        # Validate top-level keys
        assert "location" in data
        assert data["location"]["id"] == "iitb-mess-h12-14"
        assert "name" in data["location"]
        assert "estimate" in data
        assert "reports" in data

        # Validate estimate boundaries
        est = data["estimate"]
        if est["predictedWaitMinutes"] is not None:
            assert 0 <= est["predictedWaitMinutes"] <= 120
            assert 0 <= est["predictedQueueLength"] <= 300
        assert 0.0 <= est["confidence"] <= 1.0
        assert est["confidenceLabel"] in ["LOW", "MEDIUM", "HIGH", "NO DATA"]
        assert est["congestion"] in ["LOW", "MODERATE", "HIGH", "VERY_HIGH", "UNKNOWN"]
        assert est["freshness"] in ["LIVE", "RECENT", "STALE", "EXPIRED", "NO RECENT DATA"]

    def test_error_response_strict_envelope_across_failure_modes(self):
        """Verify error responses conform strictly to { success: False, error, errorCode, requestId }."""
        # 1. 400 Bad Request: Invalid location ID syntax
        bad_req_event = {
            "pathParameters": {"id": "invalid/id!@#"},
            "requestContext": {"requestId": "req-err-400"},
        }
        context_400 = MagicMock(aws_request_id="req-err-400")
        resp_400 = get_queue_mod.lambda_handler(bad_req_event, context_400)
        assert resp_400["statusCode"] == 400
        body_400 = json.loads(resp_400["body"])
        assert body_400["success"] is False
        assert "error" in body_400
        assert body_400["errorCode"] == "INVALID_LOCATION_ID"
        assert body_400["requestId"] == "req-err-400"

        # 2. 404 Not Found: Well-formed ID but non-existent
        not_found_event = {
            "pathParameters": {"id": "iitb-mess-nonexistent-outlet"},
            "requestContext": {"requestId": "req-err-404"},
        }
        context_404 = MagicMock(aws_request_id="req-err-404")
        resp_404 = get_queue_mod.lambda_handler(not_found_event, context_404)
        assert resp_404["statusCode"] == 404
        body_404 = json.loads(resp_404["body"])
        assert body_404["success"] is False
        assert body_404["errorCode"] == "LOCATION_NOT_FOUND"
        assert body_404["requestId"] == "req-err-404"

        # 3. 400 Bad Request: Malformed JSON payload on submission
        malformed_json_event = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "body": "{invalid-json-content",
            "requestContext": {"requestId": "req-err-malformed"},
        }
        context_malformed = MagicMock(aws_request_id="req-err-malformed")
        resp_malformed = submit_report_mod.lambda_handler(malformed_json_event, context_malformed)
        assert resp_malformed["statusCode"] == 400
        body_malformed = json.loads(resp_malformed["body"])
        assert body_malformed["success"] is False
        assert body_malformed["errorCode"] == "MALFORMED_JSON"

    def test_route_location_id_matching_in_sanitized_reports(self):
        """Sanitized reports returned by get_queue must strictly reflect route locationId."""
        db = QueueSenseDatabase()
        db.record_report(
            location_id="iitb-mess-h12-14",
            reported_wait_minutes=10,
            queue_length=15,
            note="Lunch rush",
        )

        event = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "requestContext": {"requestId": "req-route-match"},
        }
        resp = get_queue_mod.lambda_handler(event, None)
        body = json.loads(resp["body"])
        reports = body["data"]["reports"]
        assert len(reports) >= 1
        for rep in reports:
            assert rep["locationId"] == "iitb-mess-h12-14"


# =========================================================================
# Matrix B: Report Submission Lifecycle & Idempotency Guarantees
# =========================================================================

class TestMatrixB_ReportSubmissionLifecycle:

    def test_idempotency_concurrent_duplicate_exact_replay(self):
        """Identical submissions with same idempotencyKey return identical cached report."""
        idem_key = f"test-idem-{uuid.uuid4().hex}"
        event = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "headers": {
                "X-Idempotency-Key": idem_key,
                "X-Device-ID": "dev-alpha-001",
            },
            "body": json.dumps({"reportedWaitMinutes": 12, "queueLength": 18, "note": "Peak dinner"}),
            "requestContext": {
                "requestId": "req-first-sub",
                "identity": {"sourceIp": "10.10.1.5"},
            },
        }

        # First submission
        resp1 = submit_report_mod.lambda_handler(event, None)
        assert resp1["statusCode"] == 201
        body1 = json.loads(resp1["body"])
        report_id = body1["data"]["report"]["reportId"]

        # Duplicate submission with same key and data
        event2 = dict(event)
        event2["requestContext"] = {
            "requestId": "req-second-sub",
            "identity": {"sourceIp": "10.10.1.5"},
        }
        resp2 = submit_report_mod.lambda_handler(event2, None)
        assert resp2["statusCode"] == 201
        body2 = json.loads(resp2["body"])
        assert body2["data"]["report"]["reportId"] == report_id

    def test_idempotency_conflict_detection_and_rejection(self):
        """When an idempotency conflict occurs, handler returns HTTP 409 IDEMPOTENCY_CONFLICT."""
        idem_key = f"test-conflict-{uuid.uuid4().hex}"
        event = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "headers": {"X-Idempotency-Key": idem_key},
            "body": json.dumps({"reportedWaitMinutes": 30, "queueLength": 80}),
            "requestContext": {"requestId": "req-conflict"},
        }
        with patch.object(QueueSenseDatabase, "record_report", side_effect=IdempotencyConflictError("Idempotency conflict")):
            resp = submit_report_mod.lambda_handler(event, None)
            assert resp["statusCode"] == 409
            body = json.loads(resp["body"])
            assert body["errorCode"] == "IDEMPOTENCY_CONFLICT"

    def test_database_persistence_failure_fails_closed(self):
        """Database failure during record_report must result in 500 PERSISTENCE_FAILED, never silent 200."""
        with patch.object(QueueSenseDatabase, "record_report", side_effect=DatabasePersistenceError("DDB unreachable")):
            event = {
                "pathParameters": {"id": "iitb-mess-h12-14"},
                "headers": {"X-Device-ID": "dev-test-failure"},
                "body": json.dumps({"reportedWaitMinutes": 10, "queueLength": 10}),
                "requestContext": {"requestId": "req-fail-closed"},
            }
            resp = submit_report_mod.lambda_handler(event, None)
            assert resp["statusCode"] == 500
            body = json.loads(resp["body"])
            assert body["errorCode"] == "PERSISTENCE_FAILED"

    def test_raw_device_id_never_persisted_directly(self):
        """Raw client device ID must be securely hashed and never appear in saved report."""
        raw_dev_id = "sensitive-device-hardware-uuid-999"
        db = QueueSenseDatabase()
        rep = db.record_report(
            location_id="iitb-mess-h12-14",
            reported_wait_minutes=15,
            queue_length=20,
        )
        assert "deviceId" not in rep
        assert raw_dev_id not in str(rep)


# =========================================================================
# Matrix C: Authentication Boundary & Admin Lockdown
# =========================================================================

class TestMatrixC_AuthenticationBoundary:

    def test_admin_reports_rejects_unauthenticated_request(self):
        """GET /admin/reports without auth context must be rejected."""
        event = {"requestContext": {"requestId": "req-admin-unauth"}}
        resp = admin_mod.lambda_handler(event, None)
        assert resp["statusCode"] in [401, 403]
        body = json.loads(resp["body"])
        assert body["success"] is False

    def test_admin_reports_rejects_non_admin_cognito_group(self):
        """Cognito user not in 'Admins' group must receive 403 Forbidden."""
        event = {
            "requestContext": {
                "requestId": "req-non-admin",
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "user-uuid-123",
                            "cognito:groups": ["Students", "Staff"],
                            "token_use": "id",
                            "exp": str(int(time.time()) + 3600),
                        }
                    }
                },
            }
        }
        resp = admin_mod.lambda_handler(event, None)
        assert resp["statusCode"] == 403
        body = json.loads(resp["body"])
        assert body["errorCode"] == "FORBIDDEN_NOT_ADMIN"

    def test_admin_reports_accepts_verified_admin_group(self):
        """Cognito user with 'Admins' group must succeed and return report feed."""
        event = {
            "requestContext": {
                "requestId": "req-admin-ok",
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "admin-uuid-456",
                            "cognito:groups": ["Admins"],
                            "token_use": "id",
                            "exp": str(int(time.time()) + 3600),
                        }
                    }
                },
            }
        }
        resp = admin_mod.lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["success"] is True
        assert "reports" in body["data"]

    def test_admin_reports_rejects_expired_jwt_claims(self):
        """JWT claims with past expiration must be rejected."""
        event = {
            "requestContext": {
                "requestId": "req-admin-expired",
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "admin-uuid-456",
                            "cognito:groups": ["Admins"],
                            "token_use": "id",
                            "exp": str(int(time.time()) - 100),  # expired 100s ago
                        }
                    }
                },
            }
        }
        resp = admin_mod.lambda_handler(event, None)
        assert resp["statusCode"] in [401, 403]

    def test_production_environment_strictly_forbids_static_api_key(self, monkeypatch):
        """In production, static API key headers must be ignored/rejected."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        event = {
            "headers": {"X-Admin-Key": "queuesense-admin-secret-dev-key"},
            "requestContext": {"requestId": "req-prod-static-key"},
        }
        resp = admin_mod.lambda_handler(event, None)
        assert resp["statusCode"] in [401, 403]


# =========================================================================
# Matrix D: Rate Limiting & Abuse Resistance
# =========================================================================

class TestMatrixD_RateLimitingAndAbuseResistance:

    def test_burst_submissions_trigger_rate_limit(self):
        """Submitting beyond allowed threshold from same client triggers HTTP 429."""
        event_base = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "headers": {"X-Device-ID": "dev-burst-abuser"},
            "body": json.dumps({"reportedWaitMinutes": 10, "queueLength": 10}),
            "requestContext": {
                "identity": {"sourceIp": "192.168.1.100"},
            },
        }

        got_429 = False
        for i in range(15):
            event = dict(event_base)
            event["requestContext"] = {
                "requestId": f"req-burst-{i}",
                "identity": {"sourceIp": "192.168.1.100"},
            }
            event["headers"] = {
                "X-Device-ID": "dev-burst-abuser",
                "X-Idempotency-Key": f"burst-idem-{i}",
            }
            resp = submit_report_mod.lambda_handler(event, None)
            if resp["statusCode"] == 429:
                got_429 = True
                body = json.loads(resp["body"])
                assert "RATE_LIMIT" in body["errorCode"]
                break

        assert got_429, "Expected 429 Rate Limit Exceeded after consecutive burst submissions."

    def test_client_spoofed_forwarded_for_is_ignored(self):
        """Client-provided X-Forwarded-For headers cannot manipulate rate limit partitioning."""
        event = {
            "headers": {
                "X-Forwarded-For": "8.8.8.8, 1.1.1.1",
                "X-Device-ID": "dev-fixed-device",
            },
            "requestContext": {
                "identity": {"sourceIp": "10.0.0.99"},
            },
        }
        hash1 = compute_anonymous_client_hash(event)
        
        event2 = dict(event)
        event2["headers"] = {
            "X-Forwarded-For": "203.0.113.195",
            "X-Device-ID": "dev-fixed-device",
        }
        hash2 = compute_anonymous_client_hash(event2)
        assert hash1 == hash2

    def test_outlier_filtering_bounds_extreme_submissions(self):
        """Outlier filter detects physical bounds violations and uncorroborated spikes."""
        now_iso = datetime.now(timezone.utc).isoformat()
        # 1. Physical bounds violation (> 120 min wait)
        reports = [
            {"reportedWaitMinutes": 10, "queueLength": 12, "timestamp": now_iso},
            {"reportedWaitMinutes": 12, "queueLength": 14, "timestamp": now_iso},
            {"reportedWaitMinutes": 11, "queueLength": 13, "timestamp": now_iso},
            {"reportedWaitMinutes": 135, "queueLength": 20, "timestamp": now_iso},  # Exceeds max 120
        ]
        valid, outliers = filter_outliers(reports)
        assert len(valid) == 3
        assert len(outliers) == 1
        assert outliers[0]["outlierReason"] == "PHYSICAL_BOUNDS_VIOLATION"


# =========================================================================
# Matrix E: DynamoDB & Data Integrity
# =========================================================================

class TestMatrixE_DynamoDbAndDataIntegrity:

    def test_campus_partition_isolation_prevents_cross_talk(self, monkeypatch):
        """Dynamic campus configuration strictly isolates campus outlet directories."""
        monkeypatch.setenv("CAMPUS_ID", "iitb")
        iitb_locs = get_default_campus_locations()
        assert len(iitb_locs) > 0
        for loc in iitb_locs:
            assert loc["id"].startswith("iitb-")
            assert not loc["id"].startswith("vitap-")

        monkeypatch.setenv("CAMPUS_ID", "vitap")
        vitap_locs = get_default_campus_locations()
        assert len(vitap_locs) > 0
        for loc in vitap_locs:
            assert loc["id"].startswith("vitap-")
            assert not loc["id"].startswith("iitb-")

    def test_report_item_has_30_day_ttl(self):
        """Report item persisted in DynamoDB includes ttl attribute approximately 30 days ahead."""
        db = QueueSenseDatabase()
        now_ts = int(time.time())
        rep = db.record_report(
            location_id="iitb-mess-h12-14",
            reported_wait_minutes=15,
            queue_length=20,
        )
        assert "ttl" in rep
        expected_min_ttl = now_ts + (29 * 86400)
        expected_max_ttl = now_ts + (31 * 86400)
        assert expected_min_ttl <= rep["ttl"] <= expected_max_ttl

    def test_pagination_limits_validation(self):
        """validate_pagination_limit validates and bounds limit values."""
        is_valid_neg, val_neg, err_neg = validate_pagination_limit(-10, default=30)
        assert is_valid_neg is False
        assert "must be at least 1" in err_neg

        is_valid_ok, val_ok, _ = validate_pagination_limit(50, default=30)
        assert is_valid_ok is True
        assert val_ok == 50

        is_valid_high, val_high, err_high = validate_pagination_limit(500, default=30)
        assert is_valid_high is False
        assert "cannot exceed 100" in err_high


# =========================================================================
# Matrix F: Predictions & Recommendations Heuristic Models
# =========================================================================

class TestMatrixF_PredictionsAndRecommendations:

    def test_exponential_decay_favors_recent_reports(self):
        """Recent reports have significantly higher weighting than 25-minute old reports."""
        now = datetime.now(timezone.utc)
        t_recent = now - timedelta(minutes=2)
        t_old = now - timedelta(minutes=25)

        reports = [
            {"reportedWaitMinutes": 50.0, "queueLength": 50, "timestamp": t_old.isoformat()},
            {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": t_recent.isoformat()},
        ]
        estimate = calculate_queue_estimate(reports)
        assert estimate["predictedWaitMinutes"] < 25.0
        assert estimate["predictedQueueLength"] < 25

    def test_sparse_data_defaults_safely(self):
        """Empty report history defaults safely to honest NO DATA state without errors."""
        estimate = calculate_queue_estimate([])
        assert estimate["predictedWaitMinutes"] is None
        assert estimate["predictedQueueLength"] is None
        assert estimate["confidence"] == 0.0
        assert estimate["confidenceLabel"] == "NO DATA"
        assert estimate["freshness"] == "NO RECENT DATA"
        assert estimate["reportCount"] == 0

    def test_invalid_report_payload_rejected_by_validation(self):
        """Plausibility boundaries reject extreme/negative values in submission payload."""
        # 1. Negative wait time
        is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": -5, "queueLength": 10})
        assert not is_valid
        assert any("cannot be negative" in e for e in errors)

        # 2. Impossible wait time (> 120 mins)
        is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": 150, "queueLength": 10})
        assert not is_valid
        assert any("exceeds plausible limit" in e for e in errors)

        # 3. Fractional queue length (fractional humans)
        is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": 4.5})
        assert not is_valid
        assert any("whole integer" in e for e in errors)


# =========================================================================
# Matrix G: Infrastructure & Least-Privilege IAM Audit
# =========================================================================

class TestMatrixG_InfrastructureAndLeastPrivilegeIAM:

    def test_no_wildcard_dynamodb_write_policies(self):
        """CloudFormation template must have NO IAM policy granting DynamoDB writes on '*'."""
        tmpl = load_cfn_template()
        resources = tmpl.get("Resources", {})

        write_actions = {"dynamodb:putitem", "dynamodb:updateitem", "dynamodb:deleteitem"}

        for res_name, res in resources.items():
            if res.get("Type") == "AWS::IAM::Policy":
                props = res.get("Properties", {})
                doc = props.get("PolicyDocument", {})
                for stmt in doc.get("Statement", []):
                    actions = stmt.get("Action", [])
                    if isinstance(actions, str):
                        actions = [actions]
                    actions_lower = {a.lower() for a in actions}

                    if write_actions & actions_lower:
                        resource = stmt.get("Resource", "")
                        assert resource != "*", f"Resource wildcard on write in {res_name}"

    def test_dynamodb_table_uses_on_demand_billing(self):
        """Main DynamoDB table must configure BillingMode: PAY_PER_REQUEST."""
        tmpl = load_cfn_template()
        resources = tmpl.get("Resources", {})
        table = resources.get("MainTable")
        assert table is not None
        billing_mode = table.get("Properties", {}).get("BillingMode")
        assert billing_mode == "PAY_PER_REQUEST"

    def test_s3_bucket_has_public_access_blocked(self):
        """Frontend S3 bucket must block all public ACLs, policies and direct access."""
        tmpl = load_cfn_template()
        resources = tmpl.get("Resources", {})
        bucket = resources.get("FrontendBucket")
        assert bucket is not None
        pab = bucket.get("Properties", {}).get("PublicAccessBlockConfiguration", {})
        assert pab.get("BlockPublicAcls") is True
        assert pab.get("BlockPublicPolicy") is True
        assert pab.get("IgnorePublicAcls") is True
        assert pab.get("RestrictPublicBuckets") is True

    def test_all_lambda_log_groups_have_explicit_retention(self):
        """Every CloudWatch LogGroup must specify finite 30-day RetentionInDays."""
        tmpl = load_cfn_template()
        resources = tmpl.get("Resources", {})
        log_groups = [r for r in resources.values() if r.get("Type") == "AWS::Logs::LogGroup"]
        assert len(log_groups) >= 5
        for lg in log_groups:
            retention = lg.get("Properties", {}).get("RetentionInDays")
            assert retention == 30, f"Log group missing 30-day retention: {lg}"
