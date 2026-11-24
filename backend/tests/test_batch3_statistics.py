"""
QueueSense - Batch 3 Statistical Integrity, Model Validity & Ground-Truth Test Suite
Comprehensive testing for:
- P1.13: MAD Outlier Handling & Rush-Hour Surge Corroboration (12 Adversarial Scenarios)
- P1.14: Time-Decay Model, Half-Life Verification & Smooth Cosine Tapering
- P1.15: Dynamic Evidence-Weighting Normalization (45/35/20) & Epistemic Uncertainty Bounds
- P1.16: Recommendation Engine Cold-Start Protection, Independent Device Corroboration & Fail-Safe States
- P1.17: Absence of Physical Ground Truth Disclosure & Numerical Stability (NaN, Inf, Zero Denominators)
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
    DEFAULT_DECAY_CONSTANT_MINUTES,
    MAX_REPORT_AGE_MINUTES,
    TAPER_START_AGE_MINUTES,
)


# ==============================================================================
# P1.13: MAD OUTLIER HANDLING & CORROBORATED SURGE BEHAVIOUR (12 SCENARIOS)
# ==============================================================================

def test_p1_13_scenario_1_normal_queue_low_variance():
    """Scenario 1: Normal queue observations with low variance (all preserved)."""
    reports = [
        {"reportedWaitMinutes": 8.0, "queueLength": 10},
        {"reportedWaitMinutes": 9.0, "queueLength": 12},
        {"reportedWaitMinutes": 8.5, "queueLength": 11},
        {"reportedWaitMinutes": 9.5, "queueLength": 13},
        {"reportedWaitMinutes": 8.0, "queueLength": 10},
        {"reportedWaitMinutes": 9.0, "queueLength": 11},
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 6
    assert len(outliers) == 0


def test_p1_13_scenario_2_isolated_extremely_high_wait_time():
    """Scenario 2: One extremely high wait-time report among normal reports (isolated -> outlier)."""
    now_ts = "2026-11-24T12:00:00Z"
    reports = [
        {"reportedWaitMinutes": 8.0, "queueLength": 10, "timestamp": now_ts},
        {"reportedWaitMinutes": 9.0, "queueLength": 12, "timestamp": now_ts},
        {"reportedWaitMinutes": 8.5, "queueLength": 11, "timestamp": now_ts},
        {"reportedWaitMinutes": 8.0, "queueLength": 10, "timestamp": now_ts},
        {"reportedWaitMinutes": 9.0, "queueLength": 12, "timestamp": now_ts},
        {"reportedWaitMinutes": 110.0, "queueLength": 15, "timestamp": now_ts},  # Isolated spike
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 5
    assert len(outliers) == 1
    assert outliers[0]["reportedWaitMinutes"] == 110.0
    assert outliers[0]["outlierReason"] == "UNCORROBORATED_ISOLATED_SPIKE"


def test_p1_13_scenario_3_isolated_extremely_low_report():
    """Scenario 3: One extremely low report among high reports (isolated -> outlier)."""
    now_ts = "2026-11-24T12:00:00Z"
    reports = [
        {"reportedWaitMinutes": 45.0, "queueLength": 60, "timestamp": now_ts},
        {"reportedWaitMinutes": 48.0, "queueLength": 65, "timestamp": now_ts},
        {"reportedWaitMinutes": 46.0, "queueLength": 62, "timestamp": now_ts},
        {"reportedWaitMinutes": 50.0, "queueLength": 68, "timestamp": now_ts},
        {"reportedWaitMinutes": 47.0, "queueLength": 63, "timestamp": now_ts},
        {"reportedWaitMinutes": 2.0, "queueLength": 5, "timestamp": now_ts},   # Isolated drop
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 5
    assert len(outliers) == 1
    assert outliers[0]["reportedWaitMinutes"] == 2.0
    assert outliers[0]["outlierReason"] == "UNCORROBORATED_ISOLATED_DROP"


def test_p1_13_scenario_4_genuine_rush_hour_surge_corroborated():
    """Scenario 4: Genuine rush-hour surge supported by multiple reports (corroborated -> retained)."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 5.0, "queueLength": 6, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "dev-b1"},
        {"reportedWaitMinutes": 6.0, "queueLength": 7, "timestamp": (now - timedelta(minutes=6)).isoformat(), "deviceId": "dev-b2"},
        {"reportedWaitMinutes": 5.5, "queueLength": 6, "timestamp": (now - timedelta(minutes=7)).isoformat(), "deviceId": "dev-b3"},
        {"reportedWaitMinutes": 6.0, "queueLength": 8, "timestamp": (now - timedelta(minutes=8)).isoformat(), "deviceId": "dev-b4"},
        {"reportedWaitMinutes": 5.0, "queueLength": 6, "timestamp": (now - timedelta(minutes=9)).isoformat(), "deviceId": "dev-b5"},
        # Corroborating surge: Two students report ~35m wait with elevated queues within 30m from distinct devices
        {"reportedWaitMinutes": 35.0, "queueLength": 45, "timestamp": (now - timedelta(minutes=2)).isoformat(), "deviceId": "dev-surge-1"},
        {"reportedWaitMinutes": 38.0, "queueLength": 50, "timestamp": (now - timedelta(minutes=4)).isoformat(), "deviceId": "dev-surge-2"},
    ]
    valid, outliers = filter_outliers(reports, now=now)
    assert len(valid) == 7, "Corroborated surge reports must NOT be discarded as outliers"
    assert len(outliers) == 0


