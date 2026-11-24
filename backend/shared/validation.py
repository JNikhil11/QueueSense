"""
QueueSense - Request Validation & Input Sanitization
Provides deterministic validation for user reports, query params, and IDs.
Ensures zero HTML injection, strict numeric bounds, rejection of NaN/Infinity,
and clean, standardized error structures.
"""

from __future__ import annotations
import math
import re
from typing import Dict, Any, Tuple, List, Optional

LOCATION_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{2,40}$")
NOTE_DISALLOWED_CHARS = re.compile(r"[<>{}\\\^`~]")

MAX_WAIT_MINUTES = 120.0
MIN_WAIT_MINUTES = 0.0

MAX_QUEUE_LENGTH = 300
MIN_QUEUE_LENGTH = 0

MAX_NOTE_LENGTH = 140


def validate_location_id(loc_id: str) -> bool:
    """Validate that location ID meets safe alphanumeric and hyphen/underscore pattern."""
    if not isinstance(loc_id, str):
        return False
    return bool(LOCATION_ID_REGEX.match(loc_id.strip()))


def sanitize_note(note: Optional[str]) -> Optional[str]:
    """Sanitize optional text notes: strip HTML brackets, control chars, and truncate."""
    if note is None:
        return None
    if not isinstance(note, str):
        return None
    cleaned = NOTE_DISALLOWED_CHARS.sub("", note.strip())
    # Collapse multiple whitespace
    cleaned = " ".join(cleaned.split())
    return cleaned[:MAX_NOTE_LENGTH] if cleaned else None


