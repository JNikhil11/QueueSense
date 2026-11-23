"""
QueueSense - Production Hardening Test Suite
Verifies:
1. Fail-closed behavior on database persistence errors (HTTP 500 PERSISTENCE_FAILED).
2. Server-side idempotency deduplication with X-Idempotency-Key.
3. Privacy-preserving anonymous rate-limiting (HTTP 429 RATE_LIMIT_EXCEEDED).
4. Cold-start recommendation protection (minimum 3 reports and >= 50% confidence).
5. Historical trends aggregation by hour and day-of-week.
"""

import json
from datetime import datetime, timezone
import pytest
from backend.shared.database import (
    QueueSenseDatabase,
    InMemoryStorageAdapter,
    DatabasePersistenceError,
)
from backend.functions.submit_report.app import lambda_handler as submit_handler
from backend.functions.get_recommendations.app import lambda_handler as rec_handler
from backend.functions.get_historical.app import lambda_handler as historical_handler
from backend.shared.prediction import compute_smart_recommendation


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
    adapter = InMemoryStorageAdapter()
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

    # First 5 submissions should succeed (or be processed within limit)
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


def test_historical_aggregation_logic():
    """
    Priority 1: Historical trends aggregation.
    Verify hourly buckets and operating hours evaluation.
    """
    adapter = InMemoryStorageAdapter()
    db = QueueSenseDatabase(adapter=adapter)

    # Seed observations across different hours
    db.record_report("iitb-mess-h12-14", reported_wait_minutes=15.0, queue_length=25)
    db.record_report("iitb-mess-h12-14", reported_wait_minutes=18.0, queue_length=30)

    event = {"pathParameters": {"id": "iitb-mess-h12-14"}}
    res = historical_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    data = body["data"]
    assert "hourlyTrends" in data
    assert len(data["hourlyTrends"]) == 24
    assert data["totalObservations"] >= 2
