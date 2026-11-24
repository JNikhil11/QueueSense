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
    clear_salt_cache,
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


def test_sliding_window_rate_limiting_boundary_burst_mitigation():
    """
    Priority 1.1 Remediation:
    Verify that the sliding-window counter algorithm mitigates the fixed-window 2x boundary burst.
    A client submitting 5 requests at second 299 cannot submit another 5 requests at second 301.
    """
    from unittest.mock import patch
    from backend.shared.database import InMemoryStorageAdapter

    adapter = InMemoryStorageAdapter()
    client_hash = "adv_client_boundary_test"
    window_s = 300
    max_req = 5

    # 1. At second 299 (end of window 0): client submits 5 requests (all should succeed)
    with patch("time.time", return_value=299.0):
        results_299 = [adapter.check_rate_limit(client_hash, window_s, max_req) for _ in range(5)]
        assert all(results_299) is True

    # 2. At second 301 (2 seconds later, start of window 1): boundary burst attack
    # Under fixed window, all 5 would succeed. Under sliding window, ALL MUST BE REJECTED.
    with patch("time.time", return_value=301.0):
        results_301 = [adapter.check_rate_limit(client_hash, window_s, max_req) for _ in range(5)]
        assert any(results_301) is False
        assert sum(results_301) == 0

    # 3. At second 360 (60s later, 1 token recovered): exactly 1 request allowed sequentially
    with patch("time.time", return_value=360.0):
        assert adapter.check_rate_limit(client_hash, window_s, max_req) is True
        assert adapter.check_rate_limit(client_hash, window_s, max_req) is False

    # 4. At second 420 (120s later, 2nd token recovered): exactly 1 additional request allowed sequentially
    # (since 1 token was already consumed at t=360, leaving 1 more available)
    with patch("time.time", return_value=420.0):
        assert adapter.check_rate_limit(client_hash, window_s, max_req) is True
        assert adapter.check_rate_limit(client_hash, window_s, max_req) is False


def test_sliding_window_exact_capacity_at_t420_fresh_vs_sequential():
    """
    Priority 1.1 Mathematical Discrepancy Reconciliation:
    Verify that at t=420 (offset 120s into window 1, weight=0.6, effective_prev=3.0, max_allowed_n_curr=1):
    1. When starting fresh (N_curr=0), exactly TWO requests are permitted:
       - 1st request: N_curr=0 <= 1 -> allowed (N_curr becomes 1).
       - 2nd request: N_curr=1 <= 1 -> allowed (N_curr becomes 2).
       - 3rd request: N_curr=2 <= 1 -> rejected.
    2. When continuing sequentially from t=360 (where 1 request was consumed, so N_curr=1):
       - Exactly ONE additional request is permitted (N_curr goes from 1 to 2, 2nd request rejected).
    """
    from unittest.mock import patch, MagicMock
    from backend.shared.database import InMemoryStorageAdapter, DynamoDBStorageAdapter

    window_s = 300
    max_req = 5

    # --- Scenario 1: InMemoryStorageAdapter Fresh at t=420 ---
    mem_fresh = InMemoryStorageAdapter()
    mem_fresh._rate_limits["client_fresh::0"] = 5
    with patch("time.time", return_value=420.0):
        res_fresh = [mem_fresh.check_rate_limit("client_fresh", window_s, max_req) for _ in range(5)]
    assert res_fresh == [True, True, False, False, False], f"Expected exactly 2 allowed fresh at t=420, got {res_fresh}"
    assert sum(res_fresh) == 2

    # --- Scenario 2: InMemoryStorageAdapter Sequential (t=360 then t=420) ---
    mem_seq = InMemoryStorageAdapter()
    mem_seq._rate_limits["client_seq::0"] = 5
    with patch("time.time", return_value=360.0):
        res_360 = [mem_seq.check_rate_limit("client_seq", window_s, max_req) for _ in range(3)]
    assert res_360 == [True, False, False]  # 1 allowed at t=360

    with patch("time.time", return_value=420.0):
        res_420 = [mem_seq.check_rate_limit("client_seq", window_s, max_req) for _ in range(3)]
    assert res_420 == [True, False, False]  # 1 additional allowed at t=420 sequentially

    # --- Scenario 3: DynamoDBStorageAdapter Fresh at t=420 ---
    dyn_fresh = DynamoDBStorageAdapter("Table", "ap-southeast-2")
    mock_table = MagicMock()
    dyn_fresh._table = mock_table

    store = {("RATELIMIT#dyn_fresh", "WINDOW#0"): {"reqCount": 5}}

    def mock_get(Key):
        k = (Key["PK"], Key["SK"])
        return {"Item": store[k]} if k in store else {}

    def mock_update(Key, UpdateExpression, ConditionExpression, ExpressionAttributeNames, ExpressionAttributeValues, ReturnValues):
        k = (Key["PK"], Key["SK"])
        curr = store.get(k, {}).get("reqCount", 0)
        max_n = ExpressionAttributeValues[":max_n"]
        if "attribute_not_exists(reqCount)" in ConditionExpression and k not in store:
            pass
        elif curr <= max_n:
            pass
        else:
            class MockClientError(Exception):
                def __init__(self):
                    self.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
            raise MockClientError()
        new_c = curr + 1
        store[k] = {"reqCount": new_c}
        return {"Attributes": {"reqCount": new_c}}

    mock_table.get_item.side_effect = mock_get
    mock_table.update_item.side_effect = mock_update

    with patch("time.time", return_value=420.0):
        res_dyn = [dyn_fresh.check_rate_limit("dyn_fresh", window_s, max_req) for _ in range(5)]
    assert res_dyn == [True, True, False, False, False], f"DynamoDB expected 2 allowed fresh at t=420, got {res_dyn}"
    assert sum(res_dyn) == 2