def test_p1_13_scenario_5_sudden_surge_supported_by_only_one_report():
    """Scenario 5: Sudden surge supported by only one report (isolated -> suppressed from dominating)."""
    reports = [
        {"reportedWaitMinutes": 5.0, "queueLength": 6},
        {"reportedWaitMinutes": 6.0, "queueLength": 8},
        {"reportedWaitMinutes": 5.5, "queueLength": 7},
        {"reportedWaitMinutes": 5.0, "queueLength": 6},
        {"reportedWaitMinutes": 6.0, "queueLength": 7},
        {"reportedWaitMinutes": 40.0, "queueLength": 10},  # Uncorroborated single report
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 5
    assert len(outliers) == 1
    assert outliers[0]["reportedWaitMinutes"] == 40.0


def test_p1_13_scenario_6_mad_equal_to_zero():
    """Scenario 6: MAD equal to zero (identical reports -> handled safely without division by zero)."""
    reports = [{"reportedWaitMinutes": 12.0, "queueLength": 15} for _ in range(8)]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 8
    assert len(outliers) == 0


def test_p1_13_scenario_7_one_observation_sample():
    """Scenario 7: One-observation sample (retained, bounded uncertainty)."""
    reports = [{"reportedWaitMinutes": 15.0, "queueLength": 20}]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 1
    assert len(outliers) == 0


def test_p1_13_scenario_8_two_observation_sample():
    """Scenario 8: Two-observation sample (retained, disagreement measured)."""
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 12},
        {"reportedWaitMinutes": 25.0, "queueLength": 30},
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 2
    assert len(outliers) == 0


