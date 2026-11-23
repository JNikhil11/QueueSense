"""
QueueSense - POST /locations/{id}/reports Lambda Handler
Validates user submission, applies server timestamp & ID, enforces rate limiting,
deduplicates retries via idempotency key, durably persists to DynamoDB,
recomputes real-time queue estimate, and returns updated prediction.
Never converts persistence failures into silent success.
Fails closed when required security configurations are missing or compromised.
"""

import json
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
from database import (
    QueueSenseDatabase,
    DatabasePersistenceError,
    IdempotencyConflictError,
)
from validation import validate_location_id, validate_report_payload
from prediction import calculate_queue_estimate
from security import (
    compute_anonymous_client_hash,
    extract_idempotency_key,
    SecurityConfigurationError,
)

logger = logging.getLogger("queuesense.submit_report")
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None) or "local_req"

    try:
        # 1. Extract and validate location ID
        path_params = event.get("pathParameters") or {}
        location_id = path_params.get("id")

        if not location_id or not validate_location_id(location_id):
            return create_api_response(
                status_code=400,
                error="Invalid or missing campus outlet identifier.",
                error_code="INVALID_LOCATION_ID",
                request_id=request_id,
            )

        # 2. Parse request body
        raw_body = event.get("body")
        if not raw_body:
            return create_api_response(
                status_code=400,
                error="Missing request body payload.",
                error_code="EMPTY_PAYLOAD",
                request_id=request_id,
            )

        if isinstance(raw_body, str):
            try:
                body = json.loads(raw_body)
            except json.JSONDecodeError:
                return create_api_response(
                    status_code=400,
                    error="Malformed JSON payload in request.",
                    error_code="MALFORMED_JSON",
                    request_id=request_id,
                )
        else:
            body = raw_body

        # 3. Validate input bounds and sanitize text
        is_valid, sanitized_data, errors = validate_report_payload(body)
        if not is_valid:
            return create_api_response(
                status_code=422,
                data={"validationErrors": errors},
                error="; ".join(errors),
                error_code="VALIDATION_FAILED",
                request_id=request_id,
            )

        db = QueueSenseDatabase()

        # 4. Enforce Privacy-Preserving Rate Limiting (5 reports per 5 minutes per client hash)
        try:
            client_hash = compute_anonymous_client_hash(event)
            is_allowed = db.check_rate_limit(client_hash=client_hash, window_seconds=300, max_requests=5)
        except SecurityConfigurationError:
            raise
        except DatabasePersistenceError as db_err:
            logger.error("Rate limit check storage failure [req=%s]: %s", request_id, str(db_err), exc_info=True)
            return create_api_response(
                status_code=503,
                error="Rate limit verification service unavailable. Please retry shortly.",
                error_code="RATE_LIMIT_CHECK_FAILED",
                request_id=request_id,
            )

        if not is_allowed:
            logger.warning("Rate limit exceeded for client hash: %s on location %s", client_hash, location_id)
            return create_api_response(
                status_code=429,
                error="Submission rate limit reached. Please wait a few minutes before submitting another report.",
                error_code="RATE_LIMIT_EXCEEDED",
                request_id=request_id,
            )

        # 5. Verify outlet existence
        location = db.get_location(location_id)
        if not location:
            return create_api_response(
                status_code=404,
                error=f"Campus outlet '{location_id}' was not found in directory.",
                error_code="LOCATION_NOT_FOUND",
                request_id=request_id,
            )

        # 6. Extract Idempotency Key (prevents duplicate submissions on network retries)
        idempotency_key = extract_idempotency_key(event, body)

        # 7. Record new report durably (fails closed if DynamoDB write fails)
        new_report = db.record_report(
            location_id=location_id,
            reported_wait_minutes=sanitized_data["reportedWaitMinutes"],
            queue_length=sanitized_data["queueLength"],
            note=sanitized_data.get("note"),
            idempotency_key=idempotency_key,
        )

        # 8. Recalculate queue estimate from recent reports
        recent_reports = db.get_recent_reports(location_id, limit=30)
        updated_estimate = calculate_queue_estimate(recent_reports)
        db.save_current_estimate(location_id, updated_estimate)

        clean_report = {
            "reportId": new_report["reportId"],
            "locationId": location_id,
            "reportedWaitMinutes": float(new_report["reportedWaitMinutes"]),
            "queueLength": int(new_report["queueLength"]),
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
            request_id=request_id,
        )

    except SecurityConfigurationError as e:
        logger.error("Security configuration failure [req=%s]: %s", request_id, str(e))
        return create_api_response(
            status_code=500,
            error="Server security configuration error. Service unavailable.",
            error_code="SECURITY_CONFIGURATION_ERROR",
            request_id=request_id,
        )
    except IdempotencyConflictError as e:
        logger.warning("Idempotency conflict [req=%s]: %s", request_id, str(e))
        return create_api_response(
            status_code=409,
            error=str(e),
            error_code="IDEMPOTENCY_CONFLICT",
            request_id=request_id,
        )
    except DatabasePersistenceError as e:
        logger.error("Database persistence failure [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="Failed to record observation to durable storage. Please retry.",
            error_code="PERSISTENCE_FAILED",
            request_id=request_id,
        )
    except Exception as e:
        logger.error("Unexpected handler error [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="An internal error occurred while processing your queue report.",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
        )
