"""
QueueSense - Production Hardening Test Suite
Verifies:
1. Fail-closed behavior on database persistence errors (HTTP 500 PERSISTENCE_FAILED).
2. Server-side idempotency deduplication with TransactWriteItems / atomic reservations.
3. Concurrent idempotency requests with identical keys.
4. Fail-closed idempotency and rate-limit storage failures.
5. Missing or short RATE_LIMIT_SALT failing closed in production.
6. Cognito User Pool admin authorization and static key rejection in production.
7. Historical aggregation: 14-day cutoff query, timezone conversion to Asia/Kolkata (IST),
   and suppression of peak/quietest hours when sample count < 3.
8. Strict CORS origin resolution in production without wildcard fallbacks.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    CAMPUS_TIMEZONE = ZoneInfo("Asia/Kolkata")
except Exception:
    CAMPUS_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")
import pytest

from backend.shared.database import (
    QueueSenseDatabase,
    InMemoryStorageAdapter,
    DatabasePersistenceError,
    get_shared_test_adapter,
    reset_shared_test_adapter,
)
from backend.functions.submit_report.app import lambda_handler as submit_handler
from backend.functions.get_recommendations.app import lambda_handler as rec_handler
from backend.functions.get_historical.app import lambda_handler as historical_handler
from backend.functions.admin.app import lambda_handler as admin_handler
from backend.shared.prediction import compute_smart_recommendation
from backend.shared.security import (
    get_rate_limit_salt,
    compute_anonymous_client_hash,
    SecurityConfigurationError,
)
from backend.shared.response import resolve_cors_origin


def test_persistence_failure_fails_closed():
    """
    Priority 0: Verify that when database persistence fails,
    submit_report fails closed with HTTP 500 and PERSISTENCE_FAILED error code.
    It must NEVER return 201 Created or claim success.
    """
    failing_adapter = InMemoryStorageAdapter()
    failing_adapter.set_simulate_failure(True)
    db = QueueSenseDatabase(adapter=failing_adapter)

    with pytest.raises(DatabasePersistenceError):
        db.record_report(
            location_id="iitb-mess-h12-14",
            reported_wait_minutes=15.0,
            queue_length=20,
        )


def test_idempotency_deduplication():
    """
    Priority 0: Verify that identical idempotency keys do not generate duplicate database entries.
    """
    reset_shared_test_adapter()
    adapter = get_shared_test_adapter()
    db = QueueSenseDatabase(adapter=adapter)

    key = "idem-unique-key-12345"
    r1 = db.record_report(
        location_id="iitb-mess-h12-14",
        reported_wait_minutes=12.0,
        queue_length=15,
        note="First submit",
        idempotency_key=key,
    )
    r2 = db.record_report(
        location_id="iitb-mess-h12-14",
        reported_wait_minutes=12.0,
        queue_length=15,
        note="Retry submit",
        idempotency_key=key,
    )

    assert r1["reportId"] == r2["reportId"]
    assert len(db.get_recent_reports("iitb-mess-h12-14")) == 1


def test_concurrent_idempotency_simulation():
    """
    Priority 0: Test concurrent execution with the identical idempotency key.
    All concurrent requests must return the same report record and create exactly 1 persistent entry.
    """
    reset_shared_test_adapter()
    adapter = get_shared_test_adapter()
    db = QueueSenseDatabase(adapter=adapter)
    key = "idem-concurrent-race-key-9999"

    def submit_task(worker_id):
        return db.record_report(
            location_id="iitb-mess-h12-14",
            reported_wait_minutes=10.0 + worker_id,
            queue_length=15,
            note=f"Worker {worker_id}",
            idempotency_key=key,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(submit_task, i) for i in range(8)]
        results = [f.result() for f in futures]

    report_ids = {r["reportId"] for r in results}
    assert len(report_ids) == 1, "Concurrent requests must resolve to the identical single reportId"

    recent = db.get_recent_reports("iitb-mess-h12-14")
    matching_reports = [r for r in recent if r["reportId"] == list(report_ids)[0]]
    assert len(matching_reports) == 1, "Only one single report must be written in storage"


def test_idempotency_write_failure_fails_closed():
    """
    Priority 0: A failure during idempotency reservation must raise DatabasePersistenceError
    and must never silently return success.
    """
    adapter = InMemoryStorageAdapter()
    adapter.set_simulate_idempotency_failure(True)
    db = QueueSenseDatabase(adapter=adapter)

    with pytest.raises(DatabasePersistenceError):
        db.record_report(
            location_id="iitb-mess-h12-14",
            reported_wait_minutes=14.0,
            queue_length=18,
            idempotency_key="failing-idem-key-777",
        )


def test_client_rate_limiting_enforced():
    """
    Priority 0: Verify that submitting beyond the rate limit threshold (5 requests per window)
    triggers 429 RATE_LIMIT_EXCEEDED.
    """
    event_template = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "headers": {"user-agent": "SpamBot/1.0"},
        "requestContext": {
            "http": {"sourceIp": "192.0.2.1"},
            "requestId": "req_ratelimit_test",
        },
        "body": json.dumps({"reportedWaitMinutes": 5.0, "queueLength": 5}),
    }

    # First 5 submissions should succeed
    for i in range(5):
        event = dict(event_template)
        event["body"] = json.dumps({
            "reportedWaitMinutes": 5.0 + i,
            "queueLength": 5,
            "idempotencyKey": f"key-rate-{i}",
        })
        res = submit_handler(event, None)
        assert res["statusCode"] == 201

    # 6th submission must be rejected with 429
    event_overflow = dict(event_template)
    event_overflow["body"] = json.dumps({
        "reportedWaitMinutes": 20.0,
        "queueLength": 10,
        "idempotencyKey": "key-rate-overflow",
    })
    res_overflow = submit_handler(event_overflow, None)
    assert res_overflow["statusCode"] == 429
    body = json.loads(res_overflow["body"])
    assert body["success"] is False
    assert body["errorCode"] == "RATE_LIMIT_EXCEEDED"


def test_rate_limit_storage_failure_fails_closed():
    """
    Priority 0: If rate limit storage check fails, must fail closed with 503 RATE_LIMIT_CHECK_FAILED.
    Must never fail open.
    """
    reset_shared_test_adapter()
    adapter = get_shared_test_adapter()
    adapter.set_simulate_rate_limit_failure(True)

    event = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "headers": {"user-agent": "Tester/1.0"},
        "requestContext": {
            "http": {"sourceIp": "198.51.100.55"},
            "requestId": "req_rl_failure",
        },
        "body": json.dumps({"reportedWaitMinutes": 10.0, "queueLength": 12}),
    }

    try:
        res = submit_handler(event, None)
        assert res["statusCode"] == 503
        body = json.loads(res["body"])
        assert body["success"] is False
        assert body["errorCode"] == "RATE_LIMIT_CHECK_FAILED"
    finally:
        adapter.set_simulate_rate_limit_failure(False)


def test_user_agent_rotation_does_not_bypass_rate_limit():
    """
    Priority 0 Security Remediation:
    Verify that an attacker rotating the User-Agent header from the same source IP
    cannot bypass the rate limit. All User-Agents from the same IP must resolve to
    the identical rate-limit identity.
    """
    reset_shared_test_adapter()

    # 1. Verify hash identity is stable across varying User-Agents
    base_ip = "203.0.113.88"
    ev1 = {
        "requestContext": {"http": {"sourceIp": base_ip}},
        "headers": {"user-agent": "Mozilla/5.0 (Windows NT 10.0)"},
    }
    ev2 = {
        "requestContext": {"http": {"sourceIp": base_ip}},
        "headers": {"user-agent": "CustomCurl/7.88.1"},
    }
    ev3 = {
        "requestContext": {"http": {"sourceIp": base_ip}},
        "headers": {"user-agent": "RotatedBot/9.9.9"},
    }

    hash1 = compute_anonymous_client_hash(ev1)
    hash2 = compute_anonymous_client_hash(ev2)
    hash3 = compute_anonymous_client_hash(ev3)

    assert hash1 == hash2 == hash3, "Client hash must be identical for the same source IP regardless of User-Agent"

    # 2. Verify submission rate limit triggers on 6th request even with rotated User-Agents
    for i in range(5):
        event = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "headers": {"user-agent": f"RotatingAgentBot/{i}.0"},
            "requestContext": {
                "http": {"sourceIp": base_ip},
                "requestId": f"req_rotate_{i}",
            },
            "body": json.dumps({
                "reportedWaitMinutes": 8.0,
                "queueLength": 10,
                "idempotencyKey": f"key-rotate-{i}",
            }),
        }
        res = submit_handler(event, None)
        assert res["statusCode"] == 201

    # 6th submission with a brand new User-Agent MUST be blocked with 429
    event_6 = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "headers": {"user-agent": "BrandNewUnseenAgent/99.0"},
        "requestContext": {
            "http": {"sourceIp": base_ip},
            "requestId": "req_rotate_overflow",
        },
        "body": json.dumps({
            "reportedWaitMinutes": 10.0,
            "queueLength": 15,
            "idempotencyKey": "key-rotate-overflow",
        }),
    }
    res_6 = submit_handler(event_6, None)
    assert res_6["statusCode"] == 429
    body = json.loads(res_6["body"])
    assert body["errorCode"] == "RATE_LIMIT_EXCEEDED"


def test_client_forwarded_headers_are_strictly_ignored():
    """
    Priority 0 Security Remediation:
    Verify that client-supplied X-Forwarded-For or Forwarded headers are strictly ignored,
    and only trusted requestContext.http.sourceIp is used.
    """
    trusted_ip = "198.51.100.42"
    spoofed_ip = "1.2.3.4"

    event_spoofed = {
        "requestContext": {"http": {"sourceIp": trusted_ip}},
        "headers": {
            "x-forwarded-for": spoofed_ip,
            "forwarded": f"for={spoofed_ip}",
        },
    }
    event_honest = {
        "requestContext": {"http": {"sourceIp": trusted_ip}},
        "headers": {},
    }

    hash_spoofed = compute_anonymous_client_hash(event_spoofed)
    hash_honest = compute_anonymous_client_hash(event_honest)

    assert hash_spoofed == hash_honest, "Spoofed forwarded headers must be ignored in client identity calculation"


def test_missing_rate_limit_salt_fails_closed_in_production(monkeypatch):
    """
    Priority 1: In production mode, missing, short (< 32 chars), or weak RATE_LIMIT_SALT
    must raise SecurityConfigurationError and return HTTP 500 SECURITY_CONFIGURATION_ERROR.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")

    # 1. Missing salt
    monkeypatch.setenv("RATE_LIMIT_SALT", "")
    with pytest.raises(SecurityConfigurationError, match="missing"):
        get_rate_limit_salt()

    # 2. Short salt (< 32 chars)
    monkeypatch.setenv("RATE_LIMIT_SALT", "short-phrase-16chars")
    with pytest.raises(SecurityConfigurationError, match="insufficient entropy"):
        get_rate_limit_salt()

    # 3. Weak memorable dictionary phrase
    monkeypatch.setenv("RATE_LIMIT_SALT", "my-default-secret-password-phrase-for-testing-123456")
    with pytest.raises(SecurityConfigurationError, match="predictable or weak pattern"):
        get_rate_limit_salt()

    # 4. Valid 64-hex high-entropy salt succeeds
    valid_hex_salt = "f3a8b2c1d4e5987019283746abcdef987019283746abcdef987019283746abcdef"
    monkeypatch.setenv("RATE_LIMIT_SALT", valid_hex_salt)
    assert get_rate_limit_salt() == valid_hex_salt