def test_p1_13_scenario_9_small_sample_with_high_variance():
    """Scenario 9: Small sample (N=3, 4) with high variance (retained, avoids false outlier rejection)."""
    reports = [
        {"reportedWaitMinutes": 5.0, "queueLength": 6},
        {"reportedWaitMinutes": 12.0, "queueLength": 16},
        {"reportedWaitMinutes": 28.0, "queueLength": 35},
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 3
    assert len(outliers) == 0


def test_p1_13_scenario_10_repeated_identical_submissions():
    """Scenario 10: Repeated identical submissions (retained without crashing, distinct devices tracked)."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    reports = [
        {
            "reportedWaitMinutes": 10.0,
            "queueLength": 12,
            "deviceId": "dev_same_attacker",
            "timestamp": (now - timedelta(minutes=i)).isoformat(),
        }
        for i in range(5)
    ]
    est = calculate_queue_estimate(reports, now=now)
    assert est["predictedWaitMinutes"] == 10.0
    assert est["distinctDevicesCount"] == 1, "Single device submitting 5 times must show distinctDevicesCount = 1"


def test_p1_13_scenario_11_conflicting_wait_time_and_queue_length():
    """Scenario 11: Reports with conflicting wait-time and queue-length (e.g. wait=10m, queue=290 -> safe)."""
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 290},
        {"reportedWaitMinutes": 12.0, "queueLength": 10},
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 2
    assert len(outliers) == 0


def test_p1_13_scenario_12_surge_followed_by_rapid_return_to_normal():
    """Scenario 12: A surge followed by rapid return to normal (recent normal reports decay older surge)."""
    now = datetime(2026, 11, 24, 13, 0, 0, tzinfo=timezone.utc)
    # 25 min ago: Surge was 35m
    # 2 min ago: Cleared to 5m
    reports = [
        {
            "reportedWaitMinutes": 35.0,
            "queueLength": 45,
            "timestamp": (now - timedelta(minutes=25)).isoformat(),
        },
        {
            "reportedWaitMinutes": 5.0,
            "queueLength": 6,
            "timestamp": (now - timedelta(minutes=2)).isoformat(),
        },
    ]
    est = calculate_queue_estimate(reports, now=now)
    # Weight of 2m report (~0.875) heavily dominates 25m report (~0.189), bringing wait from 35m down to ~10.3m
    assert est["predictedWaitMinutes"] < 12.0
    assert est["congestion"] in ("MODERATE", "HIGH")


# ==============================================================================
# P1.14: TIME-DECAY MODEL, HALF-LIFE & SMOOTH TAPERING TESTS
# ==============================================================================

def test_p1_14_decay_half_life_exact_verification():
    """Verify exact half-life: t_1/2 = tau * ln(2) ~= 10.3972m produces weight exactly 0.500."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    tau = DEFAULT_DECAY_CONSTANT_MINUTES  # 15.0m
    t_half_minutes = tau * math.log(2)

    t_half = now - timedelta(minutes=t_half_minutes)
    w_half = calculate_freshness_weight(t_half, now, tau=tau)
    assert pytest.approx(w_half, rel=1e-5) == 0.50000


def test_p1_14_relative_weights_table_derivation():
    """Verify relative weights table at 0m, 5m, 10m, 15m, 20m, 30m, 45m, 50m."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    tau = 15.0

    w0 = calculate_freshness_weight(now, now, tau=tau)
    w5 = calculate_freshness_weight(now - timedelta(minutes=5), now, tau=tau)
    w10 = calculate_freshness_weight(now - timedelta(minutes=10), now, tau=tau)
    w15 = calculate_freshness_weight(now - timedelta(minutes=15), now, tau=tau)
    w20 = calculate_freshness_weight(now - timedelta(minutes=20), now, tau=tau)
    w30 = calculate_freshness_weight(now - timedelta(minutes=30), now, tau=tau)
    w45 = calculate_freshness_weight(now - timedelta(minutes=45), now, tau=tau)
    w50 = calculate_freshness_weight(now - timedelta(minutes=50), now, tau=tau)

    assert pytest.approx(w0, rel=1e-4) == 1.0000
    assert pytest.approx(w5, rel=1e-4) == math.exp(-5.0 / 15.0)  # ~0.7165
    assert pytest.approx(w10, rel=1e-4) == math.exp(-10.0 / 15.0)  # ~0.5134
    assert pytest.approx(w15, rel=1e-4) == math.exp(-1.0)  # ~0.3679
    assert pytest.approx(w20, rel=1e-4) == math.exp(-20.0 / 15.0)  # ~0.2636
    assert pytest.approx(w30, rel=1e-4) == math.exp(-2.0)  # ~0.1353
    assert pytest.approx(w45, rel=1e-4) == math.exp(-3.0)  # ~0.0498
    assert pytest.approx(w50, rel=1e-4) == math.exp(-50.0 / 15.0)  # ~0.0357


def test_p1_14_smooth_cosine_tapering_eliminates_60m_step_discontinuity():
    """
    Verify smooth cosine tapering between 50m and 60m:
    At 50m: T=1.0 -> weight = base_weight.
    At 55m: T=0.5 -> weight = base_weight * 0.5.
    At 59.9m: T -> 0.0 smoothly.
    At 60.0m: weight = 0.0 with zero step cliff.
    """
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    tau = 15.0

    w50 = calculate_freshness_weight(now - timedelta(minutes=50.0), now, tau=tau)
    w55 = calculate_freshness_weight(now - timedelta(minutes=55.0), now, tau=tau)
    w59_9 = calculate_freshness_weight(now - timedelta(minutes=59.9), now, tau=tau)
    w60 = calculate_freshness_weight(now - timedelta(minutes=60.0), now, tau=tau)
    w60_1 = calculate_freshness_weight(now - timedelta(minutes=60.1), now, tau=tau)

    base55 = math.exp(-55.0 / 15.0)
    assert pytest.approx(w55, rel=1e-4) == base55 * 0.5
    assert 0.0 < w59_9 < 0.001
    assert w60 == 0.0
    assert w60_1 == 0.0
    # Strict monotonic decay to zero
    assert w50 > w55 > w59_9 > w60


def test_p1_14_future_timestamps_and_clock_skew():
    """Future timestamps > 30s are rejected (weight 0.0); slight NTP jitter (-10s) is clamped."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)

    # 45s in future -> rejected
    w_future = calculate_freshness_weight(now + timedelta(seconds=45), now)
    assert w_future == 0.0

    # 10s in future (NTP jitter) -> clamped to age 0 (weight 1.0)
    w_jitter = calculate_freshness_weight(now + timedelta(seconds=10), now)
    assert pytest.approx(w_jitter, rel=1e-4) == 1.0


# ==============================================================================
# P1.15: DYNAMIC EVIDENCE WEIGHTING (45/35/20) & UNCERTAINTY BOUNDS
# ==============================================================================

def test_p1_15_full_model_weights_sum_to_one():
    """Full model with N >= 2: Volume 45% + Recency 35% + Agreement 20% = 100%."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    # 4 reports (full volume), age 0m (full recency), 0m disagreement (full agreement)
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 12, "timestamp": now.isoformat()}
        for _ in range(4)
    ]
    est = calculate_queue_estimate(reports, now=now)
    assert est["confidence"] == 1.0
    assert est["confidenceLabel"] == "HIGH"
    assert est["confidenceScoreType"] == "HEURISTIC_COMPOSITE"


def test_p1_15_dynamic_renormalization_for_single_observation():
    """
    When N=1, agreement cannot be evaluated.
    Weights are dynamically renormalized across volume and recency (summing to 1.0),
    and epistemic single-source uncertainty caps confidence at 0.40.
    """
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    single_report = [
        {"reportedWaitMinutes": 8.0, "queueLength": 10, "timestamp": now.isoformat()}
    ]
    est = calculate_queue_estimate(single_report, now=now)
    assert est["confidence"] <= 0.40, "Single observation confidence must be capped at 0.40"
    assert est["confidenceLabel"] in ("LIMITED", "MODERATE")
    assert est["confidenceScoreType"] == "HEURISTIC_COMPOSITE"


def test_p1_15_disagreement_penalizes_confidence():
    """High disagreement (> 15 min) eliminates agreement factor, reducing confidence."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 5.0, "queueLength": 6, "timestamp": now.isoformat()},
        {"reportedWaitMinutes": 25.0, "queueLength": 30, "timestamp": now.isoformat()},
    ]
    est = calculate_queue_estimate(reports, now=now)
    assert est["disagreementMinutes"] == 20.0
    # Agreement factor is 0.0; confidence only comes from volume (2/4 * 0.45 = 0.225) + recency (0.35) = ~0.58
    assert est["confidence"] <= 0.60


