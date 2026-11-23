"""
Unit tests for QueueSense Database layer (in-memory test mode).
"""

from backend.shared.database import QueueSenseDatabase, DEFAULT_CAMPUS_LOCATIONS


def test_database_initialization_and_listing():
    db = QueueSenseDatabase(table_name="TestTable")
    locations = db.list_locations()
    assert len(locations) == len(DEFAULT_CAMPUS_LOCATIONS)
    assert any(loc["id"] == "mess-a-central" for loc in locations)


def test_database_record_report():
    db = QueueSenseDatabase(table_name="TestTable")
    report = db.record_report(
        location_id="mess-a-central",
        reported_wait_minutes=10.5,
        queue_length=15,
        note="Normal pace",
    )
    assert report["reportId"].startswith("rep_")
    assert report["reportedWaitMinutes"] == 10.5
    assert report["queueLength"] == 15
    assert "timestamp" in report
    assert report["ttl"] > 0

    # Retrieve recent reports
    recents = db.get_recent_reports("mess-a-central")
    assert len(recents) >= 1
    assert recents[0]["reportId"] == report["reportId"]


def test_database_estimate_caching():
    db = QueueSenseDatabase(table_name="TestTable")
    estimate_data = {
        "predictedWaitMinutes": 8.0,
        "congestion": "MODERATE",
        "confidence": 0.8,
        "freshness": "LIVE",
    }
    db.save_current_estimate("mess-a-central", estimate_data)

    retrieved = db.get_current_estimate("mess-a-central")
    assert retrieved is not None
    assert retrieved["predictedWaitMinutes"] == 8.0
    assert retrieved["congestion"] == "MODERATE"
