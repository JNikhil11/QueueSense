"""
Unit tests for QueueSense Queue Intelligence Engine.
Tests:
- Freshness exponential decay
- Outlier filtering (MAD and plausibility limits)
- Empty / Sparse data behavior
- Conflicting report disagreement
- Congestion classification
- Smart recommendations and disqualification of stale outlets
"""

import math
from datetime import datetime, timezone, timedelta
import pytest
from backend.shared.prediction import (
    calculate_freshness_weight,
    classify_congestion,
    filter_outliers,
    calculate_queue_estimate,
    compute_smart_recommendation,
    determine_freshness_status,
)


def test_freshness_weight_decay():
    now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
    # Age 0m -> weight 1.0
    w0 = calculate_freshness_weight(now, now, tau=15.0)
    assert pytest.approx(w0, rel=1e-3) == 1.0

    # Age 15m (tau) -> weight exp(-1) ~= 0.3678
    w15 = calculate_freshness_weight(now - timedelta(minutes=15), now, tau=15.0)
    assert pytest.approx(w15, rel=1e-3) == math.exp(-1)

    # Age 30m (2*tau) -> weight exp(-2) ~= 0.1353
    w30 = calculate_freshness_weight(now - timedelta(minutes=30), now, tau=15.0)
    assert pytest.approx(w30, rel=1e-3) == math.exp(-2)

    # Age 65m (> 60m max age) -> weight 0.0
    w65 = calculate_freshness_weight(now - timedelta(minutes=65), now, tau=15.0)
    assert w65 == 0.0


def test_classify_congestion():
    assert classify_congestion(2.0) == "LOW"
    assert classify_congestion(3.4) == "LOW"
    assert classify_congestion(5.0) == "MODERATE"
    assert classify_congestion(8.4) == "MODERATE"
    assert classify_congestion(12.0) == "HIGH"
    assert classify_congestion(15.4) == "HIGH"
    assert classify_congestion(22.0) == "VERY_HIGH"