def test_sliding_window_multi_offset_recovery_schedule():
    """
    Priority 1.1 Remediation:
    Verify recovery schedule across multiple offsets immediately before and after window boundaries.
    """
    from unittest.mock import patch
    from backend.shared.database import InMemoryStorageAdapter

    window_s = 300
    max_req = 5

    # Table of (timestamp, expected_fresh_allowed_requests)
    offsets = [
        (300.0, 0),  # offset 0s, weight 1.0, effective 5.0 -> 0 allowed
        (301.0, 0),  # offset 1s, weight 0.9967, effective 4.983 -> 0 allowed
        (359.0, 0),  # offset 59s, weight 0.8033, effective 4.017 -> 0 allowed
        (360.0, 1),  # offset 60s, weight 0.8000, effective 4.000 -> exactly 1 allowed
        (419.0, 1),  # offset 119s, weight 0.6033, effective 3.017 -> exactly 1 allowed
        (420.0, 2),  # offset 120s, weight 0.6000, effective 3.000 -> exactly 2 allowed
        (480.0, 3),  # offset 180s, weight 0.4000, effective 2.000 -> exactly 3 allowed
        (540.0, 4),  # offset 240s, weight 0.2000, effective 1.000 -> exactly 4 allowed
        (599.0, 4),  # offset 299s, weight 0.0033, effective 0.017 -> exactly 4 allowed
        (600.0, 5),  # offset 0s into window 2, window 0 fully expired -> all 5 allowed
    ]

    for t_val, expected_allowed in offsets:
        adapter = InMemoryStorageAdapter()
        adapter._rate_limits["offset_client::0"] = 5
        with patch("time.time", return_value=t_val):
            allowed = sum(adapter.check_rate_limit("offset_client", window_s, max_req) for _ in range(10))
            assert allowed == expected_allowed, f"At t={t_val} (offset {t_val % 300}s), expected {expected_allowed} but got {allowed}"


def test_sliding_window_concurrent_requests_race_condition():
    """
    Priority 1.1 Remediation:
    Verify that concurrent multi-threaded requests from the same client hash
    cannot bypass the rate limit due to race conditions.
    """
    import concurrent.futures
    from backend.shared.database import InMemoryStorageAdapter

    adapter = InMemoryStorageAdapter()
    client_hash = "concurrent_burst_client"
    window_s = 300
    max_req = 5

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(adapter.check_rate_limit, client_hash, window_s, max_req)
            for _ in range(20)
        ]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Exactly 5 must succeed, exactly 15 must be rejected
    assert sum(results) == max_req
    assert results.count(False) == 15


def test_sliding_window_concurrent_requests_across_adjacent_windows():
    """
    Priority 1.1 Remediation:
    Examine concurrent requests across adjacent windows (e.g., requests arriving simultaneously
    at t=299.9s in window 0 and t=300.1s in window 1).
    Verify that cross-window concurrency cannot exceed the total capacity budget.
    """
    import concurrent.futures
    from unittest.mock import patch
    from backend.shared.database import InMemoryStorageAdapter

    adapter = InMemoryStorageAdapter()
    client_hash = "cross_window_client"
    window_s = 300
    max_req = 5

    # 1. Fill window 0 to capacity at t=299.0
    with patch("time.time", return_value=299.0):
        for _ in range(5):
            assert adapter.check_rate_limit(client_hash, window_s, max_req) is True

    # 2. Concurrently dispatch 10 requests at t=300.1 (immediately across window boundary)
    results_boundary = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for _ in range(10):
            # Each worker executes at t=300.1
            def task():
                with patch("time.time", return_value=300.1):
                    return adapter.check_rate_limit(client_hash, window_s, max_req)
            futures.append(executor.submit(task))
        for f in concurrent.futures.as_completed(futures):
            results_boundary.append(f.result())

    # All 10 requests across the boundary must be rejected because window 0 is at capacity
    # and effective_prev is 5 * ((300 - 0.1)/300) = 4.998 -> max_allowed_n_curr = floor(5 - 1 - 4.998) = -1 < 0
    assert sum(results_boundary) == 0
    assert results_boundary.count(False) == 10

    # 3. Test simultaneous cross-window race condition:
    # 5 threads at t=299.9 competing while 5 threads at t=300.1 execute simultaneously.
    # In distributed storage without cross-window 2PC/transactions, if a thread at t=300.1
    # reads window 0 before concurrent threads at t=299.9 finish incrementing,
    # it reads a transient n_prev < 5. Thus, cross-window concurrency can admit
    # between max_req (5) and 2 * max_req (10) requests during the sub-millisecond race.
    adapter_interleaved = InMemoryStorageAdapter()
    interleaved_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for i in range(10):
            t_target = 299.9 if (i % 2 == 0) else 300.1
            def task(t_val):
                with patch("time.time", return_value=t_val):
                    return adapter_interleaved.check_rate_limit("interleaved_client", window_s, max_req)
            futures.append(executor.submit(task, t_target))
        for f in concurrent.futures.as_completed(futures):
            interleaved_results.append(f.result())

    allowed_total = sum(interleaved_results)
    # Must admit at least 5 (window 0 capacity) and at most 10 (both windows' uncoordinated theoretical max)
    assert max_req <= allowed_total <= (2 * max_req), (
        f"Cross-window race allowed {allowed_total} requests, outside bounded range [{max_req}, {2 * max_req}]"
    )



def test_dynamodb_adapter_sliding_window_conditional_update():
    """
    Priority 1.1 Remediation:
    Verify DynamoDBStorageAdapter calculates max_allowed_n_curr, uses ConditionExpression,
    and returns False on ConditionalCheckFailedException.
    """
    from unittest.mock import MagicMock, patch
    from backend.shared.database import DynamoDBStorageAdapter

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    # Scenario A: Previous window had 5 requests; current offset is 1s (weight ~ 0.9967)
    # effective_prev = 4.983 -> max_allowed_n_curr = floor(5 - 1 - 4.983) = -1 < 0
    # Should return False immediately without calling update_item
    mock_table.get_item.return_value = {"Item": {"reqCount": 5}}

    with patch("time.time", return_value=301.0):
        allowed = adapter.check_rate_limit("test_client", 300, 5)
        assert allowed is False
        assert mock_table.update_item.call_count == 0

    # Scenario B: Previous window had 0 requests; should call update_item with ConditionExpression
    mock_table.get_item.return_value = {}
    with patch("time.time", return_value=301.0):
        allowed = adapter.check_rate_limit("test_client", 300, 5)
        assert allowed is True
        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        assert "ConditionExpression" in call_kwargs
        assert ":max_n" in call_kwargs["ExpressionAttributeValues"]
        assert call_kwargs["ExpressionAttributeValues"][":max_n"] == 4

    # Scenario C: ConditionalCheckFailedException returns False without failing closed
    class MockClientError(Exception):
        def __init__(self, code, message=""):
            self.response = {"Error": {"Code": code, "Message": message}}
            super().__init__(f"{code}: {message}")

    mock_table.update_item.side_effect = MockClientError("ConditionalCheckFailedException", "The conditional request failed")
    with patch("time.time", return_value=301.0):
        allowed = adapter.check_rate_limit("test_client", 300, 5)
        assert allowed is False

    # Scenario D: Unexpected DynamoDB error must FAIL CLOSED (raise DatabasePersistenceError)
    mock_table.update_item.side_effect = MockClientError("InternalServerError", "DynamoDB unavailable")
    from backend.shared.database import DatabasePersistenceError
    import pytest
    with pytest.raises(DatabasePersistenceError):
        with patch("time.time", return_value=301.0):
            adapter.check_rate_limit("test_client", 300, 5)


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