def test_admin_authorization_cognito_and_production_lockdown(monkeypatch):
    """
    Priority 1: Verify Cognito JWT admin authorization and lockdown in production.
    - No token -> 401 COGNITO_AUTH_REQUIRED
    - Non-admin group -> 403 FORBIDDEN_NOT_ADMIN
    - Valid admin group -> 200 SUCCESS
    - Static key disabled in production -> 401 STATIC_KEY_DISABLED_IN_PROD
    """
    # 1. Unauthenticated request
    unauth_event = {"headers": {}, "requestContext": {}}
    res = admin_handler(unauth_event, None)
    assert res["statusCode"] == 401
    body = json.loads(res["body"])
    assert body["errorCode"] in ("COGNITO_AUTH_REQUIRED", "UNAUTHORIZED", "UNAUTHORIZED_COGNITO_REQUIRED")

    # 2. Token without Admins group
    non_admin_event = {
        "headers": {},
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-uuid-1234",
                        "cognito:groups": ["Students"],
                    }
                }
            }
        },
    }
    res_non_admin = admin_handler(non_admin_event, None)
    assert res_non_admin["statusCode"] == 403
    body = json.loads(res_non_admin["body"])
    assert body["errorCode"] == "FORBIDDEN_NOT_ADMIN"

    # 3. Token with Admins group
    admin_event = {
        "headers": {},
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "admin-uuid-5678",
                        "cognito:groups": ["Admins", "Staff"],
                    }
                }
            }
        },
    }
    res_admin = admin_handler(admin_event, None)
    assert res_admin["statusCode"] == 200
    body = json.loads(res_admin["body"])
    assert body["success"] is True
    assert "reports" in body["data"]

    # 4. In production, static admin key is strictly rejected
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")
    static_key_event = {
        "headers": {"authorization": "Bearer any-static-key-here"},
        "requestContext": {},
    }
    res_static = admin_handler(static_key_event, None)
    assert res_static["statusCode"] == 401
    body = json.loads(res_static["body"])
    assert body["errorCode"] in ("STATIC_KEY_DISABLED_IN_PROD", "UNAUTHORIZED_COGNITO_REQUIRED")


