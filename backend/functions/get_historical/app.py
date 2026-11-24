"""
QueueSense - GET /locations/{id}/historical Lambda Handler
Returns aggregated historical wait time and queue patterns by hour-of-day.
Enforces 14-day cutoff, converts timestamps to campus timezone (Asia/Kolkata),
requires minimum 3 samples before declaring peak/quietest hours, and clearly
distinguishes empirical historical averages from deterministic forecasts.
"""

import os
import sys
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

current_dir = os.path.dirname(os.path.abspath(__file__))
shared_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "shared"))
if shared_dir not in sys.path:
    sys.path.insert(0, shared_dir)
if "/opt/python" not in sys.path:
    sys.path.insert(0, "/opt/python")

from response import create_api_response
from database import QueueSenseDatabase, DatabasePersistenceError
from validation import validate_location_id, validate_pagination_limit, validate_historical_days

logger = logging.getLogger("queuesense.get_historical")
logger.setLevel(logging.INFO)

# Campus Timezone: Asia/Kolkata (Indian Standard Time, UTC+05:30)
try:
    from zoneinfo import ZoneInfo
    CAMPUS_TIMEZONE = ZoneInfo("Asia/Kolkata")
except Exception:
    CAMPUS_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")

MIN_SAMPLES_PER_HOUR = 3  # Minimum observations required to declare a representative busiest/quietest hour


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

        # Validate numeric bounds on query parameters (days: 1-14, limit: 1-1000)
        query_params = (event or {}).get("queryStringParameters") or {}
        days_param = query_params.get("days")
        is_valid_days, days, days_err = validate_historical_days(
            days_param, default=14, min_val=1, max_val=14
        )
        if not is_valid_days:
            return create_api_response(
                status_code=400,
                error=days_err,
                error_code="INVALID_DAYS",
                request_id=request_id,
            )

        limit_param = query_params.get("limit")
        is_valid_limit, limit, limit_err = validate_pagination_limit(
            limit_param, default=1000, min_val=1, max_val=1000
        )
        if not is_valid_limit:
            return create_api_response(
                status_code=400,
                error=limit_err,
                error_code="INVALID_LIMIT",
                request_id=request_id,
            )

        # Retrieve historical reports (strictly enforced 14 days cutoff in DB query, bounded to 1000 reports across pages)
        hist_result = db.get_historical_reports(location_id, days=days, limit=limit, include_metadata=True)
        reports = hist_result["reports"]
        is_capped = hist_result["is_truncated"]

        # Aggregate by hour (0-23) in campus timezone (Asia/Kolkata, UTC+05:30)
        hourly_buckets = defaultdict(lambda: {"wait_sum": 0.0, "queue_sum": 0.0, "count": 0})

        for r in reports:
            ts_str = r.get("timestamp")
            if not ts_str:
                continue
            try:
                clean_ts = ts_str.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_campus = dt.astimezone(CAMPUS_TIMEZONE)
                hour = dt_campus.hour
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
        busiest_count = 0
        quietest_hour = None
        lowest_avg_wait = 9999.0
        quietest_count = 0

        for h in range(24):
            b = hourly_buckets[h]
            count = b["count"]
            if count > 0:
                avg_wait = round(b["wait_sum"] / count, 1)
                avg_queue = round(b["queue_sum"] / count, 1)

                # Consider operating hours (8:00 to 22:00) with ADEQUATE SAMPLES (>= 3)
                # for busiest / quietest insights
                if 8 <= h <= 22 and count >= MIN_SAMPLES_PER_HOUR:
                    if avg_wait > highest_avg_wait:
                        highest_avg_wait = avg_wait
                        busiest_hour = h
                        busiest_count = count
                    if avg_wait < lowest_avg_wait:
                        lowest_avg_wait = avg_wait
                        quietest_hour = h
                        quietest_count = count
            else:
                avg_wait = None
                avg_queue = None

            hourly_trends.append({
                "hour": h,
                "label": f"{h:02d}:00",
                "historicalAverageWaitMinutes": avg_wait,
                "historicalAverageQueueLength": avg_queue,
                "sampleCount": count,
                "averageWaitMinutes": avg_wait,
                "averageQueueLength": avg_queue,
                "observationCount": count,
            })

        total_observations = len(reports)
        has_sufficient_history = total_observations >= 5

        status = "available" if has_sufficient_history else "insufficient_history"
        coverage_status = "CAPPED_AT_1000_OBSERVATIONS" if is_capped else "COMPLETE_14_DAY"

        if has_sufficient_history:
            if is_capped:
                summary = (
                    f"Historical average curve aggregated from {total_observations} student observations "
                    f"over the past 14 days (sample bounded at 1,000 most recent observations for low-latency analysis; "
                    f"older observations beyond cap excluded; Campus Timezone: Asia/Kolkata)."
                )
            else:
                summary = (
                    f"Historical average curve aggregated from all {total_observations} student-submitted observations "
                    f"over the past 14 days (Campus Timezone: Asia/Kolkata)."
                )
        else:
            summary = (
                f"Only {total_observations} historical report(s) available. "
                f"Hourly curves calibrate after 5+ observations accumulate."
            )

        return create_api_response(
            status_code=200,
            data={
                "locationId": location_id,
                "locationName": location.get("name"),
                "status": status,
                "timezone": "Asia/Kolkata",
                "metricType": "HISTORICAL_AVERAGES",
                "minSamplesRequiredForPeak": MIN_SAMPLES_PER_HOUR,
                "totalObservations": total_observations,
                "isCapped": is_capped,
                "maxObservationCap": 1000,
                "coverageStatus": coverage_status,
                "disclaimer": "Historical averages reflect empirical crowdsourced observations in Indian Standard Time (IST, UTC+05:30) and should not be treated as deterministic real-time forecasts.",
                "hourlyTrends": hourly_trends,
                "busiestHour": {
                    "hour": busiest_hour,
                    "label": f"{busiest_hour:02d}:00",
                    "historicalAverageWaitMinutes": highest_avg_wait,
                    "averageWaitMinutes": highest_avg_wait,
                    "sampleCount": busiest_count,
                } if busiest_hour is not None else None,
                "quietestHour": {
                    "hour": quietest_hour,
                    "label": f"{quietest_hour:02d}:00",
                    "historicalAverageWaitMinutes": lowest_avg_wait,
                    "averageWaitMinutes": lowest_avg_wait,
                    "sampleCount": quietest_count,
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