def test_p1_15_missing_evidence_zero_reports():
    """When no reports exist, confidence is strictly 0.0 with label 'NO DATA'."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    est = calculate_queue_estimate([], now=now)
    assert est["confidence"] == 0.0
    assert est["confidenceLabel"] == "NO DATA"
    assert est["predictedWaitMinutes"] is None


# ==============================================================================
# P1.16: RECOMMENDATION ENGINE & INDEPENDENT EVIDENCE ENFORCEMENT
# ==============================================================================

def test_p1_16_qualifies_with_three_distinct_device_reports():
    """3 fresh reports from 3 distinct devices with >= 50% confidence qualifies for recommendation."""
    locations = [
        {
            "id": "mess-a",
            "name": "Mess A",
            "active": True,
            "verificationStatus": "STUDENT_SOURCED",
            "estimate": {
                "predictedWaitMinutes": 6.5,
                "confidence": 0.75,
                "confidenceLabel": "HIGH",
                "freshness": "LIVE",
                "recentReportCount": 3,
                "distinctDevicesCount": 3,
                "newestReportAgeMinutes": 2.0,
                "congestion": "MODERATE",
            },
        }
    ]
    rec = compute_smart_recommendation(locations)
    assert rec["isEligible"] is True
    assert rec["state"] == "recommended"
    assert rec["recommendedLocationId"] == "mess-a"


def test_p1_16_disqualifies_single_device_repeated_submissions():
    """3 reports submitted from a single device (distinctDevicesCount=1) is disqualified."""
    locations = [
        {
            "id": "mess-spam",
            "name": "Mess Spam",
            "active": True,
            "verificationStatus": "STUDENT_SOURCED",
            "estimate": {
                "predictedWaitMinutes": 5.0,
                "confidence": 0.80,
                "confidenceLabel": "HIGH",
                "freshness": "LIVE",
                "recentReportCount": 3,
                "distinctDevicesCount": 1,  # Single device trying to manufacture consensus!
                "newestReportAgeMinutes": 1.0,
                "congestion": "MODERATE",
            },
        }
    ]
    rec = compute_smart_recommendation(locations)
    assert rec["isEligible"] is False
    assert rec["state"] == "insufficient_data"
    assert rec["recommendedLocationId"] is None


def test_p1_16_disqualifies_unverified_and_inactive_outlets():
    """Unverified or inactive outlets must never receive a recommendation."""
    locations = [
        {
            "id": "mess-inactive",
            "name": "Mess Inactive",
            "active": False,
            "verificationStatus": "STUDENT_SOURCED",
            "estimate": {
                "predictedWaitMinutes": 2.0,
                "confidence": 0.90,
                "freshness": "LIVE",
                "recentReportCount": 4,
                "distinctDevicesCount": 4,
            },
        },
        {
            "id": "mess-unverified",
            "name": "Mess Unverified",
            "active": True,
            "verificationStatus": "UNVERIFIED",
            "estimate": {
                "predictedWaitMinutes": 2.5,
                "confidence": 0.90,
                "freshness": "LIVE",
                "recentReportCount": 4,
                "distinctDevicesCount": 4,
            },
        },
    ]
    rec = compute_smart_recommendation(locations)
    assert rec["isEligible"] is False
    assert rec["recommendedLocationId"] is None


def test_p1_16_stale_data_state_transition():
    """When all campus reports are older than 20m, returns state 'stale_data'."""
    locations = [
        {
            "id": "mess-stale",
            "name": "Mess Stale",
            "active": True,
            "verificationStatus": "STUDENT_SOURCED",
            "estimate": {
                "predictedWaitMinutes": 5.0,
                "confidence": 0.30,
                "confidenceLabel": "LIMITED",
                "freshness": "STALE",
                "recentReportCount": 2,
                "distinctDevicesCount": 2,
                "newestReportAgeMinutes": 35.0,
                "congestion": "MODERATE",
            },
        }
    ]
    rec = compute_smart_recommendation(locations)
    assert rec["isEligible"] is False
    assert rec["state"] == "stale_data"
    assert "over 20 minutes old and considered stale" in rec["reason"]


def test_p1_16_no_active_outlets_state_transition():
    """When all campus outlets are marked inactive, returns state 'no_active_outlets'."""
    locations = [
        {"id": "mess-1", "name": "Mess 1", "active": False, "estimate": {}},
        {"id": "mess-2", "name": "Mess 2", "active": False, "estimate": {}},
    ]
    rec = compute_smart_recommendation(locations)
    assert rec["isEligible"] is False
    assert rec["state"] == "no_active_outlets"
    assert "currently open or active" in rec["reason"]


# ==============================================================================
# P1.17: NUMERICAL STABILITY & SCIENTIFIC HONESTY TESTS
# ==============================================================================

def test_p1_17_nan_and_infinity_rejection():
    """Float NaN and Infinity in wait time or queue length are rejected without throwing exceptions."""
    reports = [
        {"reportedWaitMinutes": float("nan"), "queueLength": 10},
        {"reportedWaitMinutes": float("inf"), "queueLength": 10},
        {"reportedWaitMinutes": float("-inf"), "queueLength": 10},
        {"reportedWaitMinutes": 10.0, "queueLength": float("nan")},
        {"reportedWaitMinutes": 10.0, "queueLength": float("inf")},
        {"reportedWaitMinutes": 12.0, "queueLength": 15},  # Valid
    ]
    valid, outliers = filter_outliers(reports)
    assert len(valid) == 1
    assert len(outliers) == 5
    for o in outliers:
        assert "INVALID_FLOAT" in o["outlierReason"]


def test_p1_17_scientific_honesty_composite_type():
    """Estimate payload explicitly categorizes confidence score as HEURISTIC_COMPOSITE."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 8.0, "queueLength": 10, "timestamp": now.isoformat()},
        {"reportedWaitMinutes": 9.0, "queueLength": 11, "timestamp": now.isoformat()},
    ]
    est = calculate_queue_estimate(reports, now=now)
    assert est["confidenceScoreType"] == "HEURISTIC_COMPOSITE"
    assert "disagreementMinutes" in est
    assert "outliersExcluded" in est


