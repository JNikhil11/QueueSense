"""
QueueSense - GET /health Lambda Handler
Returns API status, version, and server timestamp.
"""

import os
import sys
from datetime import datetime, timezone

current_dir = os.path.dirname(os.path.abspath(__file__))
shared_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "shared"))
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)
if "/opt/python" not in sys.path:
    sys.path.insert(0, "/opt/python")

from response import create_api_response


def lambda_handler(event, context):
    return create_api_response(
        status_code=200,
        data={
            "status": "healthy",
            "service": "QueueSense-API",
            "region": os.environ.get("AWS_REGION", "ap-southeast-2"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
        },
    )
