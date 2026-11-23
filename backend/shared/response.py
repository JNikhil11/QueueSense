"""
QueueSense - Standard HTTP Response Helper for AWS Lambda HTTP APIs.
Ensures uniform JSON envelope, status codes, CORS headers, and error formatting.
"""

from __future__ import annotations
import json
from typing import Any, Dict, Optional


def create_api_response(
    status_code: int,
    data: Any,
    error: Optional[str] = None,
    cors: bool = True,
) -> Dict[str, Any]:
    """Format Lambda proxy response with consistent JSON body and CORS headers."""
    body: Dict[str, Any] = {
        "success": 200 <= status_code < 300,
    }

    if error:
        body["error"] = error
    if data is not None:
        body["data"] = data

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Cache-Control": "no-store, max-age=0",
    }

    if cors:
        headers["Access-Control-Allow-Origin"] = "*"
        headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-Api-Key"
        headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS,PATCH"

    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body),
    }

