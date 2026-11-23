"""
QueueSense - GET /admin/reports Lambda Handler
Provides operational audit feed of recent reports across campus food outlets.
Requires admin credentials (Authorization: Bearer <key> or X-Admin-Key: <key>).
Includes outlier flags and volume metrics.
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
from prediction import filter_outliers

logger = logging.getLogger("queuesense.admin")
logger.setLevel(logging.INFO)


def check_admin_authorization(event) -> bool:
    headers = event.get("headers") or {}
    # Check case-insensitively
    auth_header = ""
    admin_key_header = ""
    for k, v in headers.items():
        k_lower = k.lower()
        if k_lower == "authorization":
            auth_header = str(v)
        elif k_lower == "x-admin-key":
            admin_key_header = str(v)

    expected_key = os.environ.get("ADMIN_API_KEY", "queuesense-admin-secret-dev-key")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token == expected_key:
            return True

    if admin_key_header and admin_key_header.strip() == expected_key:
        return True

    return False


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None) or "local_req"

    try:
        # Enforce Admin Authorization
        if not check_admin_authorization(event):
            logger.warning("Unauthorized access attempt to /admin/reports [req=%s]", request_id)
            return create_api_response(
                status_code=401,
                error="Unauthorized: Valid admin credentials required. Provide 'Authorization: Bearer <token>' or 'X-Admin-Key: <key>'.",
                error_code="UNAUTHORIZED",
                request_id=request_id,
            )

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
            request_id=request_id,
        )
    except DatabasePersistenceError as e:
        logger.error("Database failure in admin audit feed [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="Failed to retrieve operational audit feed from database.",
            error_code="PERSISTENCE_FAILED",
            request_id=request_id,
        )
    except Exception as e:
        logger.error("Error accessing admin audit feed [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="An internal error occurred while fetching admin reports.",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
        )