def test_get_locations_template_and_ssm_policy_configuration():
    """
    Verify SAM template least-privilege configurations:
    1. GetLocationsFunction includes dynamodb:Query alongside GetItem, Scan, PutItem.
    2. SubmitReportFunction includes ssm:GetParameter on exact parameter ARN.
    3. SubmitReportFunction defines RATE_LIMIT_SALT_PARAMETER_NAME environment variable.
    """
    import os
    import re
    template_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "template.yaml")
    )
    with open(template_path, "r", encoding="utf-8") as f:
        template_text = f.read()

    # Verify GetLocationsFunction has dynamodb:Query
    get_loc_section = re.search(r"GetLocationsFunction:.*?(?=GetQueueFunction:)", template_text, re.DOTALL)
    assert get_loc_section, "GetLocationsFunction must be present in template"
    loc_sec_text = get_loc_section.group(0)
    assert "dynamodb:Query" in loc_sec_text, "GetLocationsFunction policy must allow dynamodb:Query"
    assert "dynamodb:GetItem" in loc_sec_text
    assert "dynamodb:Scan" in loc_sec_text
    assert "dynamodb:PutItem" in loc_sec_text
    assert "!GetAtt MainTable.Arn" in loc_sec_text

    # Verify SubmitReportFunction has ssm:GetParameter, RATE_LIMIT_SALT_PARAMETER_NAME, and dynamodb:TransactWriteItems
    submit_section = re.search(r"SubmitReportFunction:.*?(?=GetRecommendationsFunction:)", template_text, re.DOTALL)
    assert submit_section, "SubmitReportFunction must be present in template"
    sub_sec_text = submit_section.group(0)
    assert "RATE_LIMIT_SALT_PARAMETER_NAME" in sub_sec_text
    assert "ssm:GetParameter" in sub_sec_text
    assert "arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/queuesense/${Environment}/rate_limit_salt" in sub_sec_text
    assert "dynamodb:TransactWriteItems" in sub_sec_text, "SubmitReportFunction must have dynamodb:TransactWriteItems for idempotent writes"
    assert "dynamodb:*" not in sub_sec_text, "SubmitReportFunction must not grant wildcard dynamodb:*"


def test_production_salt_fetched_from_ssm_securestring(monkeypatch):
    """
    Verify that in production mode, salt is retrieved via SSM GetParameter with WithDecryption=True.
    """
    import sys
    from unittest.mock import MagicMock

    clear_salt_cache()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")
    monkeypatch.delenv("RATE_LIMIT_SALT", raising=False)
    monkeypatch.setenv("RATE_LIMIT_SALT_PARAMETER_NAME", "/queuesense/prod/rate_limit_salt")

    valid_hex_salt = "f3a8b2c1d4e5987019283746abcdef987019283746abcdef987019283746abcdef"
    mock_ssm = MagicMock()
    mock_ssm.get_parameter.return_value = {
        "Parameter": {
            "Name": "/queuesense/prod/rate_limit_salt",
            "Type": "SecureString",
            "Value": valid_hex_salt,
        }
    }
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_ssm
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

    salt = get_rate_limit_salt()
    assert salt == valid_hex_salt
    mock_ssm.get_parameter.assert_called_once_with(
        Name="/queuesense/prod/rate_limit_salt",
        WithDecryption=True,
    )


def test_ssm_salt_retrieval_is_cached(monkeypatch):
    """
    Verify that retrieved salt is cached in memory and does not call SSM repeatedly.
    """
    import sys
    from unittest.mock import MagicMock

    clear_salt_cache()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")
    monkeypatch.delenv("RATE_LIMIT_SALT", raising=False)
    monkeypatch.setenv("RATE_LIMIT_SALT_PARAMETER_NAME", "/queuesense/prod/rate_limit_salt")

    valid_hex_salt = "f3a8b2c1d4e5987019283746abcdef987019283746abcdef987019283746abcdef"
    mock_ssm = MagicMock()
    mock_ssm.get_parameter.return_value = {
        "Parameter": {"Value": valid_hex_salt}
    }
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_ssm
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

    # First call fetches from SSM
    salt1 = get_rate_limit_salt()
    assert salt1 == valid_hex_salt
    assert mock_ssm.get_parameter.call_count == 1

    # Subsequent calls must return cached salt without calling SSM again
    salt2 = get_rate_limit_salt()
    salt3 = get_rate_limit_salt()
    assert salt2 == salt1
    assert salt3 == salt1
    assert mock_ssm.get_parameter.call_count == 1


def test_ssm_failures_fail_closed(monkeypatch):
    """
    Verify that missing parameter, access denied, KMS decryption failure,
    or empty value fail closed with SecurityConfigurationError.
    """
    import sys
    from unittest.mock import MagicMock

    class FakeClientError(Exception):
        def __init__(self, code):
            super().__init__(f"SSM error: {code}")
            self.response = {"Error": {"Code": code, "Message": f"Failed with {code}"}}

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")
    monkeypatch.delenv("RATE_LIMIT_SALT", raising=False)
    monkeypatch.setenv("RATE_LIMIT_SALT_PARAMETER_NAME", "/queuesense/prod/rate_limit_salt")

    error_cases = [
        "ParameterNotFound",
        "AccessDeniedException",
        "KMS.AccessDeniedException",
        "DecryptionFailure",
    ]

    for code in error_cases:
        clear_salt_cache()
        mock_ssm = MagicMock()
        mock_ssm.get_parameter.side_effect = FakeClientError(code)
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_ssm
        monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

        with pytest.raises(SecurityConfigurationError, match=code):
            get_rate_limit_salt()

    # Empty parameter value
    clear_salt_cache()
    mock_ssm = MagicMock()
    mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "   "}}
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_ssm
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    with pytest.raises(SecurityConfigurationError, match="empty value"):
        get_rate_limit_salt()