def validate_report_payload(body: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    Validate incoming report submission payload.
    Expected fields:
      - reportedWaitMinutes: int or float [0.0, 120.0] (rejects NaN, Infinity, -Infinity, Booleans)
      - queueLength: int [0, 300] (whole integer only, rejects fractional people, NaN, Infinity, Booleans)
      - note: optional string [max 140 chars]
    Returns (is_valid, sanitized_data, error_messages).
    """
    errors: List[str] = []
    sanitized: Dict[str, Any] = {}

    if not isinstance(body, dict):
        return False, {}, ["Request body must be a valid JSON object."]

    # 1. Validate reportedWaitMinutes
    if "reportedWaitMinutes" not in body:
        errors.append("Field 'reportedWaitMinutes' is required.")
    else:
        raw_wait = body["reportedWaitMinutes"]
        # Booleans inherit from int in Python, so isinstance(True, int) is True!
        if isinstance(raw_wait, bool) or raw_wait is None:
            errors.append("Field 'reportedWaitMinutes' must be a valid numeric value.")
        elif isinstance(raw_wait, str) and raw_wait.strip().lower() in ("nan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"):
            errors.append("Field 'reportedWaitMinutes' cannot be NaN or Infinity.")
        else:
            try:
                wait_val = float(raw_wait)
                if math.isnan(wait_val) or math.isinf(wait_val):
                    errors.append("Field 'reportedWaitMinutes' cannot be NaN or Infinity.")
                elif wait_val < MIN_WAIT_MINUTES:
                    errors.append("Field 'reportedWaitMinutes' cannot be negative.")
                elif wait_val > MAX_WAIT_MINUTES:
                    errors.append(f"Field 'reportedWaitMinutes' exceeds plausible limit of {int(MAX_WAIT_MINUTES)} minutes.")
                else:
                    sanitized["reportedWaitMinutes"] = round(wait_val, 1)
            except (ValueError, TypeError, OverflowError):
                errors.append("Field 'reportedWaitMinutes' must be a valid numeric value.")

    # 2. Validate queueLength
    if "queueLength" not in body or body["queueLength"] is None:
        # If omitted or null, defaults to 0
        sanitized["queueLength"] = 0
    else:
        raw_queue = body["queueLength"]
        if isinstance(raw_queue, bool):
            errors.append("Field 'queueLength' must be a valid integer.")
        elif isinstance(raw_queue, float):
            if math.isnan(raw_queue) or math.isinf(raw_queue):
                errors.append("Field 'queueLength' cannot be NaN or Infinity.")
            elif not raw_queue.is_integer():
                errors.append("Field 'queueLength' must be a whole integer number of people.")
            elif raw_queue < MIN_QUEUE_LENGTH:
                errors.append("Field 'queueLength' cannot be negative.")
            elif raw_queue > MAX_QUEUE_LENGTH:
                errors.append(f"Field 'queueLength' exceeds plausible limit of {MAX_QUEUE_LENGTH} people.")
            else:
                sanitized["queueLength"] = int(raw_queue)
        elif isinstance(raw_queue, str):
            stripped = raw_queue.strip()
            if not re.match(r"^-?\d+$", stripped):
                errors.append("Field 'queueLength' must be a valid integer.")
            else:
                try:
                    queue_val = int(stripped)
                    if queue_val < MIN_QUEUE_LENGTH:
                        errors.append("Field 'queueLength' cannot be negative.")
                    elif queue_val > MAX_QUEUE_LENGTH:
                        errors.append(f"Field 'queueLength' exceeds plausible limit of {MAX_QUEUE_LENGTH} people.")
                    else:
                        sanitized["queueLength"] = queue_val
                except (ValueError, OverflowError):
                    errors.append("Field 'queueLength' must be a valid integer.")
        elif isinstance(raw_queue, int):
            if raw_queue < MIN_QUEUE_LENGTH:
                errors.append("Field 'queueLength' cannot be negative.")
            elif raw_queue > MAX_QUEUE_LENGTH:
                errors.append(f"Field 'queueLength' exceeds plausible limit of {MAX_QUEUE_LENGTH} people.")
            else:
                sanitized["queueLength"] = raw_queue
        else:
            errors.append("Field 'queueLength' must be a valid integer.")

    # 3. Validate optional note
    raw_note = body.get("note")
    sanitized["note"] = sanitize_note(raw_note)

    return (len(errors) == 0, sanitized, errors)


def validate_pagination_limit(
    raw_limit: Any,
    default: int = 50,
    min_val: int = 1,
    max_val: int = 100,
) -> Tuple[bool, int, Optional[str]]:
    """
    Validates pagination limit parameter.
    Rejects negative numbers, zero, booleans, NaN, Infinity, fractional floats, and values exceeding max_val.
    Returns (is_valid, validated_limit, error_message).
    """
    if raw_limit is None:
        return True, default, None
    if isinstance(raw_limit, bool):
        return False, default, "Query parameter 'limit' must be a valid integer."
    try:
        if isinstance(raw_limit, str):
            stripped = raw_limit.strip()
            if not re.match(r"^-?\d+$", stripped):
                return False, default, "Query parameter 'limit' must be a valid integer."
            val = int(stripped)
        elif isinstance(raw_limit, (int, float)):
            if isinstance(raw_limit, float) and (math.isnan(raw_limit) or math.isinf(raw_limit)):
                return False, default, "Query parameter 'limit' cannot be NaN or Infinity."
            if isinstance(raw_limit, float) and not raw_limit.is_integer():
                return False, default, "Query parameter 'limit' must be a whole integer."
            val = int(raw_limit)
        else:
            return False, default, "Query parameter 'limit' must be a valid integer."

        if val < min_val:
            return False, default, f"Query parameter 'limit' must be at least {min_val}."
        if val > max_val:
            return False, default, f"Query parameter 'limit' cannot exceed {max_val}."
        return True, val, None
    except (ValueError, OverflowError):
        return False, default, "Query parameter 'limit' must be a valid integer."


def validate_historical_days(
    raw_days: Any,
    default: int = 14,
    min_val: int = 1,
    max_val: int = 14,
) -> Tuple[bool, int, Optional[str]]:
    """
    Validates historical lookback days parameter (1 to 14 days).
    Rejects negative numbers, zero, booleans, NaN, Infinity, fractional floats, and out-of-range days.
    Returns (is_valid, validated_days, error_message).
    """
    if raw_days is None:
        return True, default, None
    if isinstance(raw_days, bool):
        return False, default, "Query parameter 'days' must be a valid integer."
    try:
        if isinstance(raw_days, str):
            stripped = raw_days.strip()
            if not re.match(r"^-?\d+$", stripped):
                return False, default, "Query parameter 'days' must be a valid integer."
            val = int(stripped)
        elif isinstance(raw_days, (int, float)):
            if isinstance(raw_days, float) and (math.isnan(raw_days) or math.isinf(raw_days)):
                return False, default, "Query parameter 'days' cannot be NaN or Infinity."
            if isinstance(raw_days, float) and not raw_days.is_integer():
                return False, default, "Query parameter 'days' must be a whole integer."
            val = int(raw_days)
        else:
            return False, default, "Query parameter 'days' must be a valid integer."

        if val < min_val or val > max_val:
            return False, default, f"Query parameter 'days' must be between {min_val} and {max_val} days."
        return True, val, None
    except (ValueError, OverflowError):
        return False, default, "Query parameter 'days' must be a valid integer."
