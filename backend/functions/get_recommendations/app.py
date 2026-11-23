"""
QueueSense - GET /recommendations Lambda Handler
Evaluates all campus outlets, filters out stale or unverified data,
and returns the best-recommended food outlet with transparent reasoning.
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
from prediction import calculate_queue_estimate, compute_smart_recommendation


def lambda_handler(event, context):
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
        )
    except Exception as e:
        return create_api_response(
            status_code=500,
            data=None,
            error=f"Error computing recommendations: {str(e)}",
        )
