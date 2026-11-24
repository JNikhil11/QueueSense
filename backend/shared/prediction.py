"""
QueueSense - Queue Intelligence & Estimation Module
Pure Python implementation with no external framework dependencies.
Provides transparent, deterministic estimation, robust rush-hour outlier handling,
smooth time-decay tapering, dynamic evidence-weighting normalization, and
cold-start recommendation protection.
"""

from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

# Configuration Constants
DEFAULT_DECAY_CONSTANT_MINUTES = 15.0  # Tau in exp(-t / tau); half-life = tau * ln(2) ~= 10.397m
MAX_REPORT_AGE_MINUTES = 60.0          # Reports older than 60m are disregarded
TAPER_START_AGE_MINUTES = 50.0         # Age where smooth cosine decay tapering begins
STALE_THRESHOLD_MINUTES = 20.0         # Age where status transitions from RECENT to STALE
LIVE_THRESHOLD_MINUTES = 7.0           # Age where status transitions from LIVE to RECENT

# Congestion Thresholds (Wait time in minutes)
CONGESTION_THRESHOLDS = {
    "LOW": (0.0, 3.5),
    "MODERATE": (3.5, 8.5),
    "HIGH": (8.5, 15.5),
    "VERY_HIGH": (15.5, float("inf")),
}

# Outlier bounds (Reported wait time and queue physical plausibility limits)
MIN_PLAUSIBLE_WAIT_MINUTES = 0.0
MAX_PLAUSIBLE_WAIT_MINUTES = 120.0
MIN_PLAUSIBLE_QUEUE_LENGTH = 0
MAX_PLAUSIBLE_QUEUE_LENGTH = 300

# MAD Outlier Tuning Constants
MAD_MIN_SCALE_MINUTES = 5.0            # Prevents division by zero or zero-deviation collapse
MAD_CUTOFF_MULTIPLIER = 3.5            # Multiplier on scale for candidate deviation
MAD_MIN_CUTOFF_MINUTES = 25.0          # Minimum deviation threshold before considering an outlier
SURGE_CORROBORATION_MIN_COUNT = 2      # Minimum concurrent reports to corroborate a surge
SURGE_CORROBORATION_WINDOW_MIN = 30.0  # Time window (minutes) to consider reports mutually corroborating
SURGE_CONSISTENCY_DELTA_MIN = 20.0     # Maximum delta between corroborating surge reports