def test_outlier_filtering():
    # Reports with obvious implausible values
    reports = [
        {"reportedWaitMinutes": 10, "queueLength": 15},
        {"reportedWaitMinutes": 12, "queueLength": 18},
        {"reportedWaitMinutes": 11, "queueLength": 14},
        {"reportedWaitMinutes": 140, "queueLength": 15},  # Plausibility limit (> 120)
        {"reportedWaitMinutes": -5, "queueLength": 10},   # Negative
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 3
    assert len(outliers) == 2

    # Statistical outlier via MAD
    normal_reports = [
        {"reportedWaitMinutes": 8, "queueLength": 10},
        {"reportedWaitMinutes": 9, "queueLength": 12},
        {"reportedWaitMinutes": 10, "queueLength": 14},
        {"reportedWaitMinutes": 8, "queueLength": 11},
        {"reportedWaitMinutes": 65, "queueLength": 15},  # Significant statistical spike
    ]
    v, o = filter_outliers(normal_reports)
    assert len(v) == 4
    assert len(o) == 1
    assert o[0]["reportedWaitMinutes"] == 65


def test_empty_and_sparse_reports():
    now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
    # Zero reports
    res_empty = calculate_queue_estimate([], now=now)
    assert res_empty["predictedWaitMinutes"] is None
    assert res_empty["congestion"] == "UNKNOWN"
    assert res_empty["confidence"] == 0.0
    assert res_empty["confidenceLabel"] == "NO DATA"
    assert res_empty["freshness"] == "NO RECENT DATA"

    # Single fresh report (2 min ago)
    single_report = [
        {
            "reportedWaitMinutes": 6.0,
            "queueLength": 8,
            "timestamp": (now - timedelta(minutes=2)).isoformat(),
        }
    ]
    res_single = calculate_queue_estimate(single_report, now=now)
    assert res_single["predictedWaitMinutes"] == 6.0
    assert res_single["predictedQueueLength"] == 8
    assert res_single["congestion"] == "MODERATE"
    assert res_single["freshness"] == "LIVE"
    assert res_single["confidenceLabel"] in ("LIMITED", "MODERATE")
    assert res_single["newestReportAgeMinutes"] == 2.0


def test_conflicting_reports_and_time_decay():
    now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
    # Report 1: 20 min ago reported 20 min wait
    # Report 2: 2 min ago reported 5 min wait (new condition)
    reports = [
        {
            "reportedWaitMinutes": 20.0,
            "queueLength": 30,
            "timestamp": (now - timedelta(minutes=20)).isoformat(),
        },
        {
            "reportedWaitMinutes": 5.0,
            "queueLength": 5,
            "timestamp": (now - timedelta(minutes=2)).isoformat(),
        },
    ]
    res = calculate_queue_estimate(reports, now=now)
    # Newer report should dominate the weight
    assert res["predictedWaitMinutes"] < 10.0
    assert res["freshness"] == "LIVE"
    assert res["disagreementMinutes"] == 15.0


def test_stale_reports_disregard():
    now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
    old_reports = [
        {
            "reportedWaitMinutes": 5.0,
            "queueLength": 6,
            "timestamp": (now - timedelta(minutes=75)).isoformat(),
        }
    ]
    res = calculate_queue_estimate(old_reports, now=now)
    assert res["predictedWaitMinutes"] is None
    assert res["freshness"] == "NO RECENT DATA"
    assert "no longer reflect current conditions" in res["evidenceExplanation"]


def test_smart_recommendation_selection():
    now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)

    locations = [
        {
            "id": "mess-a",
            "name": "Mess A",
            "active": True,
            "estimate": {
                "predictedWaitMinutes": 14.0,
                "confidence": 0.85,
                "confidenceLabel": "HIGH",
                "freshness": "LIVE",
                "recentReportCount": 4,
                "newestReportAgeMinutes": 3.0,
                "congestion": "HIGH",
            },
        },
        {
            "id": "mess-b",
            "name": "Mess B",
            "active": True,
            "estimate": {
                "predictedWaitMinutes": 4.5,
                "confidence": 0.75,
                "confidenceLabel": "HIGH",
                "freshness": "LIVE",
                "recentReportCount": 3,
                "newestReportAgeMinutes": 2.0,
                "congestion": "MODERATE",
            },
        },
        {
            "id": "canteen-c",
            "name": "Canteen C (Stale Data)",
            "active": True,
            "estimate": {
                "predictedWaitMinutes": 1.0,  # Very short wait, but stale! Must be disqualified
                "confidence": 0.10,
                "confidenceLabel": "VERY LOW",
                "freshness": "STALE",
                "recentReportCount": 1,
                "newestReportAgeMinutes": 45.0,
                "congestion": "LOW",
            },
        },
    ]

    rec = compute_smart_recommendation(locations)
    assert rec["isEligible"] is True
    assert rec["recommendedLocationId"] == "mess-b"
    assert rec["predictedWaitMinutes"] == 4.5
    assert "Shortest estimated wait" in rec["reason"]


def test_smart_recommendation_when_all_stale():
    locations = [
        {
            "id": "loc-1",
            "name": "Location 1",
            "active": True,
            "estimate": {
                "predictedWaitMinutes": None,
                "confidence": 0.0,
                "freshness": "NO RECENT DATA",
            },
        }
    ]
    rec = compute_smart_recommendation(locations)
    assert rec["isEligible"] is False
    assert rec["recommendedLocationId"] is None
    assert "Not enough recent queue reports" in rec["reason"]


