# QueueSense --- API Specification

**Base URL (Live AWS Deployment):** `https://{api-id}.execute-api.ap-southeast-2.amazonaws.com`  
**Protocol:** HTTPS  
**Content-Type:** `application/json`  

---

## 1. Endpoints Overview

| Method | Endpoint | Description | Auth |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service health status & timestamp | Public |
| `GET` | `/locations` | List all campus food outlets with current queue estimates | Public |
| `GET` | `/locations/{id}` | Retrieve specific outlet details | Public |
| `GET` | `/locations/{id}/queue` | Get real-time queue estimate and recent report timeline | Public |
| `GET` | `/locations/{id}/historical` | Aggregated 24-hour wait time and queue patterns | Public |
| `POST` | `/locations/{id}/reports` | Submit a crowdsourced queue observation | Rate-Limited |
| `GET` | `/recommendations` | Get campus-wide smart outlet recommendation | Public |
| `GET` | `/admin/reports` | Campus-wide audit log of observations | Protected (`Bearer` / `X-Admin-Key`) |

---

## 2. Endpoint Details

### 2.1 `GET /health`
Returns system status, active AWS region, and API version.

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "service": "QueueSense-API",
    "region": "ap-southeast-2",
    "timestamp": "2026-11-23T12:00:00.000000+00:00",
    "version": "1.0.0"
  }
}
```

---

### 2.2 `GET /locations`
Retrieves all configured dining halls and food courts with embedded real-time queue estimates.

**Response (200 OK):**
```json
{
  "success": true,
  "data": [
    {
      "id": "mess-a-central",
      "name": "Central Mess A (North Dining)",
      "category": "MESS",
      "description": "Primary multi-story student dining hall...",
      "openHours": "07:30 - 21:30",
      "capacity": 450,
      "active": true,
      "estimate": {
        "predictedWaitMinutes": 12.5,
        "predictedQueueLength": 18,
        "congestion": "HIGH",
        "confidence": 0.78,
        "confidenceLabel": "HIGH",
        "freshness": "LIVE",
        "reportCount": 4,
        "recentReportCount": 3,
        "newestReportAgeMinutes": 3.2,
        "newestReportTimestamp": "2026-11-23T12:26:48+00:00",
        "disagreementMinutes": 2.5,
        "outliersExcluded": 0,
        "evidenceExplanation": "Strong agreement across 3 recent reports; latest report from 3m ago.",
        "updatedAt": "2026-11-23T12:30:00+00:00"
      }
    }
  ]
}
```

---

### 2.3 `POST /locations/{id}/reports`
Submits a student queue observation. The server validates bounds, generates unique ID and timestamp, recomputes the estimate, and updates DynamoDB.

**Request Body:**
```json
{
  "reportedWaitMinutes": 8.0,
  "queueLength": 14,
  "note": "Counters 1 and 2 open, moving fast"
}
```

**Field Rules:**
- `reportedWaitMinutes`: Number, required, `0 <= value <= 120`
- `queueLength`: Integer, optional (default 0), `0 <= value <= 300`
- `note`: String, optional, max 140 chars, sanitized against XSS.

**Response (201 Created):**
```json
{
  "success": true,
  "data": {
    "message": "Queue observation successfully recorded.",
    "report": {
      "reportId": "rep_9f81a7b3c2e1",
      "locationId": "mess-a-central",
      "reportedWaitMinutes": 8.0,
      "queueLength": 14,
      "note": "Counters 1 and 2 open, moving fast",
      "timestamp": "2026-11-23T12:35:10+00:00"
    },
    "updatedEstimate": {
      "predictedWaitMinutes": 8.5,
      "predictedQueueLength": 15,
      "congestion": "MODERATE",
      "confidence": 0.82,
      "confidenceLabel": "HIGH",
      "freshness": "LIVE"
    }
  }
}
```

---

### 2.5 `GET /locations/{id}/historical`
Retrieves aggregated 24-hour queue patterns synthesized from past student observations over the last 14 days. Identifies peak rush and best time to go during operating hours (08:00 - 22:00).

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "locationId": "iitb-mess-h12-14",
    "locationName": "Hostel 12-13-14 Dining Complex",
    "status": "available",
    "totalObservations": 42,
    "hourlyTrends": [
      {
        "hour": 13,
        "label": "13:00",
        "averageWaitMinutes": 16.5,
        "averageQueueLength": 24.0,
        "observationCount": 8
      }
    ],
    "busiestHour": {
      "hour": 20,
      "label": "20:00",
      "averageWaitMinutes": 18.2
    },
    "quietestHour": {
      "hour": 16,
      "label": "16:00",
      "averageWaitMinutes": 3.5
    },
    "summary": "Historical curve synthesized from 42 verified student reports over the past 14 days."
  }
}
```

---

## 3. Standardized Error Handling

All error responses return clean JSON payloads without leaking raw internal exception stack traces:

```json
{
  "success": false,
  "error": "Submission rate limit reached. Please wait a few minutes before reporting again.",
  "errorCode": "RATE_LIMIT_EXCEEDED",
  "requestId": "c1f7a28e-5b23-4d6b-9c88-123456789abc"
}
```

### Common Error Codes:
- `INVALID_LOCATION_ID` (HTTP 400): Location identifier missing or failed regex validation.
- `EMPTY_PAYLOAD` / `MALFORMED_JSON` / `VALIDATION_FAILED` (HTTP 400/422): Input parameters out of physical bounds.
- `UNAUTHORIZED` (HTTP 401): Missing or invalid admin authorization token.
- `LOCATION_NOT_FOUND` (HTTP 404): Outlet does not exist in directory.
- `RATE_LIMIT_EXCEEDED` (HTTP 429): Client exceeded anonymous submission threshold (5 requests per 5 minutes).
- `PERSISTENCE_FAILED` (HTTP 500): Database storage rejected write; client must retry (no optimistic false success).
- `INTERNAL_ERROR` (HTTP 500): General unhandled backend exception.


