"""
QueueSense - POST /locations/{id}/reports Lambda Handler
Validates user submission, applies server timestamp & ID, updates DynamoDB,
recomputes real-time queue estimate, and returns updated prediction.
"""

import json
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
shared_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "shared"))
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)
if "/opt/python" not in sys.path:
    sys.path.insert(0, "/opt/python")

from response import create_api_response
from database import QueueSenseDatabase
from validation import validate_location_id, validate_report_payload
from prediction import calculate_queue_estimate


def lambda_handler(event, context):
    try:
        # Extract location ID
        path_params = event.get("pathParameters") or {}
        location_id = path_params.get("id")

        if not location_id or not validate_location_id(location_id):
            return create_api_response(
                status_code=400,
                data=None,
                error="Invalid or missing location identifier.",
            )

        # Parse request body
        raw_body = event.get("body")
        if not raw_body:
            return create_api_response(
                status_code=400,
                data=None,
                error="Missing request body.",
            )

        if isinstance(raw_body, str):
            try:
                body = json.loads(raw_body)
            except json.JSONDecodeError:
                return create_api_response(
                    status_code=400,
                    data=None,
                    error="Malformed JSON payload.",
                )
        else:
            body = raw_body

        # Validate input bounds and sanitize
        is_valid, sanitized_data, errors = validate_report_payload(body)
        if not is_valid:
            return create_api_response(
                status_code=422,
                data={"validationErrors": errors},
                error="; ".join(errors),
            )

        db = QueueSenseDatabase()
        location = db.get_location(location_id)
        if not location:
            return create_api_response(
                status_code=404,
                data=None,
                error=f"Location '{location_id}' does not exist.",
            )

        # Record new report with server-generated timestamp & ID
        new_report = db.record_report(
            location_id=location_id,
            reported_wait_minutes=sanitized_data["reportedWaitMinutes"],
            queue_length=sanitized_data["queueLength"],
            note=sanitized_data.get("note"),
        )

        # Immediately recalculate updated queue estimate
        recent_reports = db.get_recent_reports(location_id, limit=30)
        updated_estimate = calculate_queue_estimate(recent_reports)
        db.save_current_estimate(location_id, updated_estimate)

        clean_report = {
            "reportId": new_report["reportId"],
            "locationId": location_id,
            "reportedWaitMinutes": new_report["reportedWaitMinutes"],
            "queueLength": new_report["queueLength"],
            "note": new_report.get("note"),
            "timestamp": new_report["timestamp"],
        }

        return create_api_response(
            status_code=201,
            data={
                "message": "Queue observation successfully recorded.",
                "report": clean_report,
                "updatedEstimate": updated_estimate,
            },
        )
    except Exception as e:
        return create_api_response(
            status_code=500,
            data=None,
            error=f"Internal error processing queue report: {str(e)}",
        )