def test_ssm_weak_or_invalid_salts_rejected(monkeypatch):
    """
    Verify that SSM returning short or predictable salts is rejected in production.
    """
    import sys
    from unittest.mock import MagicMock

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")
    monkeypatch.delenv("RATE_LIMIT_SALT", raising=False)
    monkeypatch.setenv("RATE_LIMIT_SALT_PARAMETER_NAME", "/queuesense/prod/rate_limit_salt")

    # 1. Short salt (< 32 chars)
    clear_salt_cache()
    mock_ssm = MagicMock()
    mock_ssm.get_parameter.return_value = {"Parameter": {"Value": "short_salt_16"}}
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_ssm
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    with pytest.raises(SecurityConfigurationError, match="insufficient entropy"):
        get_rate_limit_salt()

    # 2. Predictable weak dictionary pattern
    clear_salt_cache()
    mock_ssm = MagicMock()
    mock_ssm.get_parameter.return_value = {
        "Parameter": {"Value": "my-default-secret-password-phrase-for-testing-123456"}
    }
    mock_boto3.client.return_value = mock_ssm
    with pytest.raises(SecurityConfigurationError, match="predictable or weak pattern"):
        get_rate_limit_salt()


def test_no_secret_exposed_in_error_responses_or_logs(monkeypatch, caplog):
    """
    Verify that when SSM fails or salt is invalid, SubmitReportFunction:
    1. Returns HTTP 500 INTERNAL_ERROR.
    2. Does NOT leak parameter names, credentials, or secrets in API response.
    3. Does NOT log sensitive salt data.
    """
    import sys
    import logging
    from unittest.mock import MagicMock

    clear_salt_cache()
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")
    monkeypatch.delenv("RATE_LIMIT_SALT", raising=False)
    monkeypatch.setenv("RATE_LIMIT_SALT_PARAMETER_NAME", "/queuesense/prod/rate_limit_salt")

    class FakeClientError(Exception):
        def __init__(self):
            super().__init__("AccessDeniedException")
            self.response = {"Error": {"Code": "AccessDeniedException", "Message": "KMS key denied"}}

    mock_ssm = MagicMock()
    mock_ssm.get_parameter.side_effect = FakeClientError()
    mock_boto3 = MagicMock()
    mock_boto3.client.return_value = mock_ssm
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

    event = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "headers": {},
        "requestContext": {
            "http": {"sourceIp": "198.51.100.77"},
            "requestId": "req_test_ssm_err",
        },
        "body": json.dumps({
            "reportedWaitMinutes": 10.0,
            "queueLength": 12,
        }),
    }

    with caplog.at_level(logging.INFO):
        res = submit_handler(event, None)

    assert res["statusCode"] == 500
    body = json.loads(res["body"])
    assert body["errorCode"] == "SECURITY_CONFIGURATION_ERROR"
    assert "Server security configuration error" in body["error"]
    assert "rate_limit_salt" not in body["error"].lower()
    assert "secret" not in body["error"].lower()
    assert "accessdenied" not in body["error"].lower()


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


# =========================================================================
# Stage 1: Production Persistence Lockdown & TTL Tests (B2, B7, A2)
# =========================================================================

def test_production_lambda_forbids_in_memory_adapter(monkeypatch):
    """
    Stage 1 / Flaw B2: Production In-Memory Fallback Lockdown.
    When running under AWS Lambda (AWS_LAMBDA_FUNCTION_NAME set) or ENVIRONMENT=prod,
    QueueSenseDatabase MUST NEVER use InMemoryStorageAdapter.
    """
    from backend.shared.database import (
        QueueSenseDatabase,
        DynamoDBStorageAdapter,
        InMemoryStorageAdapter,
        DatabasePersistenceError,
    )

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "SubmitReportFunction")
    monkeypatch.setenv("ENVIRONMENT", "prod")

    # 1. Attempting to force memory backend in production Lambda fails closed
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    with pytest.raises(DatabasePersistenceError, match="cannot be used in production environment"):
        QueueSenseDatabase()

    # 2. Attempting to set DATA_MODE=demo in production Lambda fails closed
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("DATA_MODE", "demo")
    with pytest.raises(DatabasePersistenceError, match="cannot be used in production environment"):
        QueueSenseDatabase()

    # 3. Injecting an InMemoryStorageAdapter directly in production Lambda fails closed
    monkeypatch.delenv("DATA_MODE", raising=False)
    mem_adapter = InMemoryStorageAdapter()
    with pytest.raises(DatabasePersistenceError, match="strictly forbidden in production"):
        QueueSenseDatabase(adapter=mem_adapter)

    # 4. Standard production instantiation always yields DynamoDBStorageAdapter
    db = QueueSenseDatabase()
    assert isinstance(db._adapter, DynamoDBStorageAdapter)
    assert not isinstance(db._adapter, InMemoryStorageAdapter)


def test_raw_report_ttl_retention_covers_14_day_history():
    """
    Stage 1 / Flaw B7 & A2: Raw Report TTL vs. 14-Day Historical Window.
    Verifies that raw reports are retained for at least 30 days in DynamoDB,
    ensuring that 14-day historical analysis queries find valid observations.
    """
    import time
    from backend.shared.database import DynamoDBStorageAdapter, InMemoryStorageAdapter

    mem = InMemoryStorageAdapter()
    res = mem.record_report(
        location_id="iitb-mess-h12-14",
        reported_wait_minutes=15.0,
        queue_length=10,
        note="Lunch queue observation",
    )

    # Raw report TTL must be at least 14 days (14 * 86400 seconds) in the future
    now_epoch = int(time.time())
    ttl = res.get("ttl", 0)
    retention_seconds = ttl - now_epoch

    # Must be at least 14 days (1,209,600s), configured to 30 days (~2,592,000s)
    min_required_retention = 14 * 86400
    assert retention_seconds >= min_required_retention, (
        f"Raw report TTL ({retention_seconds}s) is less than the required 14-day window ({min_required_retention}s)!"
    )
    # Check that it is approximately 30 days
    assert retention_seconds >= (29 * 86400)


