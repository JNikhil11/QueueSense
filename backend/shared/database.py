"""
QueueSense - DynamoDB Storage Access Layer
Single-table architecture supporting:
- Location metadata
- Time-series crowdsourced reports
- Pre-aggregated current queue estimates
Includes in-memory fallback for offline testability.
"""

from __future__ import annotations
import os
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Standard Seed Outlets for VIT-AP Campus Context (Configurable)
DEFAULT_CAMPUS_LOCATIONS = [
    {
        "id": "mess-a-central",
        "name": "Central Mess A (North Dining)",
        "category": "MESS",
        "description": "Primary multi-story student dining hall serving breakfast, lunch, and dinner.",
        "openHours": "07:30 - 21:30",
        "capacity": 450,
        "active": True,
    },
    {
        "id": "mess-b-south",
        "name": "South Mess B (Annex Dining)",
        "category": "MESS",
        "description": "South block student dining hall featuring traditional and vegetarian meal counters.",
        "openHours": "07:30 - 21:00",
        "capacity": 350,
        "active": True,
    },
    {
        "id": "canteen-rock-plaza",
        "name": "Rock Plaza Food Court",
        "category": "CANTEEN",
        "description": "Open-air plaza offering quick snacks, juices, hot beverages, and rolls.",
        "openHours": "10:00 - 23:00",
        "capacity": 180,
        "active": True,
    },
    {
        "id": "canteen-academic-block",
        "name": "CB Academic Bistro",
        "category": "CANTEEN",
        "description": "Fast-counter canteen situated near lecture halls for express lunch and coffee.",
        "openHours": "08:30 - 18:00",
        "capacity": 120,
        "active": True,
    },
    {
        "id": "canteen-night-cafeteria",
        "name": "Midnight Fuel Canteen",
        "category": "CANTEEN",
        "description": "Late-evening campus outlet popular during exam periods and project deadlines.",
        "openHours": "17:00 - 02:00",
        "capacity": 150,
        "active": True,
    },
]