# ==============================================================================
# P1.13 CORRECTION PASS: TEMPORAL & OBSERVER CORROBORATION REGRESSION TESTS
# ==============================================================================

def test_p1_13_corroboration_two_reports_within_30m_different_devices():
    """Two candidate spikes within 30 min from different devices corroborate each other."""
    now = datetime(2026, 11, 24, 12, 30, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "base-1"},
        {"reportedWaitMinutes": 10.5, "queueLength": 11, "timestamp": (now - timedelta(minutes=6)).isoformat(), "deviceId": "base-2"},
        {"reportedWaitMinutes": 9.5, "queueLength": 9, "timestamp": (now - timedelta(minutes=7)).isoformat(), "deviceId": "base-3"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=8)).isoformat(), "deviceId": "base-4"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=9)).isoformat(), "deviceId": "base-5"},
        # Candidate spikes (> 10 + 25 = 35 min)
        {"reportedWaitMinutes": 55.0, "queueLength": 60, "timestamp": (now - timedelta(minutes=10)).isoformat(), "deviceId": "dev-alpha"},
        {"reportedWaitMinutes": 58.0, "queueLength": 65, "timestamp": (now - timedelta(minutes=15)).isoformat(), "deviceId": "dev-beta"},
    ]
    valid, outliers = filter_outliers(reports, now=now)
    assert len(valid) == 7
    assert len(outliers) == 0


