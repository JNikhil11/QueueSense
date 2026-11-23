"""
QueueSense - GET /recommendations Lambda Handler
Evaluates all campus outlets, filters out stale or unverified data,
enforces cold-start protection (min 3 fresh reports, min 50% confidence),
and returns the best-recommended food outlet with transparent reasoning.
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
from prediction import calculate_queue_estimate, compute_smart_recommendation

logger = logging.getLogger("queuesense.get_recommendations")
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None) or "local_req"

    try:
        db = QueueSenseDatabase()
        locations = db.list_locations()

        locations_with_estimates = []
        for loc in locations:
            loc_id = loc.get("id")
            est = db.get_current_estimate(loc_id)
            if not est:
                reports = db.get_recent_reports(loc_id, limit=20)
                est = calculate_queue_estimate(reports)
                db.save_current_estimate(loc_id, est)

            locations_with_estimates.append(
                {
                    "id": loc.get("id"),
                    "name": loc.get("name"),
                    "category": loc.get("category"),
                    "active": loc.get("active", True),
                    "estimate": est,
                }
            )

        recommendation = compute_smart_recommendation(locations_with_estimates)

        return create_api_response(
            status_code=200,
            data=recommendation,
            request_id=request_id,
        )
    except DatabasePersistenceError as e:
        logger.error("Database failure in get_recommendations [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="Failed to compute recommendations due to database error.",
            error_code="PERSISTENCE_FAILED",
            request_id=request_id,
        )
    except Exception as e:
        logger.error("Error computing recommendations [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="An internal error occurred while computing recommendations.",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
        )
