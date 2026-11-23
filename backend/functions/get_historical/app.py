"""
QueueSense - GET /locations/{id}/historical Lambda Handler
Returns aggregated historical wait time and queue patterns by day-of-week and hour-of-day.
"""

import os
import sys
import logging
from collections import defaultdict
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
shared_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "shared"))
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)
if "/opt/python" not in sys.path:
    sys.path.insert(0, "/opt/python")

from response import create_api_response
from database import QueueSenseDatabase, DatabasePersistenceError
from validation import validate_location_id

logger = logging.getLogger("queuesense.get_historical")
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", None) or "local_req"

    try:
        path_params = event.get("pathParameters") or {}
        location_id = path_params.get("id")

        if not location_id or not validate_location_id(location_id):
            return create_api_response(
                status_code=400,
                error="Invalid or missing campus outlet identifier.",
                error_code="INVALID_LOCATION_ID",
                request_id=request_id,
            )

        db = QueueSenseDatabase()
        location = db.get_location(location_id)
        if not location:
            return create_api_response(
                status_code=404,
                error=f"Campus outlet '{location_id}' was not found in directory.",
                error_code="LOCATION_NOT_FOUND",
                request_id=request_id,
            )

        # Retrieve historical reports (up to 14 days)
        reports = db.get_historical_reports(location_id, days=14)

        # Aggregate by hour (0-23)
        hourly_buckets = defaultdict(lambda: {"wait_sum": 0.0, "queue_sum": 0.0, "count": 0})

        for r in reports:
            ts_str = r.get("timestamp")
            if not ts_str:
                continue
            try:
                clean_ts = ts_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_ts)
                hour = dt.hour
                wait = float(r.get("reportedWaitMinutes", 0))
                q_len = float(r.get("queueLength", 0))

                hourly_buckets[hour]["wait_sum"] += wait
                hourly_buckets[hour]["queue_sum"] += q_len
                hourly_buckets[hour]["count"] += 1
            except Exception:
                continue

        # Build full 24-hour distribution
        hourly_trends = []
        busiest_hour = None
        highest_avg_wait = -1.0
        quietest_hour = None
        lowest_avg_wait = 9999.0

        for h in range(24):
            b = hourly_buckets[h]
            if b["count"] > 0:
                avg_wait = round(b["wait_sum"] / b["count"], 1)
                avg_queue = round(b["queue_sum"] / b["count"], 1)
                count = b["count"]

                # Consider operating hours (8:00 to 22:00) for busiest / quietest insights
                if 8 <= h <= 22:
                    if avg_wait > highest_avg_wait:
                        highest_avg_wait = avg_wait
                        busiest_hour = h
                    if avg_wait < lowest_avg_wait:
                        lowest_avg_wait = avg_wait
                        quietest_hour = h
            else:
                avg_wait = None
                avg_queue = None
                count = 0

            hourly_trends.append({
                "hour": h,
                "label": f"{h:02d}:00",
                "averageWaitMinutes": avg_wait,
                "averageQueueLength": avg_queue,
                "observationCount": count,
            })

        total_observations = len(reports)
        has_sufficient_history = total_observations >= 5

        status = "available" if has_sufficient_history else "insufficient_history"
        summary = (
            f"Historical curve synthesized from {total_observations} verified student reports over the past 14 days."
            if has_sufficient_history
            else f"Only {total_observations} historical report(s) available. Hourly curves calibrate after 5+ observations accumulate."
        )

        return create_api_response(
            status_code=200,
            data={
                "locationId": location_id,
                "locationName": location.get("name"),
                "status": status,
                "totalObservations": total_observations,
                "hourlyTrends": hourly_trends,
                "busiestHour": {
                    "hour": busiest_hour,
                    "label": f"{busiest_hour:02d}:00" if busiest_hour is not None else None,
                    "averageWaitMinutes": highest_avg_wait if highest_avg_wait >= 0 else None,
                } if busiest_hour is not None else None,
                "quietestHour": {
                    "hour": quietest_hour,
                    "label": f"{quietest_hour:02d}:00" if quietest_hour is not None else None,
                    "averageWaitMinutes": lowest_avg_wait if lowest_avg_wait < 9999 else None,
                } if quietest_hour is not None else None,
                "summary": summary,
            },
            request_id=request_id,
        )
    except DatabasePersistenceError as e:
        logger.error("Database persistence failure [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="Failed to query historical queue metrics from database.",
            error_code="PERSISTENCE_FAILED",
            request_id=request_id,
        )
    except Exception as e:
        logger.error("Unexpected error in get_historical [req=%s]: %s", request_id, str(e), exc_info=True)
        return create_api_response(
            status_code=500,
            error="An internal error occurred while fetching historical data.",
            error_code="INTERNAL_ERROR",
            request_id=request_id,
        )
