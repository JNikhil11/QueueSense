"""
QueueSense - Queue Intelligence & Estimation Module
Pure Python implementation with no external framework dependencies.
Provides transparent, deterministic estimation, outlier handling, freshness decay,
and evidence confidence scoring.
"""

from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

# Configuration Constants
DEFAULT_DECAY_CONSTANT_MINUTES = 15.0  # Tau in exp(-t / tau)
MAX_REPORT_AGE_MINUTES = 60.0          # Reports older than 60m are disregarded
STALE_THRESHOLD_MINUTES = 20.0         # Age where status transitions to STALE
LIVE_THRESHOLD_MINUTES = 7.0           # Age where status transitions from LIVE to RECENT

# Congestion Thresholds (Wait time in minutes)
CONGESTION_THRESHOLDS = {
    "LOW": (0, 3.5),
    "MODERATE": (3.5, 8.5),
    "HIGH": (8.5, 15.5),
    "VERY_HIGH": (15.5, float("inf")),
}

# Outlier bounds (Reported wait time limits)
MIN_PLAUSIBLE_WAIT_MINUTES = 0
MAX_PLAUSIBLE_WAIT_MINUTES = 120
MIN_PLAUSIBLE_QUEUE_LENGTH = 0
MAX_PLAUSIBLE_QUEUE_LENGTH = 300


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse ISO 8601 string into a timezone-aware UTC datetime."""
    # Handle 'Z' suffix or standard offsets
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
) -> float:
    """
    Calculate exponential freshness weight: w = exp(-age / tau).
    Returns 0.0 if report age exceeds max_age or is in the future.
    """
    age_seconds = (now - report_time).total_seconds()
    age_minutes = age_seconds / 60.0

    if age_minutes < 0:
        # Future report protection: treat as age 0 or ignore if clock skew > 5m
        if age_minutes < -5.0:
            return 0.0
        age_minutes = 0.0

    if age_minutes > max_age:
        return 0.0

    return math.exp(-age_minutes / tau)


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


def filter_outliers(
    reports: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Separate valid reports from outliers.
    For small sample sizes (N < 5), preserve all reports within physical bounds
    and operational rush limits. A 20-minute wait during lunch rush is physically
    valid and must not be rejected merely because earlier reports were 5 minutes.
    For larger sample sizes (N >= 5), use Median Absolute Deviation (MAD) with
    rush-tolerant deviation bounds (min deviation threshold >= 25.0 minutes).
    """
    valid: List[Dict[str, Any]] = []
    outliers: List[Dict[str, Any]] = []

    # First pass: basic plausibility boundaries (0-120 min wait, 0-300 queue)
    plausible: List[Dict[str, Any]] = []
    for r in reports:
        wait = float(r.get("reportedWaitMinutes", 0))
        queue = float(r.get("queueLength", 0))
        if (
            MIN_PLAUSIBLE_WAIT_MINUTES <= wait <= MAX_PLAUSIBLE_WAIT_MINUTES
            and MIN_PLAUSIBLE_QUEUE_LENGTH <= queue <= MAX_PLAUSIBLE_QUEUE_LENGTH
        ):
            plausible.append(r)
        else:
            outliers.append(r)

    # For sample sizes under 5, do not discard plausible rush-hour observations.
    # Meal rush transitions (e.g. from 5 mins to 20 mins) are common in campus dining.
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

    # Campus dining waits experience rapid meal-hour spikes.
    # Use rush-tolerant cutoff: effective threshold is at least 25.0 minutes deviation.
    cutoff = max(3.5 * mad, 25.0)

    for r in plausible:
        wait = float(r["reportedWaitMinutes"])
        if abs(wait - median_wait) > cutoff:
            outliers.append(r)
        else:
            valid.append(r)

    return valid, outliers


