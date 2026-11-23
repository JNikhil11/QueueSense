"""
QueueSense - GET /admin/reports Lambda Handler
Provides operational audit feed of recent reports across campus food outlets.
Includes outlier flags and volume metrics.
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
from prediction import filter_outliers


def lambda_handler(event, context):
    try:
        query_params = event.get("queryStringParameters") or {}
        limit_param = query_params.get("limit", "50")
        try:
            limit = min(int(limit_param), 100)
        except ValueError:
            limit = 50

        db = QueueSenseDatabase()
        reports = db.list_all_reports(limit=limit)

        # Flag outliers for admin visibility
        valid_reports, outliers = filter_outliers(reports)
        outlier_ids = {o.get("reportId") for o in outliers if o.get("reportId")}

        audit_feed = []
        for r in reports:
            audit_feed.append(
                {
                    "reportId": r.get("reportId"),
                    "locationId": r.get("locationId"),
                    "reportedWaitMinutes": float(r.get("reportedWaitMinutes", 0)),
                    "queueLength": int(r.get("queueLength", 0)),
                    "note": r.get("note"),
                    "timestamp": r.get("timestamp"),
                    "isOutlier": r.get("reportId") in outlier_ids,
                }
            )

        return create_api_response(
            status_code=200,
            data={
                "totalReportsReturned": len(audit_feed),
                "outlierCount": len(outlier_ids),
                "reports": audit_feed,
            },
        )
    except Exception as e:
        return create_api_response(
            status_code=500,
            data=None,
            error=f"Error accessing admin audit feed: {str(e)}",
        )