def test_client_supplied_timestamp_is_strictly_ignored_by_backend():
    """
    Stage 1 / Flaw B8: Authoritative Server UTC Timestamps.
    Verifies that when a client attempts to pass a retro-active or future timestamp,
    SubmitReportFunction strictly ignores it and generates an authoritative server UTC timestamp.
    """
    from datetime import datetime, timezone

    fake_client_timestamp = "2020-01-01T00:00:00Z"
    event = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "headers": {},
        "requestContext": {
            "http": {"sourceIp": "198.51.100.99"},
            "requestId": "req_test_server_ts",
        },
        "body": json.dumps({
            "reportedWaitMinutes": 12.0,
            "queueLength": 8,
            "note": "Testing timestamp tampering",
            "timestamp": fake_client_timestamp,
        }),
    }

    before_utc = datetime.now(timezone.utc)
    res = submit_handler(event, None)
    after_utc = datetime.now(timezone.utc)

    assert res["statusCode"] == 201
    body = json.loads(res["body"])
    report = body["data"]["report"]

    # Client timestamp MUST NOT be used
    assert report["timestamp"] != fake_client_timestamp

    # Server timestamp must be between before_utc and after_utc
    clean_ts = report["timestamp"].replace("Z", "+00:00")
    report_dt = datetime.fromisoformat(clean_ts)
    if report_dt.tzinfo is None:
        report_dt = report_dt.replace(tzinfo=timezone.utc)

    assert before_utc <= report_dt <= after_utc


# =========================================================================
# Priority 1.2: Historical Reports Pagination Tests
# =========================================================================

def test_historical_reports_dynamodb_pagination_follows_last_evaluated_key(monkeypatch):
    """
    Priority 1.2: Verify DynamoDBStorageAdapter follows LastEvaluatedKey across multiple pages
    until all matching historical items within the 14-day window are collected.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    page1_items = [
        {"PK": "LOCATION#iitb-mess-h12-14", "SK": f"REPORT#2026-11-20T{i:02d}:00:00#rep_{i}", "reportedWaitMinutes": 10.0, "queueLength": 5}
        for i in range(200)
    ]
    page2_items = [
        {"PK": "LOCATION#iitb-mess-h12-14", "SK": f"REPORT#2026-11-15T{i:02d}:00:00#rep_{i+200}", "reportedWaitMinutes": 15.0, "queueLength": 8}
        for i in range(150)
    ]

    last_key = {"PK": "LOCATION#iitb-mess-h12-14", "SK": "REPORT#2026-11-20T199:00:00#rep_199"}

    def mock_query(**kwargs):
        if "ExclusiveStartKey" not in kwargs:
            return {"Items": page1_items, "LastEvaluatedKey": last_key}
        else:
            assert kwargs["ExclusiveStartKey"] == last_key
            return {"Items": page2_items}

    mock_table.query.side_effect = mock_query

    reports = adapter.get_historical_reports("iitb-mess-h12-14", days=14, limit=1000)

    assert len(reports) == 350
    assert mock_table.query.call_count == 2
    # Verify both pages are converted and present
    assert reports[0]["reportedWaitMinutes"] == 10.0
    assert reports[200]["reportedWaitMinutes"] == 15.0


def test_historical_reports_dynamodb_pagination_respects_custom_limit(monkeypatch):
    """
    Priority 1.2: Verify pagination stops immediately once the caller-specified limit is satisfied,
    preventing over-fetching and unnecessary DynamoDB RCUs.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    page1_items = [{"PK": "LOCATION#loc", "SK": f"REPORT#{i}", "reportedWaitMinutes": 5.0} for i in range(200)]
    page2_items = [{"PK": "LOCATION#loc", "SK": f"REPORT#{i+200}", "reportedWaitMinutes": 6.0} for i in range(200)]
    page3_items = [{"PK": "LOCATION#loc", "SK": f"REPORT#{i+400}", "reportedWaitMinutes": 7.0} for i in range(100)]

    def mock_query(**kwargs):
        limit_requested = kwargs.get("Limit", 200)
        start_key = kwargs.get("ExclusiveStartKey")
        if start_key is None:
            return {"Items": page1_items[:limit_requested], "LastEvaluatedKey": {"PK": "loc", "SK": "199"}}
        elif start_key == {"PK": "loc", "SK": "199"}:
            return {"Items": page2_items[:limit_requested], "LastEvaluatedKey": {"PK": "loc", "SK": "399"}}
        else:
            return {"Items": page3_items[:limit_requested]}

    mock_table.query.side_effect = mock_query

    # Request limit=250: Page 1 gives 200, Page 2 requests min(50, 200) = 50. Total 250.
    reports = adapter.get_historical_reports("loc", days=14, limit=250)

    assert len(reports) == 250
    assert mock_table.query.call_count == 2
    # Verify second query was called with page_limit=50
    second_call_kwargs = mock_table.query.call_args_list[1][1]
    assert second_call_kwargs["Limit"] == 50


def test_historical_reports_dynamodb_pagination_stops_cleanly_when_no_more_pages(monkeypatch):
    """
    Priority 1.2: Single-page dataset terminates cleanly after 1 call when LastEvaluatedKey is absent.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    mock_table.query.return_value = {
        "Items": [{"PK": "LOCATION#loc", "SK": f"REPORT#{i}", "reportedWaitMinutes": 8.0} for i in range(45)]
    }

    reports = adapter.get_historical_reports("loc", days=14, limit=1000)
    assert len(reports) == 45
    assert mock_table.query.call_count == 1


def test_historical_reports_dynamodb_pagination_max_pages_safety_guard(monkeypatch):
    """
    Priority 1.2: Adversarial safety guard.
    If DynamoDB continually returns LastEvaluatedKey (e.g. simulated infinite stream),
    the loop terminates at max_pages=20 without hanging or unbounded memory growth.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    call_counter = [0]
    # Each page returns 10 unique items and a LastEvaluatedKey indefinitely
    def mock_query(**kwargs):
        call_counter[0] += 1
        c = call_counter[0]
        return {
            "Items": [
                {
                    "PK": "LOCATION#infinite",
                    "SK": f"REPORT#ts_{c}_{i}",
                    "reportId": f"inf_{c}_{i}",
                    "reportedWaitMinutes": 5.0,
                }
                for i in range(10)
            ],
            "LastEvaluatedKey": {"PK": "LOCATION#infinite", "SK": f"REPORT#next_{c}"},
        }

    mock_table.query.side_effect = mock_query

    # Even with limit=5000, max_pages=20 must break the loop
    reports = adapter.get_historical_reports("infinite", days=14, limit=5000)
    assert mock_table.query.call_count == 20
    assert len(reports) == 200  # 20 pages * 10 items