# Recognized verified location statuses (Fail-Closed Recommendation Policy)
VERIFIED_LOCATION_STATUSES = {
    "VERIFIED",
    "VERIFIED_CAMPUS_DIRECTORY",
    "STUDENT_SOURCED",
    "COMMUNITY_LISTING",
    "COMMUNITY_DIRECTORY",
}


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 string into a timezone-aware UTC datetime."""
    clean_str = ts_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calculate_freshness_weight(
    report_time: datetime,
    now: datetime,
    tau: float = DEFAULT_DECAY_CONSTANT_MINUTES,
    max_age: float = MAX_REPORT_AGE_MINUTES,
    taper_start: float = TAPER_START_AGE_MINUTES,
) -> float:
    """
    Calculate time-decay freshness weight with smooth tapering:
    - Base weight: w_base = exp(-age / tau).
    - Half-life: t_1/2 = tau * ln(2) (~10.397 min for tau=15.0).
    - Future timestamps (> 30s ahead) are rejected (return 0.0).
    - Minor clock jitter (-30s <= age < 0s) is clamped to age 0.0.
    - Smooth cosine tapering between taper_start (50m) and max_age (60m)
      eliminates the step discontinuity at the 60-minute cutoff:
      T(age) = 0.5 * (1.0 + cos(pi * (age - 50) / 10)) for 50 <= age <= 60.
    - Reports older than max_age return 0.0.
    """
    age_seconds = (now - report_time).total_seconds()
    age_minutes = age_seconds / 60.0

    if age_minutes < 0:
        # Reject future reports exceeding clock-skew tolerance (> 30 seconds ahead)
        if age_minutes < -0.5:
            return 0.0
        age_minutes = 0.0

    if age_minutes > max_age:
        return 0.0

    base_weight = math.exp(-age_minutes / tau)

    # Smooth cosine tapering between taper_start and max_age
    if age_minutes > taper_start:
        taper_fraction = (age_minutes - taper_start) / (max_age - taper_start)
        taper_weight = 0.5 * (1.0 + math.cos(math.pi * taper_fraction))
        return base_weight * taper_weight

    return base_weight


def classify_congestion(wait_minutes: float) -> str:
    """Classify waiting time into LOW, MODERATE, HIGH, or VERY_HIGH."""
    if wait_minutes < 0:
        return "UNKNOWN"
    for level, (low, high) in CONGESTION_THRESHOLDS.items():
        if low <= wait_minutes < high:
            return level
    return "VERY_HIGH"


def determine_freshness_status(newest_age_minutes: Optional[float]) -> str:
    """
    Categorize data freshness based on newest observation:
    - LIVE: <= 7 mins ago
    - RECENT: <= 20 mins ago
    - STALE: <= 60 mins ago
    - NO RECENT DATA: > 60 mins or no reports
    """
    if newest_age_minutes is None:
        return "NO RECENT DATA"
    if newest_age_minutes <= LIVE_THRESHOLD_MINUTES:
        return "LIVE"
    if newest_age_minutes <= STALE_THRESHOLD_MINUTES:
        return "RECENT"
    if newest_age_minutes <= MAX_REPORT_AGE_MINUTES:
        return "STALE"
    return "NO RECENT DATA"


def extract_report_timestamp(report: Dict[str, Any]) -> Optional[datetime]:
    """Safely extract and parse an ISO 8601 timestamp from a report dictionary."""
    raw_ts = report.get("timestamp")
    if not raw_ts:
        return None
    try:
        return parse_iso_timestamp(str(raw_ts))
    except (ValueError, TypeError):
        return None


def filter_outliers(
    reports: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Robust outlier filtering with Corroborated Surge Detection:
    1. Physical Bounds Filtering:
       Checks 0 <= reportedWaitMinutes <= 120 and 0 <= queueLength <= 300.
       Rejects non-numeric, NaN, Infinity, or negative inputs.
    2. Small Sample Sizes (N < 5 plausible):
       Preserves all plausible reports. Small samples lack statistical power
       to reliably compute MAD without high false-positive rejection.
    3. Large Sample Sizes (N >= 5 plausible):
       Computes median wait time and Median Absolute Deviation (MAD).
       Enforces minimum scale (>= 5.0m) and rush-tolerant cutoff (>= 25.0m deviation).
       Corroborated Surge Detection:
       Candidate deviations (wait > median + cutoff) represent a genuine surge ONLY IF
       corroborated by at least one other eligible peer report within SURGE_CORROBORATION_WINDOW_MIN
       (30 minutes) from a distinct client device identifier (where available) with value
       consistency (delta <= 20 minutes).
       Reports with missing or unparseable timestamps cannot establish timing and cannot
       corroborate surges. Elevated queue count alone does NOT substitute for peer corroboration.
       Uncorroborated isolated extreme spikes/drops are isolated and excluded.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    valid: List[Dict[str, Any]] = []
    outliers: List[Dict[str, Any]] = []

    # First pass: Physical plausibility & numerical integrity
    plausible: List[Dict[str, Any]] = []
    for r in reports:
        raw_wait = r.get("reportedWaitMinutes")
        raw_queue = r.get("queueLength", 0)

        # Numerical type and finiteness check
        if raw_wait is None or isinstance(raw_wait, bool) or not isinstance(raw_wait, (int, float)):
            outliers.append({**r, "outlierReason": "NON_NUMERIC_WAIT_TIME"})
            continue
        if raw_queue is None or isinstance(raw_queue, bool) or not isinstance(raw_queue, (int, float)):
            outliers.append({**r, "outlierReason": "NON_NUMERIC_QUEUE_LENGTH"})
            continue

        wait = float(raw_wait)
        queue = float(raw_queue)

        if math.isnan(wait) or math.isinf(wait):
            outliers.append({**r, "outlierReason": "INVALID_FLOAT_WAIT_TIME"})
            continue
        if math.isnan(queue) or math.isinf(queue):
            outliers.append({**r, "outlierReason": "INVALID_FLOAT_QUEUE_LENGTH"})
            continue

        if (
            MIN_PLAUSIBLE_WAIT_MINUTES <= wait <= MAX_PLAUSIBLE_WAIT_MINUTES
            and MIN_PLAUSIBLE_QUEUE_LENGTH <= queue <= MAX_PLAUSIBLE_QUEUE_LENGTH
        ):
            plausible.append(r)
        else:
            outliers.append({**r, "outlierReason": "PHYSICAL_BOUNDS_VIOLATION"})

    # For sample sizes under 5, do not discard plausible rush-hour observations.
    if len(plausible) < 5:
        return plausible, outliers

    # Compute median of reported wait minutes
    waits = sorted([float(r["reportedWaitMinutes"]) for r in plausible])
    n = len(waits)
    median_wait = waits[n // 2] if n % 2 != 0 else (waits[n // 2 - 1] + waits[n // 2]) / 2.0

    # Calculate MAD (Median Absolute Deviation)
    abs_deviations = sorted([abs(w - median_wait) for w in waits])
    mad = (
        abs_deviations[n // 2]
        if n % 2 != 0
        else (abs_deviations[n // 2 - 1] + abs_deviations[n // 2]) / 2.0
    )

    # Campus dining queues experience rapid meal-hour spikes.
    # Base cutoff combines 3.5 * MAD with a safe minimum 25.0 minutes deviation
    cutoff = max(MAD_CUTOFF_MULTIPLIER * mad, MAD_MIN_CUTOFF_MINUTES)

    # Identify candidate spikes and candidate drops
    candidate_spikes: List[Dict[str, Any]] = []
    candidate_drops: List[Dict[str, Any]] = []
    normal_reports: List[Dict[str, Any]] = []

    for r in plausible:
        wait = float(r["reportedWaitMinutes"])
        if (wait - median_wait) > cutoff:
            candidate_spikes.append(r)
        elif (median_wait - wait) > cutoff:
            candidate_drops.append(r)
        else:
            normal_reports.append(r)

    # Evaluate candidate spikes with strict temporal and observer Corroborated Surge Detection
    corroborated_spikes: List[Dict[str, Any]] = []
    for r in candidate_spikes:
        wait = float(r["reportedWaitMinutes"])
        ts_r = extract_report_timestamp(r)
        dev_r = r.get("deviceId") or r.get("clientHash") or r.get("reporterId")

        # If timing cannot be established, report cannot be corroborated as concurrent
        if ts_r is None:
            outliers.append({**r, "outlierReason": "UNCORROBORATED_MISSING_TIMESTAMP"})
            continue

        is_corroborated_by_peers = False
        peer_matches = 0

        for peer in candidate_spikes:
            if peer is r:
                continue

            ts_peer = extract_report_timestamp(peer)
            if ts_peer is None:
                continue

            # Check 1: Temporal proximity within SURGE_CORROBORATION_WINDOW_MIN (30.0 min)
            time_delta_min = abs((ts_r - ts_peer).total_seconds()) / 60.0
            if time_delta_min > SURGE_CORROBORATION_WINDOW_MIN:
                continue

            # Check 2: Distinct client device identifiers if available
            dev_peer = peer.get("deviceId") or peer.get("clientHash") or peer.get("reporterId")
            if dev_r and dev_peer and dev_r == dev_peer:
                # Same client identifier cannot establish peer consensus
                continue

            # Check 3: Value consistency within SURGE_CONSISTENCY_DELTA_MIN (20.0 min)
            peer_wait = float(peer["reportedWaitMinutes"])
            if abs(wait - peer_wait) <= SURGE_CONSISTENCY_DELTA_MIN:
                peer_matches += 1

        if peer_matches >= 1:
            corroborated_spikes.append(r)
        else:
            outliers.append({**r, "outlierReason": "UNCORROBORATED_ISOLATED_SPIKE"})

    # Evaluate candidate drops with strict temporal and observer corroboration
    corroborated_drops: List[Dict[str, Any]] = []
    for r in candidate_drops:
        wait = float(r["reportedWaitMinutes"])
        ts_r = extract_report_timestamp(r)
        dev_r = r.get("deviceId") or r.get("clientHash") or r.get("reporterId")

        if ts_r is None:
            outliers.append({**r, "outlierReason": "UNCORROBORATED_MISSING_TIMESTAMP"})
            continue

        peer_matches = 0
        for peer in candidate_drops:
            if peer is r:
                continue

            ts_peer = extract_report_timestamp(peer)
            if ts_peer is None:
                continue

            time_delta_min = abs((ts_r - ts_peer).total_seconds()) / 60.0
            if time_delta_min > SURGE_CORROBORATION_WINDOW_MIN:
                continue

            dev_peer = peer.get("deviceId") or peer.get("clientHash") or peer.get("reporterId")
            if dev_r and dev_peer and dev_r == dev_peer:
                continue

            peer_wait = float(peer["reportedWaitMinutes"])
            if abs(wait - peer_wait) <= SURGE_CONSISTENCY_DELTA_MIN:
                peer_matches += 1

        if peer_matches >= 1:
            corroborated_drops.append(r)
        else:
            outliers.append({**r, "outlierReason": "UNCORROBORATED_ISOLATED_DROP"})

    valid = normal_reports + corroborated_spikes + corroborated_drops
    return valid, outliers


def calculate_queue_estimate(
    reports: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    tau: float = DEFAULT_DECAY_CONSTANT_MINUTES,
) -> Dict[str, Any]:
    """
    Core estimation function:
    Computes time-decay weighted wait time and queue length,
    freshness state, heuristic confidence score, and independent evidence tracking.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Filter out malformed & extreme outliers
    valid_reports, outliers = filter_outliers(reports, now=now)

    if not valid_reports:
        return {
            "predictedWaitMinutes": None,
            "predictedQueueLength": None,
            "congestion": "UNKNOWN",
            "confidence": 0.0,
            "confidenceLabel": "NO DATA",
            "confidenceScoreType": "HEURISTIC_COMPOSITE",
            "freshness": "NO RECENT DATA",
            "reportCount": 0,
            "recentReportCount": 0,
            "distinctDevicesCount": 0,
            "newestReportAgeMinutes": None,
            "newestReportTimestamp": None,
            "disagreementMinutes": 0.0,
            "outliersExcluded": len(outliers),
            "evidenceExplanation": "No recent observations recorded for this outlet.",
            "updatedAt": now.isoformat(),
        }

    # Calculate weights and ages
    weighted_wait_sum = 0.0
    weighted_queue_sum = 0.0
    total_weight = 0.0
    newest_age_minutes: Optional[float] = None
    newest_timestamp: Optional[str] = None
    recent_reports: List[Dict[str, Any]] = []
    observed_devices: set = set()
    distinct_timestamps: List[datetime] = []

    for r in valid_reports:
        raw_ts = r.get("timestamp")
        if not raw_ts:
            continue
        try:
            ts = parse_iso_timestamp(str(raw_ts))
        except (ValueError, TypeError):
            continue

        age_seconds = (now - ts).total_seconds()
        age_min = age_seconds / 60.0

        # Reject future reports beyond clock skew tolerance
        if age_min < -0.5:
            continue
        age_min = max(0.0, age_min)

        if newest_age_minutes is None or age_min < newest_age_minutes:
            newest_age_minutes = age_min
            newest_timestamp = ts.isoformat()

        if age_min <= MAX_REPORT_AGE_MINUTES:
            weight = calculate_freshness_weight(ts, now, tau=tau)
            if weight > 0.0001:
                wait_val = float(r["reportedWaitMinutes"])
                queue_val = float(r.get("queueLength", 0))
                weighted_wait_sum += weight * wait_val
                weighted_queue_sum += weight * queue_val
                total_weight += weight
                recent_reports.append(r)

                # Track distinct device / client identity
                dev_id = r.get("deviceId") or r.get("clientHash") or r.get("reporterId")
                if dev_id:
                    observed_devices.add(str(dev_id))
                distinct_timestamps.append(ts)

    if total_weight < 0.001 or not recent_reports:
        return {
            "predictedWaitMinutes": None,
            "predictedQueueLength": None,
            "congestion": "UNKNOWN",
            "confidence": 0.0,
            "confidenceLabel": "NO RECENT DATA",
            "confidenceScoreType": "HEURISTIC_COMPOSITE",
            "freshness": "NO RECENT DATA",
            "reportCount": len(reports),
            "recentReportCount": 0,
            "distinctDevicesCount": 0,
            "newestReportAgeMinutes": newest_age_minutes,
            "newestReportTimestamp": newest_timestamp,
            "disagreementMinutes": 0.0,
            "outliersExcluded": len(outliers),
            "evidenceExplanation": "Past reports are over 60 minutes old and no longer reflect current conditions.",
            "updatedAt": now.isoformat(),
        }

    # Evaluate distinct devices count
    if observed_devices:
        distinct_devices_count = len(observed_devices)
    else:
        # Fallback for anonymous / legacy reports without device IDs:
        # Measure distinct submissions separated by at least 3 minutes
        sorted_ts = sorted(distinct_timestamps)
        independent_bursts = 0
        last_counted_ts: Optional[datetime] = None
        for cur_ts in sorted_ts:
            if last_counted_ts is None or (cur_ts - last_counted_ts).total_seconds() >= 180.0:
                independent_bursts += 1
                last_counted_ts = cur_ts
        distinct_devices_count = max(1, independent_bursts)

    # Final weighted estimates
    estimated_wait = round(weighted_wait_sum / total_weight, 1)
    estimated_queue = int(round(weighted_queue_sum / total_weight))
    congestion = classify_congestion(estimated_wait)
    freshness = determine_freshness_status(newest_age_minutes)

    # Measure disagreement between recent reports
    if len(recent_reports) > 1:
        waits = [float(r["reportedWaitMinutes"]) for r in recent_reports]
        disagreement = round(max(waits) - min(waits), 1)
    else:
        disagreement = 0.0

    # Calculate Confidence Score (0.0 to 1.0) via Dynamic Renormalization (P1.15)
    # Factor 1: Volume of reports (base weight: 0.45, saturates at 4 reports)
    volume_raw = min(len(recent_reports) / 4.0, 1.0)
    # Factor 2: Recency of newest report (base weight: 0.35, decays over 25m)
    recency_raw = max(0.0, 1.0 - (newest_age_minutes or 0.0) / 25.0)

    if len(recent_reports) > 1:
        # Factor 3: Agreement (base weight: 0.20, disagreement <= 3m gives full score)
        agreement_raw = max(0.0, 1.0 - (disagreement / 15.0))
        # Full model: 45% volume + 35% recency + 20% agreement = 100%
        confidence = round(
            min(1.0, 0.45 * volume_raw + 0.35 * recency_raw + 0.20 * agreement_raw),
            2,
        )
    else:
        # Dynamic renormalization when agreement cannot be evaluated (N=1)
        # Active weights: w_vol = 0.45 / 0.80 = 0.5625, w_rec = 0.35 / 0.80 = 0.4375
        renormalized_score = (0.45 * volume_raw + 0.35 * recency_raw) / 0.80
        # Epistemic single-source uncertainty cap: a single report carries higher variance
        confidence = round(min(0.40, renormalized_score * 0.70), 2)

    # Qualitative label (P1.15)
    # Strictly > 0.40 with at least 2 reports receives MODERATE.
    # Scores <= 0.40 receive LIMITED. Single-report confidence is capped <= 0.40 and receives LIMITED.
    if confidence >= 0.70:
        confidence_label = "HIGH"
    elif confidence > 0.40 and len(recent_reports) >= 2:
        confidence_label = "MODERATE"
    elif confidence >= 0.20:
        confidence_label = "LIMITED"
    else:
        confidence_label = "VERY LOW"

    # Human-readable explanation
    count_str = f"{len(recent_reports)} recent report" if len(recent_reports) == 1 else f"{len(recent_reports)} recent reports"
    age_str = f"{int(round(newest_age_minutes or 0))}m ago" if (newest_age_minutes or 0) >= 1 else "just now"

    if confidence_label == "HIGH":
        explanation = f"Strong agreement across {count_str}; latest report from {age_str}."
    elif confidence_label == "MODERATE":
        explanation = f"Moderate consensus based on {count_str}; updated {age_str}."
    elif confidence_label == "LIMITED":
        if len(recent_reports) == 1:
            explanation = f"Based on a single observation from {age_str}. More reports will improve accuracy."
        else:
            explanation = f"Limited evidence based on {count_str}; updated {age_str}."
    else:
        explanation = f"Observations are aging ({age_str}); estimate may not reflect sudden rushes."

    return {
        "predictedWaitMinutes": estimated_wait,
        "predictedQueueLength": estimated_queue,
        "congestion": congestion,
        "confidence": confidence,
        "confidenceLabel": confidence_label,
        "confidenceScoreType": "HEURISTIC_COMPOSITE",
        "freshness": freshness,
        "reportCount": len(reports),
        "recentReportCount": len(recent_reports),
        "distinctDevicesCount": distinct_devices_count,
        "newestReportAgeMinutes": round(newest_age_minutes, 1) if newest_age_minutes is not None else None,
        "newestReportTimestamp": newest_timestamp,
        "disagreementMinutes": disagreement,
        "outliersExcluded": len(outliers),
        "evidenceExplanation": explanation,
        "updatedAt": now.isoformat(),
    }