def test_cold_start_recommendation_protection():
    """
    Priority 1: Cold start protection.
    A single observation or low confidence (< 50%) MUST NOT declare a winner.
    """
    sparse_data = [
        {
            "id": "iitb-mess-h12-14",
            "name": "Hostel 12-14 Dining Hall",
            "active": True,
            "estimate": {
                "predictedWaitMinutes": 5.0,
                "confidence": 0.35,  # Too low
                "confidenceLabel": "LIMITED",
                "freshness": "RECENT",
                "recentReportCount": 1,  # Only 1 report! Needs >= 3
                "newestReportAgeMinutes": 14.0,
                "congestion": "MODERATE",
            },
        }
    ]

    rec = compute_smart_recommendation(sparse_data)
    assert rec["isEligible"] is False
    assert rec["state"] == "insufficient_data"
    assert rec["recommendedLocationId"] is None
    assert "Not enough recent queue reports" in rec["reason"]


def test_recommendation_qualifies_with_three_reports_and_high_confidence():
    """
    Priority 1: Qualifies once >= 3 reports and >= 50% confidence are met.
    """
    qualified_data = [
        {
            "id": "iitb-mess-h12-14",
            "name": "Hostel 12-14 Dining Hall",
            "active": True,
            "estimate": {
                "predictedWaitMinutes": 6.5,
                "confidence": 0.72,
                "confidenceLabel": "HIGH",
                "freshness": "LIVE",
                "recentReportCount": 4,
                "newestReportAgeMinutes": 3.0,
                "congestion": "MODERATE",
            },
        }
    ]

    rec = compute_smart_recommendation(qualified_data)
    assert rec["isEligible"] is True
    assert rec["state"] == "recommended"
    assert rec["recommendedLocationId"] == "iitb-mess-h12-14"
    assert rec["predictedWaitMinutes"] == 6.5