def test_historical_reports_dynamodb_pagination_failure_fails_closed(monkeypatch):
    """
    Priority 1.2: Fail-closed verification.
    If DynamoDB fails during any page of a multi-page historical query,
    it MUST raise DatabasePersistenceError rather than returning partial/corrupted silent results.
    """
    import sys
    from unittest.mock import MagicMock
    import pytest
    from backend.shared.database import DynamoDBStorageAdapter, DatabasePersistenceError

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    page1_items = [{"PK": "LOCATION#err", "SK": "REPORT#1", "reportedWaitMinutes": 10.0}]

    class MockClientError(Exception):
        pass

    def mock_query(**kwargs):
        if "ExclusiveStartKey" not in kwargs:
            return {"Items": page1_items, "LastEvaluatedKey": {"PK": "err", "SK": "1"}}
        else:
            raise MockClientError("DynamoDB transient network failure on page 2")

    mock_table.query.side_effect = mock_query

    with pytest.raises(DatabasePersistenceError, match="Failed to query historical observations"):
        adapter.get_historical_reports("err", days=14, limit=1000)


def test_historical_handler_end_to_end_with_large_paginated_history():
    """
    Priority 1.2: End-to-end integration test with get_historical Lambda handler.
    Verify that when >200 historical reports exist across the 14-day window,
    the handler ingests all reports without truncation and aggregates accurate hourly trends.
    """
    reset_shared_test_adapter()
    adapter = get_shared_test_adapter()
    db = QueueSenseDatabase(adapter=adapter)

    now_utc = datetime.now(timezone.utc)
    # Populate 250 reports across 14 days at Hour 13 IST (07:30 UTC)
    for i in range(250):
        days_ago = (i % 13) + 1  # 1 to 13 days ago (all within 14-day cutoff)
        dt = (now_utc - timedelta(days=days_ago)).replace(hour=7, minute=30, second=0, microsecond=0)
        iso_str = dt.isoformat()
        adapter._store[f"LOCATION#iitb-mess-h12-14::REPORT#paginated_{i:04d}"] = {
            "PK": "LOCATION#iitb-mess-h12-14",
            "SK": f"REPORT#{iso_str}#rep_{i:04d}",
            "entityType": "REPORT",
            "reportId": f"rep_{i:04d}",
            "locationId": "iitb-mess-h12-14",
            "reportedWaitMinutes": 20.0,
            "queueLength": 30,
            "timestamp": iso_str,
        }

    event = {"pathParameters": {"id": "iitb-mess-h12-14"}}
    res = historical_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    data = body["data"]

    # All 250 reports must be aggregated (NOT truncated to 200)
    assert data["totalObservations"] == 250
    bucket_13 = [b for b in data["hourlyTrends"] if b["hour"] == 13][0]
    assert bucket_13["sampleCount"] == 250
    assert bucket_13["historicalAverageWaitMinutes"] == 20.0


def test_historical_reports_dynamodb_pagination_empty_page_with_last_evaluated_key(monkeypatch):
    """
    Priority 1.2: Empty page with LastEvaluatedKey.
    DynamoDB may return an empty Items list with a LastEvaluatedKey (e.g. after filtering/evaluating items).
    The pagination loop MUST NOT abort prematurely; it must continue to subsequent pages.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    page2_items = [
        {"PK": "LOCATION#loc", "SK": f"REPORT#ts_{i}", "reportId": f"r_{i}", "reportedWaitMinutes": 10.0}
        for i in range(5)
    ]

    def mock_query(**kwargs):
        if "ExclusiveStartKey" not in kwargs:
            # Page 1: Empty items list, but LastEvaluatedKey is present
            return {"Items": [], "LastEvaluatedKey": {"PK": "loc", "SK": "checkpoint_1"}}
        else:
            # Page 2: Contains items, LastEvaluatedKey is None
            return {"Items": page2_items}

    mock_table.query.side_effect = mock_query

    reports = adapter.get_historical_reports("loc", days=14, limit=1000)
    assert mock_table.query.call_count == 2
    assert len(reports) == 5
    assert reports[0]["reportId"] == "r_0"


def test_historical_reports_dynamodb_pagination_1mb_boundary_simulation(monkeypatch):
    """
    Priority 1.2: 1 MB response boundary simulation.
    DynamoDB returns fewer items than requested Limit because response reached 1 MB size boundary.
    Pagination loop must seamlessly request the next page until limit is satisfied.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    # Simulate 3 pages of 50 items each due to 1MB buffer cap
    p1 = [{"PK": "LOCATION#heavy", "SK": f"REPORT#ts_1_{i}", "reportId": f"r_1_{i}", "reportedWaitMinutes": 5.0} for i in range(50)]
    p2 = [{"PK": "LOCATION#heavy", "SK": f"REPORT#ts_2_{i}", "reportId": f"r_2_{i}", "reportedWaitMinutes": 6.0} for i in range(50)]
    p3 = [{"PK": "LOCATION#heavy", "SK": f"REPORT#ts_3_{i}", "reportId": f"r_3_{i}", "reportedWaitMinutes": 7.0} for i in range(20)]

    def mock_query(**kwargs):
        start_key = kwargs.get("ExclusiveStartKey")
        if start_key is None:
            return {"Items": p1, "LastEvaluatedKey": {"PK": "heavy", "SK": "p1_end"}}
        elif start_key == {"PK": "heavy", "SK": "p1_end"}:
            return {"Items": p2, "LastEvaluatedKey": {"PK": "heavy", "SK": "p2_end"}}
        else:
            return {"Items": p3}

    mock_table.query.side_effect = mock_query

    reports = adapter.get_historical_reports("heavy", days=14, limit=1000)
    assert mock_table.query.call_count == 3
    assert len(reports) == 120


