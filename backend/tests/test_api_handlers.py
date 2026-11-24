"""
Integration tests for QueueSense Lambda Handlers.
Invokes handler functions directly with synthetic API Gateway HTTP API events.
"""

import json
from backend.functions.health.app import lambda_handler as health_handler
from backend.functions.get_locations.app import lambda_handler as locations_handler
from backend.functions.get_queue.app import lambda_handler as queue_handler
from backend.functions.submit_report.app import lambda_handler as submit_handler
from backend.functions.get_recommendations.app import lambda_handler as rec_handler
from backend.functions.admin.app import lambda_handler as admin_handler
from backend.functions.get_historical.app import lambda_handler as historical_handler


def test_health_handler():
    res = health_handler({}, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"


def test_get_locations_handler():
    res = locations_handler({}, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    assert len(body["data"]) >= 5
    first_loc = body["data"][0]
    assert "estimate" in first_loc


def test_submit_report_and_get_queue():
    # Submit report to authentic IIT Bombay outlet
    target_id = "iitb-mess-h12-14"
    event = {
        "pathParameters": {"id": target_id},
        "body": json.dumps({
            "reportedWaitMinutes": 7.5,
            "queueLength": 12,
            "note": "Line moving briskly",
        }),
    }
    res_sub = submit_handler(event, None)
    assert res_sub["statusCode"] == 201
    body_sub = json.loads(res_sub["body"])
    assert body_sub["success"] is True
    assert body_sub["data"]["report"]["reportedWaitMinutes"] == 7.5

    # Check queue endpoint
    q_event = {
        "pathParameters": {"id": target_id},
    }
    res_q = queue_handler(q_event, None)
    assert res_q["statusCode"] == 200
    body_q = json.loads(res_q["body"])
    assert body_q["success"] is True
    assert body_q["data"]["location"]["id"] == target_id
    assert len(body_q["data"]["reports"]) >= 1


def test_submit_report_validation_failure():
    event = {
        "pathParameters": {"id": "mess-a-central"},
        "body": json.dumps({
            "reportedWaitMinutes": -10,  # Invalid negative
        }),
    }
    res = submit_handler(event, None)
    assert res["statusCode"] == 422
    body = json.loads(res["body"])
    assert body["success"] is False
    assert "negative" in body["error"]


def test_get_recommendations_handler():
    res = rec_handler({}, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    assert "reason" in body["data"]


def test_admin_reports_handler_authorized():
    event = {
        "queryStringParameters": {"limit": "10"},
        "headers": {"Authorization": "Bearer queuesense-admin-secret-dev-key"},
    }
    res = admin_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    assert "reports" in body["data"]


def test_admin_reports_handler_unauthorized():
    event = {
        "queryStringParameters": {"limit": "10"},
        "headers": {},
    }
    res = admin_handler(event, None)
    assert res["statusCode"] == 401
    body = json.loads(res["body"])
    assert body["success"] is False
    assert body["errorCode"] == "UNAUTHORIZED"


def test_get_historical_handler():
    event = {"pathParameters": {"id": "iitb-mess-h12-14"}}
    res = historical_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    assert "hourlyTrends" in body["data"]
    assert len(body["data"]["hourlyTrends"]) == 24
    assert body["data"]["locationId"] == "iitb-mess-h12-14"


def test_get_recommendations_handler_fail_closed_verification(monkeypatch):
    """Handler-level test verifying fail-closed policy: only recognized verified statuses qualify."""
    qualifying_estimate_verified = {
        "predictedWaitMinutes": 15.0,
        "predictedQueueLength": 20,
        "congestion": "MODERATE",
        "confidence": 0.85,
        "confidenceLabel": "HIGH",
        "freshness": "LIVE",
        "recentReportCount": 4,
        "distinctDevicesCount": 4,
        "newestReportAgeMinutes": 2.0,
    }
    qualifying_estimate_unverified = {
        "predictedWaitMinutes": 3.0,  # Shorter wait, but unverified
        "predictedQueueLength": 5,
        "congestion": "LOW",
        "confidence": 0.90,
        "confidenceLabel": "HIGH",
        "freshness": "LIVE",
        "recentReportCount": 5,
        "distinctDevicesCount": 5,
        "newestReportAgeMinutes": 1.0,
    }

    mock_locations = [
        # 1. Verified active outlet with qualifying evidence
        {
            "id": "loc-verified",
            "name": "Verified Outlet",
            "active": True,
            "verificationStatus": "STUDENT_SOURCED",
        },
        # 2. Explicitly unverified active outlet (UNVERIFIED)
        {
            "id": "loc-explicit-unverified",
            "name": "Unverified Outlet",
            "active": True,
            "verificationStatus": "UNVERIFIED",
        },
        # 3. Missing verification status (None)
        {
            "id": "loc-missing-status",
            "name": "Missing Status Outlet",
            "active": True,
            "verificationStatus": None,
        },
        # 4. Unknown verification status
        {
            "id": "loc-unknown-status",
            "name": "Unknown Status Outlet",
            "active": True,
            "verificationStatus": "RANDOM_EXTERNAL_STATUS",
        },
        # 5. Inactive outlet (active: False)
        {
            "id": "loc-inactive",
            "name": "Inactive Outlet",
            "active": False,
            "verificationStatus": "STUDENT_SOURCED",
        },
    ]

    from backend.shared.database import QueueSenseDatabase
    monkeypatch.setattr(QueueSenseDatabase, "list_locations", lambda self: mock_locations)
    monkeypatch.setattr(
        QueueSenseDatabase,
        "get_current_estimate",
        lambda self, loc_id: qualifying_estimate_verified if loc_id == "loc-verified" else qualifying_estimate_unverified,
    )

    res = rec_handler({}, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    rec_data = body["data"]

    # 6. Verified outlet MUST win over unverified outlet with lower wait
    assert rec_data["state"] == "recommended"
    assert rec_data["recommendedLocationId"] == "loc-verified"
    assert rec_data["recommendedLocationName"] == "Verified Outlet"
    assert rec_data["predictedWaitMinutes"] == 15.0
    assert rec_data["eligibleCount"] == 1


def test_get_recommendations_handler_disqualifies_all_unverified(monkeypatch):
    """When all campus outlets are unverified or missing status, recommendation fails-closed."""
    qualifying_estimate = {
        "predictedWaitMinutes": 5.0,
        "predictedQueueLength": 10,
        "congestion": "MODERATE",
        "confidence": 0.80,
        "confidenceLabel": "HIGH",
        "freshness": "LIVE",
        "recentReportCount": 3,
        "distinctDevicesCount": 3,
        "newestReportAgeMinutes": 2.0,
    }

    mock_locations = [
        {"id": "loc-u1", "name": "Unverified 1", "active": True, "verificationStatus": "UNVERIFIED"},
        {"id": "loc-u2", "name": "Unverified 2", "active": True, "verificationStatus": None},
        {"id": "loc-u3", "name": "Unverified 3", "active": True, "verificationStatus": "UNKNOWN_CLAIM"},
    ]

    from backend.shared.database import QueueSenseDatabase
    monkeypatch.setattr(QueueSenseDatabase, "list_locations", lambda self: mock_locations)
    monkeypatch.setattr(QueueSenseDatabase, "get_current_estimate", lambda self, loc_id: qualifying_estimate)

    res = rec_handler({}, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    rec_data = body["data"]

    # Must fail-closed: no outlet recommended
    assert rec_data["isEligible"] is False
    assert rec_data["recommendedLocationId"] is None
    assert rec_data["eligibleCount"] == 0


