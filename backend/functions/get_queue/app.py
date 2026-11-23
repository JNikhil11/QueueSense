"""
QueueSense - GET /locations/{id}/queue Lambda Handler
Returns current queue prediction and recent observation history for a specific outlet.
"""

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
from validation import validate_location_id
from prediction import calculate_queue_estimate


def lambda_handler(event, context):
    try:
        # Extract location ID from path parameters
        path_params = event.get("pathParameters") or {}
        location_id = path_params.get("id")

        if not location_id or not validate_location_id(location_id):
            return create_api_response(
                status_code=400,
                data=None,
                error="Invalid or missing location identifier.",
            )

        db = QueueSenseDatabase()
        location = db.get_location(location_id)
        if not location:
            return create_api_response(
                status_code=404,
                data=None,
                error=f"Campus outlet with id '{location_id}' was not found.",
            )

        # Retrieve recent reports
        reports = db.get_recent_reports(location_id, limit=30)
        estimate = calculate_queue_estimate(reports)
        # Update current estimate record
        db.save_current_estimate(location_id, estimate)

        # Clean reports for client output (strip internal PK/SK)
        clean_reports = [
            {
                "reportId": r.get("reportId"),
                "reportedWaitMinutes": float(r.get("reportedWaitMinutes", 0)),
                "queueLength": int(r.get("queueLength", 0)),
                "note": r.get("note"),
                "timestamp": r.get("timestamp"),
            }
            for r in reports
        ]

        clean_location = {
            k: v for k, v in location.items() if k not in ("PK", "SK", "entityType")
        }

        return create_api_response(
            status_code=200,
            data={
                "location": clean_location,
                "estimate": estimate,
                "reports": clean_reports,
            },
        )
    except Exception as e:
        return create_api_response(
            status_code=500,
            data=None,
            error=f"Error fetching queue data: {str(e)}",
        )