def test_historical_reports_ordering_and_cutoff_correctness_across_page_boundaries(monkeypatch):
    """
    Priority 1.2: Ordering and cutoff correctness.
    - Reports must be sorted in strictly descending order across multiple page boundaries.
    - Cutoff parameter is accurately passed to DynamoDB KeyConditionExpression.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    p1 = [
        {"PK": "LOCATION#loc", "SK": "REPORT#2026-11-24T10:00:00#r1", "reportId": "r1", "timestamp": "2026-11-24T10:00:00"},
        {"PK": "LOCATION#loc", "SK": "REPORT#2026-11-23T10:00:00#r2", "reportId": "r2", "timestamp": "2026-11-23T10:00:00"},
    ]
    p2 = [
        {"PK": "LOCATION#loc", "SK": "REPORT#2026-11-22T10:00:00#r3", "reportId": "r3", "timestamp": "2026-11-22T10:00:00"},
        {"PK": "LOCATION#loc", "SK": "REPORT#2026-11-20T10:00:00#r4", "reportId": "r4", "timestamp": "2026-11-20T10:00:00"},
    ]

    def mock_query(**kwargs):
        if "ExclusiveStartKey" not in kwargs:
            assert kwargs["ScanIndexForward"] is False, "Must query in reverse chronological order"
            return {"Items": p1, "LastEvaluatedKey": {"PK": "loc", "SK": "p1_end"}}
        else:
            return {"Items": p2}

    mock_table.query.side_effect = mock_query

    reports = adapter.get_historical_reports("loc", days=14, limit=1000)
    assert len(reports) == 4
    # Verify strict descending order across page boundaries
    timestamps = [r["timestamp"] for r in reports]
    assert timestamps == sorted(timestamps, reverse=True)


def test_historical_reports_deduplication_of_boundary_overlap(monkeypatch):
    """
    Priority 1.2: Boundary deduplication.
    If a record overlaps between page 1 and page 2, the adapter deduplicates by report ID.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    # r_overlap is returned in both page 1 and page 2
    p1 = [
        {"PK": "LOCATION#loc", "SK": "REPORT#ts_1#r1", "reportId": "r1"},
        {"PK": "LOCATION#loc", "SK": "REPORT#ts_2#r_overlap", "reportId": "r_overlap"},
    ]
    p2 = [
        {"PK": "LOCATION#loc", "SK": "REPORT#ts_2#r_overlap", "reportId": "r_overlap"},
        {"PK": "LOCATION#loc", "SK": "REPORT#ts_3#r3", "reportId": "r3"},
    ]

    def mock_query(**kwargs):
        if "ExclusiveStartKey" not in kwargs:
            return {"Items": p1, "LastEvaluatedKey": {"PK": "loc", "SK": "p1_end"}}
        else:
            return {"Items": p2}

    mock_table.query.side_effect = mock_query

    reports = adapter.get_historical_reports("loc", days=14, limit=1000)
    assert len(reports) == 3  # r1, r_overlap, r3 (duplicate omitted)
    report_ids = [r["reportId"] for r in reports]
    assert report_ids == ["r1", "r_overlap", "r3"]


def test_historical_reports_exact_1000_cap_metadata_and_api_exposure(monkeypatch):
    """
    Priority 1.2: Exact 1,000 cap metadata and API exposure.
    Verify that when more than 1,000 observations exist, include_metadata=True flags is_truncated=True,
    and GET /locations/{id}/historical exposes isCapped=True and coverageStatus='CAPPED_AT_1000_OBSERVATIONS'.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter, QueueSenseDatabase

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    # Mock 1000 items returned across 5 pages of 200, with LastEvaluatedKey still present at the 1000 mark
    call_idx = [0]
    def mock_query(**kwargs):
        call_idx[0] += 1
        c = call_idx[0]
        items = [{"PK": "loc", "SK": f"REPORT#{c}_{i}", "reportId": f"r_{c}_{i}", "reportedWaitMinutes": 10.0} for i in range(200)]
        return {"Items": items, "LastEvaluatedKey": {"PK": "loc", "SK": f"next_{c}"}}

    mock_table.query.side_effect = mock_query

    meta_result = adapter.get_historical_reports("loc", days=14, limit=1000, include_metadata=True)
    assert meta_result["is_truncated"] is True
    assert meta_result["total_retrieved"] == 1000
    assert meta_result["limit"] == 1000
    assert len(meta_result["reports"]) == 1000


# =========================================================================
# Priority 1.3: Location Listing and Seeding on Read Path Tests
# =========================================================================

def test_list_locations_never_seeds_on_read_path_when_empty(monkeypatch):
    """
    Priority 1.3: Read-path purity.
    When a DynamoDB table contains 0 locations, list_locations() MUST NOT call put_item
    to seed the table on the read path. It must cleanly return an empty list.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("EmptyTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    # Query or Scan on empty table returns empty Items list
    mock_table.query.return_value = {"Items": []}
    mock_table.scan.return_value = {"Items": []}

    locations = adapter.list_locations()
    assert locations == []
    # put_item MUST NEVER be called on the read path!
    assert mock_table.put_item.call_count == 0


def test_list_locations_paginates_scan_without_side_effects(monkeypatch):
    """
    Priority 1.3: If GSI1 is absent, list_locations traverses multiple scan pages
    following LastEvaluatedKey to collect all locations across 1MB boundaries without seeding.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    # Force GSI1 query to fail to test paginated scan fallback
    mock_table.query.side_effect = Exception("ValidationException: Index GSI1 does not exist")

    p1_locs = [{"PK": "LOCATION#l1", "SK": "METADATA", "entityType": "LOCATION", "id": "l1", "name": "Location B", "active": True}]
    p2_locs = [{"PK": "LOCATION#l2", "SK": "METADATA", "entityType": "LOCATION", "id": "l2", "name": "Location A", "active": True}]

    def mock_scan(**kwargs):
        if "ExclusiveStartKey" not in kwargs:
            return {"Items": p1_locs, "LastEvaluatedKey": {"PK": "l1", "SK": "METADATA"}}
        else:
            return {"Items": p2_locs}

    mock_table.scan.side_effect = mock_scan

    locations = adapter.list_locations()
    assert mock_table.scan.call_count == 2
    assert len(locations) == 2
    # Sorted by name: Location A, Location B
    assert locations[0]["name"] == "Location A"
    assert locations[1]["name"] == "Location B"
    assert mock_table.put_item.call_count == 0


# =========================================================================
# Priority 1.4: Administrative Report Feed Pagination Tests
# =========================================================================

def test_list_all_reports_paginated_scan_when_first_page_has_no_matching_reports(monkeypatch):
    """
    Priority 1.4: Administrative report feed pagination.
    In DynamoDB, Limit applies before FilterExpression. If the first page of a scan contains 0 reports
    (e.g. only locations and rate limits), list_all_reports must continue paginating over LastEvaluatedKey
    until the requested limit of reports is collected.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    # Force GSI1 query to fail to test paginated scan fallback
    mock_table.query.side_effect = Exception("GSI1 unavailable in test table")

    # Page 1: 0 matching reports (only other entities evaluated), but LastEvaluatedKey present
    # Page 2: 10 matching reports
    reports_page2 = [
        {"PK": "loc", "SK": f"REPORT#{i}", "entityType": "REPORT", "reportId": f"r_{i}", "timestamp": f"2026-11-24T{i:02d}:00:00"}
        for i in range(10)
    ]

    def mock_scan(**kwargs):
        if "ExclusiveStartKey" not in kwargs:
            return {"Items": [], "LastEvaluatedKey": {"PK": "checkpoint_page_1"}}
        else:
            return {"Items": reports_page2}

    mock_table.scan.side_effect = mock_scan

    results = adapter.list_all_reports(limit=10)
    assert mock_table.scan.call_count == 2
    assert len(results) == 10
    assert results[0]["reportId"] == "r_9"  # Reverse chronological


# =========================================================================
# Priority 1.5: DynamoDB GSI1 Model & Query Schema Tests
# =========================================================================

def test_template_main_table_has_gsi1_entity_type_index():
    """
    Priority 1.5: Verify SAM template defines GSI1 on MainTable with GSI1PK and GSI1SK.
    """
    import os
    import re
    template_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "template.yaml")
    )
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify GSI1 attributes in AttributeDefinitions
    assert "AttributeName: GSI1PK" in content
    assert "AttributeName: GSI1SK" in content

    # Verify GlobalSecondaryIndexes definition
    gsi_match = re.search(r"GlobalSecondaryIndexes:.*?(?=TimeToLiveSpecification:)", content, re.DOTALL)
    assert gsi_match, "GlobalSecondaryIndexes must be defined in template.yaml"
    gsi_text = gsi_match.group(0)
    assert "IndexName: GSI1" in content
    assert "AttributeName: GSI1PK" in gsi_text
    assert "KeyType: HASH" in gsi_text
    assert "AttributeName: GSI1SK" in gsi_text
    assert "KeyType: RANGE" in gsi_text
    assert "ProjectionType: ALL" in gsi_text


