"""
QueueSense - Standard HTTP Response Helper for AWS Lambda HTTP APIs.
Ensures uniform JSON envelope, status codes, CORS headers, and error formatting.
Never exposes internal stack traces, database keys, or AWS exceptions to clients.
In production, CORS requires explicit deployed frontend origin and never defaults to '*' or localhost.
"""

from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional


def resolve_cors_origin(event: Any = None, allowed_origin: Optional[str] = None) -> Optional[str]:
    """
    Resolves the strict CORS origin.
    In production: Requires explicitly configured origin. Fails closed (returns None)
    instead of defaulting to wildcard or localhost.
    In non-production: Allows configured origin or local development server.
    """
    if isinstance(event, str):
        allowed_origin = event
        event = None

    env = os.environ.get("ENVIRONMENT", "").lower()
    data_mode = os.environ.get("DATA_MODE", "").lower()
    is_production = env in ("prod", "production") or data_mode == "production" or bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    configured = os.environ.get("ALLOWED_ORIGIN") or os.environ.get("ALLOWED_ORIGINS") or os.environ.get("FRONTEND_ORIGIN")
    allowed_list = [o.strip() for o in configured.split(",") if o.strip() and o.strip() != "*"] if configured else []

    if allowed_origin and allowed_origin != "*":
        if not is_production or not allowed_list or allowed_origin in allowed_list:
            return allowed_origin

    if event and isinstance(event, dict):
        headers = event.get("headers") or {}
        req_origin = headers.get("origin") or headers.get("Origin")
        if req_origin:
            if not is_production:
                return req_origin
            if req_origin in allowed_list:
                return req_origin

    if allowed_list:
        return allowed_list[0]

    if is_production:
        # Strict fail-closed: No wildcard or localhost allowed in production
        return None

    # Local development & unit tests only
    return "http://localhost:5173"


def create_api_response(
    status_code: int,
    data: Any = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
    request_id: Optional[str] = None,
    cors: bool = True,
    allowed_origin: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Format Lambda proxy response with consistent JSON body, security headers, and CORS.
    Returns:
      {
        "success": bool,
        "data": Any,
        "error": str (if error present),
        "errorCode": str (if error present),
        "requestId": str (if provided)
      }
    """
    is_success = 200 <= status_code < 300
    body: Dict[str, Any] = {
        "success": is_success,
    }

    if error:
        code = error_code or ("BAD_REQUEST" if status_code < 500 else "INTERNAL_ERROR")
        body["error"] = error
        body["errorCode"] = code

    if data is not None:
        body["data"] = data

    for k, v in kwargs.items():
        body[k] = v

    if request_id:
        body["requestId"] = request_id

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Cache-Control": "no-store, max-age=0",
    }

    if cors:
        origin = resolve_cors_origin(allowed_origin)
        if origin:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-Api-Key,X-Idempotency-Key"
            headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
            headers["Access-Control-Max-Age"] = "600"

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body),
    }