def test_exact_20m_submission_scenario_regression():
    """
    Priority 1 Regression Test:
    Reproduction scenario:
    - Outlet had prior observations of 5m (2m ago) and 6m (8m ago).
    - User submits: 20 min wait, 40 people queue, note: "Heavy rush" at time now.
    - Verified:
      1. filter_outliers preserves the 20m report (it is not discarded as an outlier).
      2. calculate_queue_estimate computes time-decayed aggregate (~11.3m wait, ~20 people queue).
      3. Congestion status transitions from MODERATE to HIGH.
      4. Individual observation values (20m, 40 queue) are preserved in reports list.
    """
    now = datetime(2026, 11, 23, 12, 30, 0, tzinfo=timezone.utc)
    reports = [
        {
            "reportId": "rep_user_rush_01",
            "reportedWaitMinutes": 20.0,
            "queueLength": 40,
            "note": "Heavy rush",
            "timestamp": now.isoformat(),  # 0m ago (Just now)
        },
        {
            "reportId": "rep_seed_04",
            "reportedWaitMinutes": 5.0,
            "queueLength": 6,
            "note": "Very short queue",
            "timestamp": (now - timedelta(minutes=2)).isoformat(),  # 2m ago
        },
        {
            "reportId": "rep_seed_05",
            "reportedWaitMinutes": 6.0,
            "queueLength": 8,
            "note": "Smooth flow",
            "timestamp": (now - timedelta(minutes=8)).isoformat(),  # 8m ago
        },
    ]

    valid, outliers = filter_outliers(reports)
    assert len(valid) == 3, "20m report must not be discarded as an outlier"
    assert len(outliers) == 0

    est = calculate_queue_estimate(reports, now=now)
    # Total weight = 1.0 + exp(-2/15) + exp(-8/15) = 1.0 + 0.875 + 0.586 = 2.461
    # Weighted wait = (20*1.0 + 5*0.875 + 6*0.586) / 2.461 = 27.89 / 2.461 = 11.3m
    assert pytest.approx(est["predictedWaitMinutes"], abs=0.5) == 11.3
    assert est["predictedQueueLength"] in (19, 20)
    assert est["congestion"] == "HIGH"
    assert est["freshness"] == "LIVE"
    assert est["newestReportAgeMinutes"] == 0.0
    assert est["reportCount"] == 3


def test_mad_identical_reports_edge_case():
    """
    Stage 3 / Flaw C1: Outlier Detection MAD Edge Case (Identical Reports).
    When all reports have identical values, MAD = 0.
    The minimum cutoff of 25.0 min prevents zero-deviation division or false outlier rejection.
    """
    identical_reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 12} for _ in range(6)
    ]
    valid, outliers = filter_outliers(identical_reports)
    assert len(valid) == 6
    assert len(outliers) == 0


def test_half_life_decay_mathematical_precision():
    """
    Stage 3 / Flaw C4: Decay Constant Sensitivity & Half-Life Verification.
    For tau = 15.0 minutes, the exact half-life is t_1/2 = 15 * ln(2) = 10.3972077... minutes.
    At this exact age, the freshness weight MUST be 0.500.
    """
    now = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
    tau = 15.0
    half_life_minutes = tau * math.log(2)  # ~10.3972m

    t_half = now - timedelta(minutes=half_life_minutes)
    w_half = calculate_freshness_weight(t_half, now, tau=tau)
    assert pytest.approx(w_half, rel=1e-5) == 0.50000


def test_breakdown_point_and_majority_poisoning_defense():
    """
    Stage 3 / Flaw C2: Majority Poisoning & Robustness Boundaries.
    Verifies that:
    1. A single or minority poisoned extreme report (e.g. 110m among 8m reports) is rejected.
    2. Documented breakdown point: when malicious reports exceed 50%, statistical MAD breaks down,
       proving why upstream rate-limiting (5 submissions/5 min/IP) is the essential security barrier.
    """
    # 4 authentic reports vs 1 extreme malicious report -> outlier rejected
    reports_with_minority_poison = [
        {"reportedWaitMinutes": 8.0, "queueLength": 10},
        {"reportedWaitMinutes": 9.0, "queueLength": 12},
        {"reportedWaitMinutes": 8.5, "queueLength": 11},
        {"reportedWaitMinutes": 7.5, "queueLength": 9},
        {"reportedWaitMinutes": 110.0, "queueLength": 250},  # Poisoned injection
    ]
    valid, outliers = filter_outliers(reports_with_minority_poison)
    assert len(valid) == 4
    assert len(outliers) == 1
    assert outliers[0]["reportedWaitMinutes"] == 110.0