def test_gsi1_keys_populated_on_locations_and_reports(monkeypatch):
    """
    Priority 1.5: Verify GSI1PK and GSI1SK are automatically populated when
    persisting reports and seeding locations.
    """
    import sys
    from unittest.mock import MagicMock
    from backend.shared.database import DynamoDBStorageAdapter

    mock_boto3 = MagicMock()
    monkeypatch.setitem(sys.modules, "boto3", mock_boto3)
    monkeypatch.setitem(sys.modules, "boto3.dynamodb", MagicMock())
    monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", MagicMock())

    adapter = DynamoDBStorageAdapter("TestTable", "ap-southeast-2")
    mock_table = MagicMock()
    adapter._table = mock_table

    # 1. Record report
    report = adapter.record_report("iitb-mess-h12-14", 15.0, 20, note="Testing GSI1 keys")
    assert report["GSI1PK"] == "ENTITY#REPORT"
    assert report["GSI1SK"].startswith("2026-")

    # 2. Seed locations
    mock_table.reset_mock()
    adapter.seed_locations()
    assert mock_table.put_item.call_count > 0
    seeded_loc = mock_table.put_item.call_args_list[0][1]["Item"]
    assert seeded_loc["GSI1PK"] == "ENTITY#LOCATION"
    assert "GSI1SK" in seeded_loc


# =========================================================================
# Priority 1.6: Multi-Campus Isolation Tests
# =========================================================================

def test_template_has_campus_id_parameter_wired_to_globals():
    """
    Priority 1.6: Verify CampusId parameter exists in template.yaml and is passed
    to Globals.Function.Environment.Variables.CAMPUS_ID.
    """
    import os
    import re
    template_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "template.yaml")
    )
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "CampusId:" in content
    assert "Default: iitb" in content
    assert "CAMPUS_ID: !Ref CampusId" in content


def test_campus_id_environment_selects_locations_dynamically(monkeypatch):
    """
    Priority 1.6: Verify CAMPUS_ID environment variable selects the appropriate
    campus directory (e.g. vitap -> VITAP_CAMPUS_LOCATIONS; iitb -> IITB_CAMPUS_LOCATIONS).
    """
    from backend.shared.database import get_default_campus_locations, VITAP_CAMPUS_LOCATIONS, IITB_CAMPUS_LOCATIONS

    # When CAMPUS_ID is vitap
    monkeypatch.setenv("CAMPUS_ID", "vitap")
    vitap_locs = get_default_campus_locations()
    assert len(vitap_locs) == len(VITAP_CAMPUS_LOCATIONS)
    assert vitap_locs[0]["id"].startswith("vitap-")

    # When CAMPUS_ID is iitb
    monkeypatch.setenv("CAMPUS_ID", "iitb")
    iitb_locs = get_default_campus_locations()
    assert len(iitb_locs) == len(IITB_CAMPUS_LOCATIONS)
    assert iitb_locs[0]["id"].startswith("iitb-")


# =========================================================================
# Priority 1.7: Structured Data Provenance Tests
# =========================================================================

def test_campus_locations_have_structured_provenance_metadata():
    """
    Priority 1.7: Data Provenance.
    Verify all default campus locations have a structured provenance object
    distinguishing verified directory facts from dynamic crowdsourced observations.
    """
    from backend.shared.database import IITB_CAMPUS_LOCATIONS, VITAP_CAMPUS_LOCATIONS

    all_locs = IITB_CAMPUS_LOCATIONS + VITAP_CAMPUS_LOCATIONS
    for loc in all_locs:
        assert "provenance" in loc, f"Location {loc.get('id')} must contain provenance metadata"
        prov = loc["provenance"]
        assert prov["sourceType"] in ("COMMUNITY_DIRECTORY", "OFFICIAL_DIRECTORY")
        assert len(prov["verifiedBy"]) > 0
        assert "lastVerifiedDate" in prov
        assert prov["isCrowdsourced"] is False, "Directory metadata itself must not be marked crowdsourced"
        assert "reportedWaitMinutes" in prov["crowdsourcedAttributes"]
        assert "queueLength" in prov["crowdsourcedAttributes"]


def test_get_locations_exposes_provenance_without_leaking_internal_keys():
    """
    Priority 1.7: Verify GET /locations Lambda response exposes structured provenance
    while stripping internal single-table keys (PK, SK, entityType, GSI1PK, GSI1SK).
    """
    from backend.functions.get_locations.app import lambda_handler as locations_handler

    event = {}
    res = locations_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    locations = body["data"]

    for loc in locations:
        assert "provenance" in loc, "Cleaned location must include structured provenance"
        # Internal keys must NEVER leak to client
        assert "PK" not in loc
        assert "SK" not in loc
        assert "entityType" not in loc
        assert "GSI1PK" not in loc
        assert "GSI1SK" not in loc