def test_p1_13_uncorroborated_two_reports_exceeding_30m_window():
    """Two candidate spikes separated by > 30 minutes cannot corroborate each other."""
    now = datetime(2026, 11, 24, 13, 0, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "base-1"},
        {"reportedWaitMinutes": 10.5, "queueLength": 11, "timestamp": (now - timedelta(minutes=6)).isoformat(), "deviceId": "base-2"},
        {"reportedWaitMinutes": 9.5, "queueLength": 9, "timestamp": (now - timedelta(minutes=7)).isoformat(), "deviceId": "base-3"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=8)).isoformat(), "deviceId": "base-4"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=9)).isoformat(), "deviceId": "base-5"},
        # Candidate spikes 45 minutes apart (> 30 min window)
        {"reportedWaitMinutes": 55.0, "queueLength": 60, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "dev-alpha"},
        {"reportedWaitMinutes": 58.0, "queueLength": 65, "timestamp": (now - timedelta(minutes=50)).isoformat(), "deviceId": "dev-beta"},
    ]
    valid, outliers = filter_outliers(reports, now=now)
    assert len(valid) == 5
    assert len(outliers) == 2
    for o in outliers:
        assert o["outlierReason"] == "UNCORROBORATED_ISOLATED_SPIKE"


def test_p1_13_uncorroborated_two_reports_same_device():
    """Two candidate spikes from the same device cannot establish peer consensus."""
    now = datetime(2026, 11, 24, 12, 30, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "base-1"},
        {"reportedWaitMinutes": 10.5, "queueLength": 11, "timestamp": (now - timedelta(minutes=6)).isoformat(), "deviceId": "base-2"},
        {"reportedWaitMinutes": 9.5, "queueLength": 9, "timestamp": (now - timedelta(minutes=7)).isoformat(), "deviceId": "base-3"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=8)).isoformat(), "deviceId": "base-4"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=9)).isoformat(), "deviceId": "base-5"},
        # Same device submitting two spikes within 5 minutes
        {"reportedWaitMinutes": 55.0, "queueLength": 60, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "dev-same"},
        {"reportedWaitMinutes": 58.0, "queueLength": 65, "timestamp": (now - timedelta(minutes=10)).isoformat(), "deviceId": "dev-same"},
    ]
    valid, outliers = filter_outliers(reports, now=now)
    assert len(valid) == 5
    assert len(outliers) == 2
    for o in outliers:
        assert o["outlierReason"] == "UNCORROBORATED_ISOLATED_SPIKE"


def test_p1_13_uncorroborated_missing_timestamp():
    """Candidate spikes with missing timestamps cannot establish temporal concurrency."""
    now = datetime(2026, 11, 24, 12, 30, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "base-1"},
        {"reportedWaitMinutes": 10.5, "queueLength": 11, "timestamp": (now - timedelta(minutes=6)).isoformat(), "deviceId": "base-2"},
        {"reportedWaitMinutes": 9.5, "queueLength": 9, "timestamp": (now - timedelta(minutes=7)).isoformat(), "deviceId": "base-3"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=8)).isoformat(), "deviceId": "base-4"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=9)).isoformat(), "deviceId": "base-5"},
        # Two spikes, but missing timestamps
        {"reportedWaitMinutes": 55.0, "queueLength": 60, "deviceId": "dev-alpha"},
        {"reportedWaitMinutes": 58.0, "queueLength": 65, "timestamp": None, "deviceId": "dev-beta"},
    ]
    valid, outliers = filter_outliers(reports, now=now)
    assert len(valid) == 5
    assert len(outliers) == 2
    for o in outliers:
        assert o["outlierReason"] == "UNCORROBORATED_MISSING_TIMESTAMP"


def test_p1_13_uncorroborated_invalid_timestamp():
    """Candidate spikes with unparseable timestamps cannot establish temporal concurrency."""
    now = datetime(2026, 11, 24, 12, 30, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "base-1"},
        {"reportedWaitMinutes": 10.5, "queueLength": 11, "timestamp": (now - timedelta(minutes=6)).isoformat(), "deviceId": "base-2"},
        {"reportedWaitMinutes": 9.5, "queueLength": 9, "timestamp": (now - timedelta(minutes=7)).isoformat(), "deviceId": "base-3"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=8)).isoformat(), "deviceId": "base-4"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=9)).isoformat(), "deviceId": "base-5"},
        # Malformed timestamp strings
        {"reportedWaitMinutes": 55.0, "queueLength": 60, "timestamp": "invalid-iso-string", "deviceId": "dev-alpha"},
        {"reportedWaitMinutes": 58.0, "queueLength": 65, "timestamp": "2026-99-99T99:99:99Z", "deviceId": "dev-beta"},
    ]
    valid, outliers = filter_outliers(reports, now=now)
    assert len(valid) == 5
    assert len(outliers) == 2
    for o in outliers:
        assert o["outlierReason"] == "UNCORROBORATED_MISSING_TIMESTAMP"


