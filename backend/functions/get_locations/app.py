"""
QueueSense - GET /locations Lambda Handler
Returns all active campus locations with their real-time queue estimate snapshot.
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
from prediction import calculate_queue_estimate


def lambda_handler(event, context):
    try:
        db = QueueSenseDatabase()
        locations = db.list_locations()

        results = []
        for loc in locations:
            loc_id = loc.get("id")
            # First check if we have a cached estimate
            est = db.get_current_estimate(loc_id)
            if not est:
                # Calculate from recent reports
                reports = db.get_recent_reports(loc_id, limit=20)
                est = calculate_queue_estimate(reports)
                db.save_current_estimate(loc_id, est)

            # Strip DynamoDB single-table keys from client view
            clean_loc = {k: v for k, v in loc.items() if k not in ("PK", "SK", "entityType")}
            clean_est = {k: v for k, v in est.items() if k not in ("PK", "SK", "entityType")}
            clean_loc["estimate"] = clean_est
            results.append(clean_loc)

        return create_api_response(status_code=200, data=results)
    except Exception as e:
        return create_api_response(
            status_code=500,
            data=None,
            error=f"Failed to retrieve campus locations: {str(e)}",
        )
