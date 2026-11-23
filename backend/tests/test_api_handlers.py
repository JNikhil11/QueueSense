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
    # Submit report
    event = {
        "pathParameters": {"id": "mess-a-central"},
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
        "pathParameters": {"id": "mess-a-central"},
    }
    res_q = queue_handler(q_event, None)
    assert res_q["statusCode"] == 200
    body_q = json.loads(res_q["body"])
    assert body_q["success"] is True
    assert body_q["data"]["location"]["id"] == "mess-a-central"
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


def test_admin_reports_handler():
    event = {"queryStringParameters": {"limit": "10"}}
    res = admin_handler(event, None)
    assert res["statusCode"] == 200
    body = json.loads(res["body"])
    assert body["success"] is True
    assert "reports" in body["data"]
