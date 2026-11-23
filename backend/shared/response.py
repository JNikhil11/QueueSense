"""
QueueSense - Standard HTTP Response Helper for AWS Lambda HTTP APIs.
Ensures uniform JSON envelope, status codes, CORS headers, and error formatting.
Never exposes internal stack traces, database keys, or AWS exceptions to clients.
"""

from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional


def create_api_response(
    status_code: int,
    data: Any = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
    request_id: Optional[str] = None,
    cors: bool = True,
    allowed_origin: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Format Lambda proxy response with consistent JSON body, security headers, and CORS.
    Returns:
      {
        "success": bool,
        "data": Any,
        "error": { "code": str, "message": str } (if error present),
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

    if request_id:
        body["requestId"] = request_id

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Cache-Control": "no-store, max-age=0",
    }

    if cors:
        origin = allowed_origin or os.environ.get("ALLOWED_ORIGIN", "*")
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-Api-Key,X-Idempotency-Key"
        headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        headers["Access-Control-Max-Age"] = "600"

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body),
    }

