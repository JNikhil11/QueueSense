"""
Unit tests for QueueSense input validation, security sanitization, and location patterns.
"""

from backend.shared.validation import (
    validate_location_id,
    validate_report_payload,
    sanitize_note,
)


def test_validate_location_id():
    assert validate_location_id("mess-a") is True
    assert validate_location_id("canteen_rock_plaza_1") is True
    assert validate_location_id("a") is False  # too short (<2)
    assert validate_location_id("mess;DROP TABLE") is False  # SQL injection attempt
    assert validate_location_id("<script>") is False
    assert validate_location_id("../etc/passwd") is False


def test_sanitize_note():
    assert sanitize_note(None) is None
    assert sanitize_note("  Fast moving line at counter 2  ") == "Fast moving line at counter 2"
    # Strips angle brackets and dangerous characters
    assert sanitize_note("<script>alert('xss')</script>") == "scriptalert('xss')/script"
    # Truncates to 140 chars
    long_note = "A" * 200
    assert len(sanitize_note(long_note)) == 140


def test_validate_report_payload_valid():
    valid_payload = {
        "reportedWaitMinutes": 12,
        "queueLength": 18,
        "note": "Counters 1 and 2 open.",
    }
    is_valid, data, errors = validate_report_payload(valid_payload)
    assert is_valid is True
    assert len(errors) == 0
    assert data["reportedWaitMinutes"] == 12.0
    assert data["queueLength"] == 18
    assert data["note"] == "Counters 1 and 2 open."


def test_validate_report_payload_negative_values():
    bad_payload = {
        "reportedWaitMinutes": -5,
        "queueLength": -1,
    }
    is_valid, data, errors = validate_report_payload(bad_payload)
    assert is_valid is False
    assert any("negative" in err for err in errors)


def test_validate_report_payload_excessive_values():
    excessive_payload = {
        "reportedWaitMinutes": 350,  # Max is 120
        "queueLength": 9999,         # Max is 300
    }
    is_valid, data, errors = validate_report_payload(excessive_payload)
    assert is_valid is False
    assert len(errors) == 2


def test_validate_report_payload_missing_required():
    empty_payload = {}
    is_valid, data, errors = validate_report_payload(empty_payload)
    assert is_valid is False
    assert any("reportedWaitMinutes" in err for err in errors)