class QueueSenseDatabase:
    """DynamoDB client wrapper with auto-initialization and memory fallback."""

    _shared_memory_store: Dict[str, Dict[str, Any]] = {}
    _memory_initialized: bool = False

    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.environ.get("TABLE_NAME", "QueueSense-Main")
        self._dynamodb_resource = None
        self._table = None
        self._use_in_memory = False

        # Attempt to initialize boto3 if AWS credentials or SAM local available
        try:
            import boto3  # type: ignore
            # Check if boto3 has credentials / region configured
            self._dynamodb_resource = boto3.resource(
                "dynamodb",
                region_name=os.environ.get("AWS_REGION", "ap-southeast-2"),
            )
            self._table = self._dynamodb_resource.Table(self.table_name)
        except Exception:
            self._use_in_memory = True

        # Prepopulate shared memory store with default locations if not initialized
        if (self._use_in_memory or not self._table) and not QueueSenseDatabase._memory_initialized:
            self._init_memory_store()

    def _init_memory_store(self):
        """Seed default outlets into shared in-memory store."""
        for loc in DEFAULT_CAMPUS_LOCATIONS:
            pk = f"LOCATION#{loc['id']}"
            sk = "METADATA"
            key = f"{pk}::{sk}"
            QueueSenseDatabase._shared_memory_store[key] = {
                "PK": pk,
                "SK": sk,
                "entityType": "LOCATION",
                **loc,
            }
        QueueSenseDatabase._memory_initialized = True

    def list_locations(self) -> List[Dict[str, Any]]:
        """Retrieve all active campus locations."""
        if self._use_in_memory or not self._table:
            locations = [
                item
                for item in QueueSenseDatabase._shared_memory_store.values()
                if item.get("entityType") == "LOCATION" and item.get("active", True)
            ]
            return sorted(locations, key=lambda x: x["name"])

        try:
            from boto3.dynamodb.conditions import Attr  # type: ignore
            resp = self._table.scan(
                FilterExpression=Attr("entityType").eq("LOCATION") & Attr("active").eq(True)
            )
            items = resp.get("Items", [])
            if not items:
                self.seed_default_locations()
                return self.list_locations()
            return sorted(items, key=lambda x: x.get("name", ""))
        except Exception:
            return DEFAULT_CAMPUS_LOCATIONS

    def get_location(self, location_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve single location metadata."""
        pk = f"LOCATION#{location_id}"
        sk = "METADATA"
        key = f"{pk}::{sk}"

        if self._use_in_memory or not self._table:
            return QueueSenseDatabase._shared_memory_store.get(key)

        try:
            resp = self._table.get_item(Key={"PK": pk, "SK": sk})
            return resp.get("Item")
        except Exception:
            return next((l for l in DEFAULT_CAMPUS_LOCATIONS if l["id"] == location_id), None)

    def record_report(
        self,
        location_id: str,
        reported_wait_minutes: float,
        queue_length: int,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record a crowdsourced observation.
        Generates server-side timestamp, unique ID, and 7-day TTL.
        """
        now = datetime.now(timezone.utc)
        iso_timestamp = now.isoformat()
        report_id = f"rep_{uuid.uuid4().hex[:12]}"
        epoch_ttl = int(time.time()) + (7 * 86400)  # 7 days

        pk = f"LOCATION#{location_id}"
        sk = f"REPORT#{iso_timestamp}#{report_id}"

        item = {
            "PK": pk,
            "SK": sk,
            "entityType": "REPORT",
            "reportId": report_id,
            "locationId": location_id,
            "reportedWaitMinutes": round(float(reported_wait_minutes), 1),
            "queueLength": int(queue_length),
            "note": note,
            "timestamp": iso_timestamp,
            "ttl": epoch_ttl,
        }

        if self._use_in_memory or not self._table:
            QueueSenseDatabase._shared_memory_store[f"{pk}::{sk}"] = item
            return item

        try:
            self._table.put_item(Item=item)
            return item
        except Exception:
            QueueSenseDatabase._shared_memory_store[f"{pk}::{sk}"] = item
            return item

    def get_recent_reports(
        self, location_id: str, limit: int = 30
    ) -> List[Dict[str, Any]]:
        """Retrieve recent reports for a specific location, newest first."""
        pk = f"LOCATION#{location_id}"

        if self._use_in_memory or not self._table:
            items = [
                v
                for k, v in QueueSenseDatabase._shared_memory_store.items()
                if v.get("PK") == pk and v.get("entityType") == "REPORT"
            ]
            items.sort(key=lambda x: x["timestamp"], reverse=True)
            return items[:limit]

        try:
            from boto3.dynamodb.conditions import Key  # type: ignore
            resp = self._table.query(
                KeyConditionExpression=Key("PK").eq(pk)
                & Key("SK").begins_with("REPORT#"),
                ScanIndexForward=False,
                Limit=limit,
            )
            return resp.get("Items", [])
        except Exception:
            items = [
                v
                for k, v in QueueSenseDatabase._shared_memory_store.items()
                if v.get("PK") == pk and v.get("entityType") == "REPORT"
            ]
            items.sort(key=lambda x: x["timestamp"], reverse=True)
            return items[:limit]

    def save_current_estimate(
        self, location_id: str, estimate: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Save aggregated queue estimate for fast single-point reads."""
        pk = f"LOCATION#{location_id}"
        sk = "ESTIMATE#CURRENT"

        item = {
            "PK": pk,
            "SK": sk,
            "entityType": "ESTIMATE",
            "locationId": location_id,
            **estimate,
        }

        if self._use_in_memory or not self._table:
            QueueSenseDatabase._shared_memory_store[f"{pk}::{sk}"] = item
            return item

        try:
            from decimal import Decimal  # type: ignore
            clean_item = self._convert_floats_to_decimal(item)
            self._table.put_item(Item=clean_item)
            return item
        except Exception:
            QueueSenseDatabase._shared_memory_store[f"{pk}::{sk}"] = item
            return item

    def get_current_estimate(self, location_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored current estimate for a location."""
        pk = f"LOCATION#{location_id}"
        sk = "ESTIMATE#CURRENT"

        if self._use_in_memory or not self._table:
            return QueueSenseDatabase._shared_memory_store.get(f"{pk}::{sk}")

        try:
            resp = self._table.get_item(Key={"PK": pk, "SK": sk})
            return resp.get("Item")
        except Exception:
            return QueueSenseDatabase._shared_memory_store.get(f"{pk}::{sk}")

    def list_all_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Admin/Audit: Retrieve recent reports across all locations."""
        if self._use_in_memory or not self._table:
            items = [
                v for v in QueueSenseDatabase._shared_memory_store.values() if v.get("entityType") == "REPORT"
            ]
            items.sort(key=lambda x: x["timestamp"], reverse=True)
            return items[:limit]

        try:
            from boto3.dynamodb.conditions import Attr  # type: ignore
            resp = self._table.scan(
                FilterExpression=Attr("entityType").eq("REPORT"),
                Limit=limit,
            )
            items = resp.get("Items", [])
            items.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            return items[:limit]
        except Exception:
            items = [
                v for v in QueueSenseDatabase._shared_memory_store.values() if v.get("entityType") == "REPORT"
            ]
            items.sort(key=lambda x: x["timestamp"], reverse=True)
            return items[:limit]

    def seed_default_locations(self):
        """Populate DynamoDB table with initial location metadata."""
        if not self._table:
            self._init_memory_store()
            return

        try:
            for loc in DEFAULT_CAMPUS_LOCATIONS:
                pk = f"LOCATION#{loc['id']}"
                sk = "METADATA"
                item = {
                    "PK": pk,
                    "SK": sk,
                    "entityType": "LOCATION",
                    **loc,
                }
                self._table.put_item(Item=item)
        except Exception:
            self._init_memory_store()

    @staticmethod
    def _convert_floats_to_decimal(obj: Any) -> Any:
        from decimal import Decimal
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: QueueSenseDatabase._convert_floats_to_decimal(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [QueueSenseDatabase._convert_floats_to_decimal(v) for v in obj]
        return obj