def test_p1_13_mixed_surge_peers_partial_corroboration():
    """When 3 spikes exist, only mutually proximate peers within 30m corroborate; distant one is excluded."""
    now = datetime(2026, 11, 24, 13, 0, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "base-1"},
        {"reportedWaitMinutes": 10.5, "queueLength": 11, "timestamp": (now - timedelta(minutes=6)).isoformat(), "deviceId": "base-2"},
        {"reportedWaitMinutes": 9.5, "queueLength": 9, "timestamp": (now - timedelta(minutes=7)).isoformat(), "deviceId": "base-3"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=8)).isoformat(), "deviceId": "base-4"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=9)).isoformat(), "deviceId": "base-5"},
        # Two spikes 5m apart at T-10m and T-15m
        {"reportedWaitMinutes": 55.0, "queueLength": 60, "timestamp": (now - timedelta(minutes=10)).isoformat(), "deviceId": "dev-alpha"},
        {"reportedWaitMinutes": 58.0, "queueLength": 65, "timestamp": (now - timedelta(minutes=15)).isoformat(), "deviceId": "dev-beta"},
        # Third spike 55m ago (> 30m away from dev-alpha and dev-beta)
        {"reportedWaitMinutes": 60.0, "queueLength": 70, "timestamp": (now - timedelta(minutes=55)).isoformat(), "deviceId": "dev-gamma"},
    ]
    valid, outliers = filter_outliers(reports, now=now)
    assert len(valid) == 7
    assert len(outliers) == 1
    assert outliers[0]["deviceId"] == "dev-gamma"
    assert outliers[0]["outlierReason"] == "UNCORROBORATED_ISOLATED_SPIKE"


def test_p1_13_isolated_high_wait_high_queue_cannot_self_corroborate():
    """An isolated report with extreme wait and high queue cannot self-corroborate without a peer report."""
    now = datetime(2026, 11, 24, 12, 30, 0, tzinfo=timezone.utc)
    reports = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=5)).isoformat(), "deviceId": "base-1"},
        {"reportedWaitMinutes": 10.5, "queueLength": 11, "timestamp": (now - timedelta(minutes=6)).isoformat(), "deviceId": "base-2"},
        {"reportedWaitMinutes": 9.5, "queueLength": 9, "timestamp": (now - timedelta(minutes=7)).isoformat(), "deviceId": "base-3"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=8)).isoformat(), "deviceId": "base-4"},
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=9)).isoformat(), "deviceId": "base-5"},
        # Extreme wait and queue without any peer
        {"reportedWaitMinutes": 110.0, "queueLength": 250, "timestamp": (now - timedelta(minutes=2)).isoformat(), "deviceId": "dev-isolated"},
    ]
    valid, outliers = filter_outliers(reports, now=now)
    assert len(valid) == 5
    assert len(outliers) == 1
    assert outliers[0]["deviceId"] == "dev-isolated"
    assert outliers[0]["outlierReason"] == "UNCORROBORATED_ISOLATED_SPIKE"


# ==============================================================================
# P1.15 CORRECTION PASS: CONFIDENCE BOUNDARY (0.39, 0.40, 0.41) & EXPLANATION TESTS
# ==============================================================================

def test_p1_15_confidence_boundary_0_39_0_40_0_41():
    """
    Test confidence label boundary at exactly 0.40:
    - confidence = 0.39 -> LIMITED
    - confidence = 0.40 -> LIMITED
    - confidence = 0.41 (with N >= 2) -> MODERATE
    - single report is capped at <= 0.40 and strictly receives LIMITED, never MODERATE
    """
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Single report (N=1) capped <= 0.40 receives LIMITED
    single_rep = [{"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": now.isoformat()}]
    est_single = calculate_queue_estimate(single_rep, now=now)
    assert est_single["confidence"] == 0.40
    assert est_single["confidenceLabel"] == "LIMITED"
    assert "Based on a single observation from" in est_single["evidenceExplanation"]
    assert "More reports will improve accuracy." in est_single["evidenceExplanation"]

    # 2. Score = 0.40 with N=2 -> LIMITED
    reports_40 = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=12.5)).isoformat(), "deviceId": "d1"},
        {"reportedWaitMinutes": 25.0, "queueLength": 20, "timestamp": (now - timedelta(minutes=12.5)).isoformat(), "deviceId": "d2"},
    ]
    est_40 = calculate_queue_estimate(reports_40, now=now)
    assert est_40["confidence"] == 0.40
    assert est_40["confidenceLabel"] == "LIMITED"
    assert "Limited evidence based on 2 recent reports" in est_40["evidenceExplanation"]

    # 3. Score = 0.39 with N=2 -> LIMITED
    reports_39 = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=13.2)).isoformat(), "deviceId": "d1"},
        {"reportedWaitMinutes": 25.0, "queueLength": 20, "timestamp": (now - timedelta(minutes=13.2)).isoformat(), "deviceId": "d2"},
    ]
    est_39 = calculate_queue_estimate(reports_39, now=now)
    assert est_39["confidence"] == 0.39
    assert est_39["confidenceLabel"] == "LIMITED"
    assert "Limited evidence based on 2 recent reports" in est_39["evidenceExplanation"]

    # 4. Score = 0.41 with N=2 -> MODERATE
    reports_41 = [
        {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=11.8)).isoformat(), "deviceId": "d1"},
        {"reportedWaitMinutes": 25.0, "queueLength": 20, "timestamp": (now - timedelta(minutes=11.8)).isoformat(), "deviceId": "d2"},
    ]
    est_41 = calculate_queue_estimate(reports_41, now=now)
    assert est_41["confidence"] == 0.41
    assert est_41["confidenceLabel"] == "MODERATE"
    assert "Moderate consensus based on 2 recent reports" in est_41["evidenceExplanation"]


