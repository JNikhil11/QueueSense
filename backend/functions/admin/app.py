"""
QueueSense - GET /admin/reports Lambda Handler
Provides operational audit feed of recent reports across campus food outlets.
Requires authenticated Cognito Administrator access (cognito:groups includes 'Admins').
In production, static admin keys are strictly prohibited; unauthenticated access is rejected.
"""

import logging
import os
import sys
from typing import Dict, Any, Tuple, Optional

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


def check_admin_authorization(event: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates that the incoming request is authorized by a verified Administrator.
    Returns: (is_authorized, user_identity, error_code)
    """
    # 1. API Gateway HTTP API Cognito Authorizer JWT claims inspection
    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}
    jwt = authorizer.get("jwt") or {}
    claims = jwt.get("claims") or {}

    if claims:
        # Check if user is in 'Admins' group
        groups = claims.get("cognito:groups") or []
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",") if g.strip()]
        if "Admins" in groups:
            return True, claims.get("username") or claims.get("sub"), None
        logger.warning("Authenticated user is not in 'Admins' group: sub=%s", claims.get("sub"))
        return False, None, "FORBIDDEN_NOT_ADMIN"

    # 2. Check environment & data mode
    env = os.environ.get("ENVIRONMENT", "").lower()
    data_mode = os.environ.get("DATA_MODE", "").lower()
    is_production = env in ("prod", "production") or data_mode == "production" or bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    if is_production:
        # Strict Production Gate: Fail closed. Static admin keys are completely disabled in production.
        logger.warning("Unauthenticated request to production /admin/reports without Cognito JWT.")
        return False, None, "UNAUTHORIZED_COGNITO_REQUIRED"

    # 3. Non-production / Test environments ONLY
    # Allows injected test authorization or explicit non-production test key
    test_key = os.environ.get("ADMIN_DEV_KEY") or os.environ.get("ADMIN_API_KEY")
    if test_key and test_key.strip():
        headers = event.get("headers") or {}
        auth_header = headers.get("authorization") or headers.get("Authorization") or ""
        admin_key_header = headers.get("x-admin-key") or headers.get("X-Admin-Key") or ""

        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == test_key.strip():
                return True, "dev-admin-user", None

        if admin_key_header and admin_key_header.strip() == test_key.strip():
            return True, "dev-admin-user", None

    return False, None, "UNAUTHORIZED"


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None) or "local_req"

    try:
        # Enforce Admin Authorization
        is_authorized, user_identity, auth_error = check_admin_authorization(event)
        if not is_authorized:
            status_code = 403 if auth_error == "FORBIDDEN_NOT_ADMIN" else 401
            error_message = (
                "Forbidden: Administrator privileges required in Cognito User Pool."
                if auth_error == "FORBIDDEN_NOT_ADMIN"
                else "Unauthorized: Valid Cognito Administrator JWT credentials required."
            )
            return create_api_response(
                status_code=status_code,
                error=error_message,
                error_code=auth_error or "UNAUTHORIZED",
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

        # Flag statistical outliers for administrator review
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
                "operatorIdentity": user_identity,
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