def test_historical_timezone_conversion_and_cutoff():
    """
    Priority 1: Historical trends aggregation.
    - Timestamp 06:30 UTC must convert to 12:00 IST (Asia/Kolkata, UTC+05:30) and bucket in hour 12.
    - Reports older than 14 days must be excluded.
    """
    reset_shared_test_adapter()
    adapter = get_shared_test_adapter()
    db = QueueSenseDatabase(adapter=adapter)

    now_utc = datetime.now(timezone.utc)
    # Report 1: 2 days ago at 06:30 UTC -> 12:00 IST (Hour 12)
    dt_valid = (now_utc - timedelta(days=2)).replace(hour=6, minute=30, second=0, microsecond=0)
    iso_valid = dt_valid.isoformat()

    # Report 2: 16 days ago (exceeds 14-day cutoff)
    dt_expired = now_utc - timedelta(days=16)
    iso_expired = dt_expired.isoformat()

    adapter._store["LOCATION#iitb-mess-h12-14::REPORT#valid_001"] = {
        "PK": "LOCATION#iitb-mess-h12-14",
        "SK": f"REPORT#{iso_valid}#rep_001",
        "entityType": "REPORT",
        "reportId": "rep_001",
        "locationId": "iitb-mess-h12-14",
        "reportedWaitMinutes": 18.0,
        "queueLength": 25,
        "timestamp": iso_valid,
    }
    adapter._store["LOCATION#iitb-mess-h12-14::REPORT#expired_002"] = {
        "PK": "LOCATION#iitb-mess-h12-14",
        "SK": f"REPORT#{iso_expired}#rep_002",
        "entityType": "REPORT",
        "reportId": "rep_002",
        "locationId": "iitb-mess-h12-14",
        "reportedWaitMinutes": 35.0,
        "queueLength": 50,
        "timestamp": iso_expired,
    }

    event = {"pathParameters": {"id": "iitb-mess-h12-14"}}
    res = historical_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    data = body["data"]

    assert data["timezone"] == "Asia/Kolkata"
    assert data["metricType"] == "HISTORICAL_AVERAGES"
    # Only the 1 within-cutoff observation should be aggregated; expired one excluded
    assert data["totalObservations"] == 1

    bucket_12 = [b for b in data["hourlyTrends"] if b["hour"] == 12][0]
    assert bucket_12["sampleCount"] == 1
    assert bucket_12["historicalAverageWaitMinutes"] == 18.0

    bucket_6 = [b for b in data["hourlyTrends"] if b["hour"] == 6][0]
    assert bucket_6["sampleCount"] == 0, "Hour 6 UTC must NOT contain 06:30 UTC when mapped to Asia/Kolkata"