# ==============================================================================
# P1.16 CORRECTION PASS: FAIL-CLOSED OPERATIONAL VERIFICATION STATUS TESTS
# ==============================================================================

def test_p1_16_fail_closed_verification_status_policy():
    """Verify that only recognized verified statuses qualify under fail-closed policy."""
    qualifying_est = {
        "predictedWaitMinutes": 10.0,
        "freshness": "LIVE",
        "recentReportCount": 3,
        "confidence": 0.70,
        "distinctDevicesCount": 2,
        "confidenceLabel": "HIGH",
        "congestion": "MODERATE",
        "newestReportAgeMinutes": 2.0,
    }

    # 1. Recognized verified status -> qualifies
    for v_status in ["VERIFIED", "VERIFIED_CAMPUS_DIRECTORY", "STUDENT_SOURCED", "COMMUNITY_LISTING", "COMMUNITY_DIRECTORY"]:
        locs = [{"id": "loc-1", "name": "Campus Mess", "active": True, "verificationStatus": v_status, "estimate": qualifying_est}]
        rec = compute_smart_recommendation(locs)
        assert rec["isEligible"] is True
        assert rec["recommendedLocationId"] == "loc-1"

    # 2. Explicitly UNVERIFIED -> disqualified
    locs_unverified = [{"id": "loc-2", "name": "Unverified Stall", "active": True, "verificationStatus": "UNVERIFIED", "estimate": qualifying_est}]
    rec_unverified = compute_smart_recommendation(locs_unverified)
    assert rec_unverified["isEligible"] is False

    # 3. Missing verificationStatus (None) -> disqualified
    locs_none = [{"id": "loc-3", "name": "No Status Stall", "active": True, "verificationStatus": None, "estimate": qualifying_est}]
    rec_none = compute_smart_recommendation(locs_none)
    assert rec_none["isEligible"] is False

    # 4. Unknown verificationStatus -> disqualified
    locs_unknown = [{"id": "loc-4", "name": "Unknown Stall", "active": True, "verificationStatus": "RANDOM_STATUS", "estimate": qualifying_est}]
    rec_unknown = compute_smart_recommendation(locs_unknown)
    assert rec_unknown["isEligible"] is False

    # 5. Inactive outlet -> disqualified
    locs_inactive = [{"id": "loc-5", "name": "Inactive Stall", "active": False, "verificationStatus": "STUDENT_SOURCED", "estimate": qualifying_est}]
    rec_inactive = compute_smart_recommendation(locs_inactive)
    assert rec_inactive["isEligible"] is False

    # 6. Verified outlet with higher wait wins against unverified outlet with lower wait
    competing_locs = [
        {
            "id": "unverified-low-wait",
            "name": "Unverified Fast Stall",
            "active": True,
            "verificationStatus": "UNVERIFIED",
            "estimate": {**qualifying_est, "predictedWaitMinutes": 2.0},
        },
        {
            "id": "verified-standard-wait",
            "name": "Verified Reliable Mess",
            "active": True,
            "verificationStatus": "STUDENT_SOURCED",
            "estimate": {**qualifying_est, "predictedWaitMinutes": 12.0},
        },
    ]
    rec_comp = compute_smart_recommendation(competing_locs)
    assert rec_comp["isEligible"] is True
    assert rec_comp["recommendedLocationId"] == "verified-standard-wait"
    assert rec_comp["predictedWaitMinutes"] == 12.0
