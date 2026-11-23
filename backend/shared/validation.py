"""
QueueSense - Request Validation & Input Sanitization
Provides deterministic validation for user reports, query params, and IDs.
Ensures zero HTML injection, bounded values, and clean error structures.
"""

from __future__ import annotations
import re
from typing import Dict, Any, Tuple, List, Optional

LOCATION_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{2,40}$")
NOTE_DISALLOWED_CHARS = re.compile(r"[<>{}\\\^`~]")

MAX_WAIT_MINUTES = 120
MAX_QUEUE_LENGTH = 300
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
      - reportedWaitMinutes: int or float [0, 120]
      - queueLength: int [0, 300]
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
        try:
            wait_val = float(body["reportedWaitMinutes"])
            if wait_val < 0:
                errors.append("Field 'reportedWaitMinutes' cannot be negative.")
            elif wait_val > MAX_WAIT_MINUTES:
                errors.append(f"Field 'reportedWaitMinutes' exceeds plausible limit of {MAX_WAIT_MINUTES} minutes.")
            else:
                sanitized["reportedWaitMinutes"] = round(wait_val, 1)
        except (ValueError, TypeError):
            errors.append("Field 'reportedWaitMinutes' must be a valid numeric value.")

    # 2. Validate queueLength
    if "queueLength" not in body:
        # If omitted, defaults to 0
        sanitized["queueLength"] = 0
    else:
        try:
            queue_val = int(body["queueLength"])
            if queue_val < 0:
                errors.append("Field 'queueLength' cannot be negative.")
            elif queue_val > MAX_QUEUE_LENGTH:
                errors.append(f"Field 'queueLength' exceeds plausible limit of {MAX_QUEUE_LENGTH} people.")
            else:
                sanitized["queueLength"] = queue_val
        except (ValueError, TypeError):
            errors.append("Field 'queueLength' must be a valid integer.")

    # 3. Validate optional note
    raw_note = body.get("note")
    sanitized["note"] = sanitize_note(raw_note)

    return (len(errors) == 0, sanitized, errors)