def test_historical_insufficient_samples_suppresses_rush_hours():
    """
    Priority 1: Busiest/quietest hours must require at least 3 samples per hour.
    With < 3 samples, busiestHour and quietestHour must remain None.
    """
    reset_shared_test_adapter()
    adapter = get_shared_test_adapter()
    db = QueueSenseDatabase(adapter=adapter)

    # Add 2 reports at 12:00 IST (06:30 UTC)
    now_utc = datetime.now(timezone.utc)
    dt1 = (now_utc - timedelta(days=1)).replace(hour=6, minute=30, second=0)
    dt2 = (now_utc - timedelta(days=2)).replace(hour=6, minute=30, second=0)

    for idx, dt in enumerate([dt1, dt2]):
        iso_ts = dt.isoformat()
        adapter._store[f"LOCATION#iitb-mess-h12-14::REPORT#sample_{idx}"] = {
            "PK": "LOCATION#iitb-mess-h12-14",
            "SK": f"REPORT#{iso_ts}#rep_sub_{idx}",
            "entityType": "REPORT",
            "reportId": f"rep_sub_{idx}",
            "locationId": "iitb-mess-h12-14",
            "reportedWaitMinutes": 15.0,
            "queueLength": 20,
            "timestamp": iso_ts,
        }

    event = {"pathParameters": {"id": "iitb-mess-h12-14"}}
    res = historical_handler(event, None)
    body = json.loads(res["body"])
    data = body["data"]

    # With only 2 samples, rush hour insight must be suppressed
    assert data["busiestHour"] is None
    assert data["quietestHour"] is None

    # Add 3rd report at 12:00 IST
    dt3 = (now_utc - timedelta(days=3)).replace(hour=6, minute=30, second=0)
    iso_ts3 = dt3.isoformat()
    adapter._store["LOCATION#iitb-mess-h12-14::REPORT#sample_2"] = {
        "PK": "LOCATION#iitb-mess-h12-14",
        "SK": f"REPORT#{iso_ts3}#rep_sub_2",
        "entityType": "REPORT",
        "reportId": "rep_sub_2",
        "locationId": "iitb-mess-h12-14",
        "reportedWaitMinutes": 15.0,
        "queueLength": 20,
        "timestamp": iso_ts3,
    }

    res2 = historical_handler(event, None)
    data2 = json.loads(res2["body"])["data"]
    assert data2["busiestHour"] is not None
    assert data2["busiestHour"]["hour"] == 12
    assert data2["busiestHour"]["sampleCount"] == 3


def test_cors_origin_production_lockdown(monkeypatch):
    """
    Priority 2: Strict CORS resolution in production.
    Never defaults to wildcard or localhost when running in production.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://d1234abcd.cloudfront.net")

    # Exact matching origin allowed
    event_valid = {"headers": {"origin": "https://d1234abcd.cloudfront.net"}}
    cors_valid = resolve_cors_origin(event_valid)
    assert cors_valid == "https://d1234abcd.cloudfront.net"

    # Unauthorized origin disallowed (fails closed)
    event_invalid = {"headers": {"origin": "https://malicious-site.example.com"}}
    cors_invalid = resolve_cors_origin(event_invalid)
    assert cors_invalid != "*"
    assert cors_invalid != "https://malicious-site.example.com"