def compute_smart_recommendation(
    locations_with_estimates: List[Dict[str, Any]],
    min_reports: int = 3,
    min_confidence: float = 0.50,
    min_distinct_devices: int = 2,
) -> Dict[str, Any]:
    """
    Defensible recommendation engine (P1.16):
    Recommends the active outlet with the shortest credible wait time.
    Cold-Start Protection & Operational Safeguards:
    1. Operational verification: Must be an active location and not unverified.
    2. Freshness: Requires observations within the last 20 minutes (LIVE or RECENT).
    3. Volume threshold: Requires at least min_reports (default: 3) fresh observations.
    4. Confidence threshold: Requires confidence >= min_confidence (default: 0.50).
    5. Independent evidence: Requires observations from at least min_distinct_devices (default: 2)
       distinct client devices or independent observation bursts.
    Fail-Safe States:
    - "recommended": Qualified recommendation found.
    - "insufficient_data": Fresh data exists but thresholds not met.
    - "stale_data": All campus observations are stale (> 20m old).
    - "no_active_outlets": No candidate locations are active.
    """
    eligible: List[Dict[str, Any]] = []
    has_active_locations = False
    has_fresh_reports = False

    for loc in locations_with_estimates:
        # Check active status
        if not loc.get("active", True):
            continue
        has_active_locations = True

        # Check operational verification status (Fail-Closed Policy P1.16)
        # Only recognized verified statuses qualify. Missing, None, empty, or unknown strings are disqualified.
        v_status = loc.get("verificationStatus")
        if not v_status or not isinstance(v_status, str) or v_status not in VERIFIED_LOCATION_STATUSES:
            continue

        est = loc.get("estimate", {})
        freshness = est.get("freshness", "NO RECENT DATA")
        confidence = est.get("confidence", 0.0)
        predicted_wait = est.get("predictedWaitMinutes")
        recent_count = est.get("recentReportCount", 0)
        distinct_devices = est.get("distinctDevicesCount", recent_count)

        if freshness in ("LIVE", "RECENT"):
            has_fresh_reports = True

        # Check all qualification criteria
        if (
            predicted_wait is not None
            and freshness in ("LIVE", "RECENT")
            and recent_count >= min_reports
            and confidence >= min_confidence
            and distinct_devices >= min_distinct_devices
        ):
            eligible.append(loc)

    if not eligible:
        if not has_active_locations:
            state = "no_active_outlets"
            reason = "No campus food outlets are currently open or active."
        elif not has_fresh_reports:
            state = "stale_data"
            reason = (
                "Not enough recent queue reports across campus to make a reliable recommendation yet. "
                "All campus queue observations are over 20 minutes old and considered stale. "
                "Fresh student reports are needed before making a recommendation."
            )
        else:
            state = "insufficient_data"
            reason = (
                f"Not enough recent queue reports across campus to make a reliable recommendation yet. "
                f"At least {min_reports} fresh observations (within 20 minutes), {int(min_confidence * 100)}%+ "
                f"confidence, and corroboration from multiple distinct client devices are required."
            )

        return {
            "recommendedLocationId": None,
            "recommendedLocationName": None,
            "predictedWaitMinutes": None,
            "congestion": "UNKNOWN",
            "confidence": 0.0,
            "confidenceLabel": "INSUFFICIENT DATA",
            "reason": reason,
            "isEligible": False,
            "state": state,
            "minReportsRequired": min_reports,
            "minConfidenceRequired": min_confidence,
            "candidateCount": len(locations_with_estimates),
            "eligibleCount": 0,
        }

    # Sort eligible by predicted wait minutes (ascending), then by confidence (descending)
    eligible.sort(
        key=lambda x: (
            x["estimate"]["predictedWaitMinutes"],
            -x["estimate"]["confidence"],
        )
    )

    winner = eligible[0]
    w_est = winner["estimate"]
    w_wait = w_est["predictedWaitMinutes"]
    w_reports = w_est["recentReportCount"]
    w_age = w_est["newestReportAgeMinutes"]

    age_text = f"{int(round(w_age))}m ago" if w_age and w_age >= 1 else "just now"
    reason = (
        f"Shortest estimated wait (~{w_wait} min) with {w_est['confidenceLabel'].lower()} evidence; "
        f"verified by {w_reports} fresh reports updated {age_text}."
    )

    return {
        "recommendedLocationId": winner["id"],
        "recommendedLocationName": winner["name"],
        "predictedWaitMinutes": w_wait,
        "congestion": w_est["congestion"],
        "confidence": w_est["confidence"],
        "confidenceLabel": w_est["confidenceLabel"],
        "reason": reason,
        "isEligible": True,
        "state": "recommended",
        "candidateCount": len(locations_with_estimates),
        "eligibleCount": len(eligible),
    }