def calculate_queue_estimate(
    reports: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    tau: float = DEFAULT_DECAY_CONSTANT_MINUTES,
) -> Dict[str, Any]:
    """
    Core estimation function:
    Computes time-decay weighted wait time and queue length,
    freshness state, confidence level, and evidence summary.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Filter out malformed & extreme outliers
    valid_reports, outliers = filter_outliers(reports)

    if not valid_reports:
        return {
            "predictedWaitMinutes": None,
            "predictedQueueLength": None,
            "congestion": "UNKNOWN",
            "confidence": 0.0,
            "confidenceLabel": "NO DATA",
            "freshness": "NO RECENT DATA",
            "reportCount": 0,
            "recentReportCount": 0,
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

    for r in valid_reports:
        ts = parse_iso_timestamp(str(r["timestamp"]))
        age_min = max(0.0, (now - ts).total_seconds() / 60.0)

        if newest_age_minutes is None or age_min < newest_age_minutes:
            newest_age_minutes = age_min
            newest_timestamp = ts.isoformat()

        if age_min <= MAX_REPORT_AGE_MINUTES:
            weight = calculate_freshness_weight(ts, now, tau=tau)
            if weight > 0.001:
                wait_val = float(r["reportedWaitMinutes"])
                queue_val = float(r.get("queueLength", 0))
                weighted_wait_sum += weight * wait_val
                weighted_queue_sum += weight * queue_val
                total_weight += weight
                recent_reports.append(r)

    if total_weight < 0.01 or not recent_reports:
        return {
            "predictedWaitMinutes": None,
            "predictedQueueLength": None,
            "congestion": "UNKNOWN",
            "confidence": 0.0,
            "confidenceLabel": "NO RECENT DATA",
            "freshness": "NO RECENT DATA",
            "reportCount": len(reports),
            "recentReportCount": 0,
            "newestReportAgeMinutes": newest_age_minutes,
            "newestReportTimestamp": newest_timestamp,
            "disagreementMinutes": 0.0,
            "outliersExcluded": len(outliers),
            "evidenceExplanation": "Past reports are over 60 minutes old and no longer reflect current conditions.",
            "updatedAt": now.isoformat(),
        }

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

    # Calculate Confidence Score (0.0 to 1.0)
    # Factor 1: Volume of reports (up to 4 reports gives 0.45)
    volume_score = min(len(recent_reports) / 4.0, 1.0) * 0.45

    # Factor 2: Recency of newest report (within 5m gives 0.35, decaying)
    recency_factor = max(0.0, 1.0 - (newest_age_minutes or 0.0) / 25.0) * 0.35

    # Factor 3: Agreement (disagreement <= 3 mins gives 0.20, penalized if wide)
    if len(recent_reports) > 1:
        agreement_factor = max(0.0, 1.0 - (disagreement / 15.0)) * 0.20
    else:
        # Single report: cannot measure agreement, neutral weight
        agreement_factor = 0.08

    confidence = round(min(1.0, volume_score + recency_factor + agreement_factor), 2)

    # Qualitative label
    if confidence >= 0.70:
        confidence_label = "HIGH"
    elif confidence >= 0.40:
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
        explanation = f"Solid estimate based on {count_str}; updated {age_str}."
    elif confidence_label == "LIMITED":
        explanation = f"Based on a single observation from {age_str}. More reports will improve accuracy."
    else:
        explanation = f"Observations are aging ({age_str}); estimate may not reflect sudden rushes."

    return {
        "predictedWaitMinutes": estimated_wait,
        "predictedQueueLength": estimated_queue,
        "congestion": congestion,
        "confidence": confidence,
        "confidenceLabel": confidence_label,
        "freshness": freshness,
        "reportCount": len(reports),
        "recentReportCount": len(recent_reports),
        "newestReportAgeMinutes": round(newest_age_minutes, 1) if newest_age_minutes is not None else None,
        "newestReportTimestamp": newest_timestamp,
        "disagreementMinutes": disagreement,
        "outliersExcluded": len(outliers),
        "evidenceExplanation": explanation,
        "updatedAt": now.isoformat(),
    }


def compute_smart_recommendation(
    locations_with_estimates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Defensible recommendation engine:
    Recommends the outlet with the shortest credible wait time.
    Disqualifies outlets with STALE, NO RECENT DATA, or VERY LOW confidence.
    Explains the exact reasoning in plain language.
    """
    eligible: List[Dict[str, Any]] = []

    for loc in locations_with_estimates:
        est = loc.get("estimate", {})
        freshness = est.get("freshness", "NO RECENT DATA")
        confidence = est.get("confidence", 0.0)
        predicted_wait = est.get("predictedWaitMinutes")

        # Must be an active location
        if not loc.get("active", True):
            continue

        # Must have fresh or recent data, valid wait time, and non-negligible confidence
        if (
            predicted_wait is not None
            and freshness in ("LIVE", "RECENT")
            and confidence >= 0.25
        ):
            eligible.append(loc)

    if not eligible:
        return {
            "recommendedLocationId": None,
            "recommendedLocationName": None,
            "reason": "Not enough recent queue reports across campus to make a reliable recommendation yet.",
            "isEligible": False,
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
        f"verified by {w_reports} report{'s' if w_reports != 1 else ''} updated {age_text}."
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
        "candidateCount": len(locations_with_estimates),
        "eligibleCount": len(eligible),
    }

