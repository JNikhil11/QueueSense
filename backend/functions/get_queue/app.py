"""
QueueSense - GET /locations/{id}/queue Lambda Handler
Returns current queue prediction and recent observation history for a specific outlet.
"""

import logging
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
shared_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "shared"))
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)
if "/opt/python" not in sys.path:
    sys.path.insert(0, "/opt/python")

from response import create_api_response
from database import QueueSenseDatabase, DatabasePersistenceError
from validation import validate_location_id
from prediction import calculate_queue_estimate

logger = logging.getLogger("queuesense.get_queue")
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None) or "local_req"

    try:
        path_params = event.get("pathParameters") or {}
        location_id = path_params.get("id")

        if not location_id or not validate_location_id(location_id):
            return create_api_response(
                status_code=400,
                error="Invalid or missing campus outlet identifier.",
                error_code="INVALID_LOCATION_ID",
                request_id=request_id,
            )

        db = QueueSenseDatabase()
        location = db.get_location(location_id)
        if not location:
            return create_api_response(
                status_code=404,
                error=f"Campus outlet with id '{location_id}' was not found.",
                error_code="LOCATION_NOT_FOUND",
                request_id=request_id,
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
                "locationId": location_id,
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
            request_id=request_id,
        )
    except DatabasePersistenceError as e:
        logger.error("Database failure in get_queue [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="Failed to retrieve queue details from database.",
            error_code="PERSISTENCE_FAILED",
            request_id=request_id,
        )
    except Exception as e:
        logger.error("Error fetching queue data [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="An internal error occurred while fetching queue details.",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
        )
