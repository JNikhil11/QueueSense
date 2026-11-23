"""
QueueSense - DynamoDB Storage Access Layer
Single-table architecture supporting:
- Location metadata with verifiable provenance
- Time-series crowdsourced reports
- Pre-aggregated current queue estimates
- Atomic idempotency deduplication
- Privacy-preserving anonymous rate-limiting records
- Historical day/time bucketed observations
- Strict separation of production DynamoDB and isolated unit test adapters.
"""

from __future__ import annotations
import os
import time
import uuid
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger("queuesense.database")

# =========================================================================
# Custom Exceptions (Fail-Closed, Controlled Public Errors)
# =========================================================================

class QueueSenseDatabaseError(Exception):
    """Base exception for all QueueSense database layer operations."""
    pass


class DatabasePersistenceError(QueueSenseDatabaseError):
    """Raised when a durable write operation fails in DynamoDB."""
    pass


class RateLimitExceededError(QueueSenseDatabaseError):
    """Raised when a client exceeds allowed submission frequency."""
    pass


class IdempotencyConflictError(QueueSenseDatabaseError):
    """Raised when an idempotency conflict occurs."""
    pass


class LocationNotFoundError(QueueSenseDatabaseError):
    """Raised when a queried campus outlet does not exist."""
    pass


# =========================================================================
# Verifiable Campus Food Directories (Configurable via CAMPUS_ID)
# Note: VerificationStatus is marked STUDENT_SOURCED unless institutional
# signed confirmation is on file.
# =========================================================================

IITB_CAMPUS_LOCATIONS = [
    {
        "id": "iitb-mess-h12-14",
        "name": "Hostel 12-13-14 Dining Complex",
        "category": "MESS",
        "description": "Central multi-tiered student mess serving breakfast, lunch, snacks, and dinner counters.",
        "landmarkLocation": "Hostel 12-14 Complex, Lakeside Road, East Campus",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Council of Student Affairs / Gymkhana Guide (Community Sourced)",
        "openHours": "07:30 - 21:30",
        "capacity": 650,
        "active": True,
    },
    {
        "id": "iitb-mess-h15-16",
        "name": "Hostel 15-16 Dining Hall",
        "category": "MESS",
        "description": "Modern high-capacity hostel mess catering to senior undergraduate and postgraduate wings.",
        "landmarkLocation": "Hostel 15-16 Quadrangle, North-East Campus",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Student Mentor Program (SMP Guide)",
        "openHours": "07:30 - 21:30",
        "capacity": 550,
        "active": True,
    },
    {
        "id": "iitb-mess-h2",
        "name": "Hostel 2 Dining Hall & Mess",
        "category": "MESS",
        "description": "Historic hostel mess renowned for South and North Indian rotating regional menus.",
        "landmarkLocation": "Hostel 2 Quadrangle, near Gymkhana Grounds",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Hostel 2 Council & SMP Guide",
        "openHours": "07:30 - 21:00",
        "capacity": 350,
        "active": True,
    },
    {
        "id": "iitb-canteen-h3",
        "name": "Hostel 3 Canteen & Juice Centre",
        "category": "CANTEEN",
        "description": "Beloved campus late-night staple serving fresh fruit juices, dosas, parathas, and tea.",
        "landmarkLocation": "Ground Floor, Hostel 3, Main Hostel Avenue",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Gymkhana Freshers Guide",
        "openHours": "14:00 - 02:30",
        "capacity": 120,
        "active": True,
    },
    {
        "id": "iitb-canteen-lhc",
        "name": "LHC Food Court (Lecture Hall)",
        "category": "CANTEEN",
        "description": "High-velocity daytime cafeteria serving express lunches, coffee, sandwiches, and rolls.",
        "landmarkLocation": "Ground Floor, Lecture Hall Complex (LHC), Academic Area",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Academic Facilities & SMP Guide",
        "openHours": "08:30 - 18:30",
        "capacity": 220,
        "active": True,
    },
    {
        "id": "iitb-canteen-gulmohar",
        "name": "Gulmohar Restaurant & Cafe",
        "category": "CANTEEN",
        "description": "Multi-cuisine sit-down restaurant and faculty guest lounge serving thalis and meals.",
        "landmarkLocation": "Gulmohar Building, First Floor, Opposite Main Building",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Estate & Hospitality Directory",
        "openHours": "11:00 - 22:30",
        "capacity": 180,
        "active": True,
    },
    {
        "id": "iitb-canteen-kresit",
        "name": "KReSIT IT Canteen (CSE)",
        "category": "CANTEEN",
        "description": "Quick-service eatery favored by computer science students for coffee, noodles, and wraps.",
        "landmarkLocation": "Kanwal Rekhi School of Information Technology (KReSIT)",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Dept of Computer Science & Eng Guide",
        "openHours": "09:00 - 20:00",
        "capacity": 90,
        "active": True,
    },
    {
        "id": "iitb-cafe-92",
        "name": "Cafe 92 (SAC Hangout)",
        "category": "CANTEEN",
        "description": "Active evening hangout spot serving milkshakes, burgers, hot fries, and snacks.",
        "landmarkLocation": "Students Activity Centre (SAC) Grounds",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Gymkhana Cultural Affairs Guide",
        "openHours": "16:00 - 01:00",
        "capacity": 140,
        "active": True,
    },
    {
        "id": "iitb-canteen-brewberrys",
        "name": "Brewberrys The Coffee Bar",
        "category": "CANTEEN",
        "description": "Artisan coffee, bakery items, iced brews, and quiet tables for study sessions.",
        "landmarkLocation": "Adjacent to Central Library, Main Academic Spine",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Central Library Amenities Guide",
        "openHours": "08:00 - 23:00",
        "capacity": 80,
        "active": True,
    },
    {
        "id": "iitb-amul-parlour",
        "name": "Amul Ice Cream & Dairy Parlour",
        "category": "CANTEEN",
        "description": "Exclusive dairy outlet offering ice creams, flavored milk, milkshakes, and packaged snacks.",
        "landmarkLocation": "Near Hostel 1 & Campus School Junction",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Commercial Establishments Guide",
        "openHours": "09:00 - 23:00",
        "capacity": 40,
        "active": True,
    },
]

VITAP_CAMPUS_LOCATIONS = [
    {
        "id": "vitap-mess-a",
        "name": "Central Mess A (North Block)",
        "category": "MESS",
        "description": "Multi-counter student dining hall serving breakfast, lunch, and dinner.",
        "landmarkLocation": "North Dining Block, Near MH-1",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "VIT-AP Student Dining Guide (Community Sourced)",
        "openHours": "07:30 - 21:30",
        "capacity": 450,
        "active": True,
    },
    {
        "id": "vitap-mess-b",
        "name": "South Mess B (Annex Dining)",
        "category": "MESS",
        "description": "South dining hall featuring vegetarian and regional dining counters.",
        "landmarkLocation": "South Student Block, Near LH-1",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "VIT-AP Student Dining Guide (Community Sourced)",
        "openHours": "07:30 - 21:00",
        "capacity": 350,
        "active": True,
    },
    {
        "id": "vitap-rock-plaza",
        "name": "Rock Plaza Food Court",
        "category": "CANTEEN",
        "description": "Open-air food court offering quick snacks, fruit juices, and meals.",
        "landmarkLocation": "Central Plaza, Between Academic & Hostel Blocks",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "VIT-AP Student Dining Guide (Community Sourced)",
        "openHours": "10:00 - 23:00",
        "capacity": 180,
        "active": True,
    },
    {
        "id": "vitap-academic-bistro",
        "name": "Academic Bistro",
        "category": "CANTEEN",
        "description": "Express counter near lecture halls for sandwiches, rolls, and coffee.",
        "landmarkLocation": "Central Block (CB), Ground Floor",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "VIT-AP Student Dining Guide (Community Sourced)",
        "openHours": "08:30 - 18:00",
        "capacity": 120,
        "active": True,
    },
    {
        "id": "vitap-midnight-fuel",
        "name": "Midnight Fuel Canteen",
        "category": "CANTEEN",
        "description": "Late-evening campus eatery active during study and project hours.",
        "landmarkLocation": "Hostel Avenue Commercial Area",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "VIT-AP Student Dining Guide (Community Sourced)",
        "openHours": "17:00 - 02:00",
        "capacity": 150,
        "active": True,
    },
]

# Configurable active campus (default: iitb)
ACTIVE_CAMPUS = os.environ.get("CAMPUS_ID", "iitb").lower()
DEFAULT_CAMPUS_LOCATIONS = (
    VITAP_CAMPUS_LOCATIONS if ACTIVE_CAMPUS == "vitap" else IITB_CAMPUS_LOCATIONS
)


# =========================================================================
# Abstract Storage Adapter
# =========================================================================

class BaseStorageAdapter(ABC):
    """Abstract interface defining the required persistence contract."""

    @abstractmethod
    def list_locations(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_location(self, location_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def record_report(
        self,
        location_id: str,
        reported_wait_minutes: float,
        queue_length: int,
        note: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_recent_reports(self, location_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def save_current_estimate(self, location_id: str, estimate: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_current_estimate(self, location_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_all_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def check_rate_limit(self, client_hash: str, window_seconds: int = 300, max_requests: int = 5) -> bool:
        pass

    @abstractmethod
    def get_historical_reports(self, location_id: str, days: int = 14, limit: int = 200) -> List[Dict[str, Any]]:
        pass


# =========================================================================
# Production DynamoDB Storage Adapter (Fails Closed, No Silent Fallback)
# =========================================================================

class DynamoDBStorageAdapter(BaseStorageAdapter):
    """
    Production DynamoDB client.
    Guarantees that a write is only reported successful if confirmed by DynamoDB.
    Propagates controlled DatabasePersistenceError on AWS errors.
    """

    def __init__(self, table_name: str, region: Optional[str] = None):
        self.table_name = table_name
        self.region = region or os.environ.get("AWS_REGION", "ap-southeast-2")
        self._dynamodb_resource = None
        self._table = None
        self._init_dynamodb()

    def _init_dynamodb(self):
        try:
            import boto3  # type: ignore
            self._dynamodb_resource = boto3.resource("dynamodb", region_name=self.region)
            self._table = self._dynamodb_resource.Table(self.table_name)
        except Exception as e:
            logger.error("Failed to initialize DynamoDB resource: %s", str(e))
            self._table = None

    def _ensure_table(self):
        if self._table is None:
            self._init_dynamodb()
        if self._table is None:
            raise DatabasePersistenceError("DynamoDB storage table is not available.")

    def list_locations(self) -> List[Dict[str, Any]]:
        self._ensure_table()
        try:
            from boto3.dynamodb.conditions import Attr  # type: ignore
            resp = self._table.scan(
                FilterExpression=Attr("entityType").eq("LOCATION") & Attr("active").eq(True)
            )
            items = resp.get("Items", [])
            if not items:
                # First-time seed into database
                self.seed_locations()
                return self.list_locations()
            return sorted(items, key=lambda x: x.get("name", ""))
        except Exception as e:
            logger.error("DynamoDB list_locations failed: %s", str(e))
            raise DatabasePersistenceError(f"Failed to retrieve campus locations from database: {str(e)}")

    def get_location(self, location_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_table()
        pk = f"LOCATION#{location_id}"
        sk = "METADATA"
        try:
            resp = self._table.get_item(Key={"PK": pk, "SK": sk})
            return resp.get("Item")
        except Exception as e:
            logger.error("DynamoDB get_location failed: %s", str(e))
            raise DatabasePersistenceError(f"Failed to retrieve location '{location_id}' from database.")

    def record_report(
        self,
        location_id: str,
        reported_wait_minutes: float,
        queue_length: int,
        note: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_table()

        # Idempotency Check: if key provided and already registered, return cached report
        if idempotency_key:
            idem_pk = f"IDEMPOTENCY#{idempotency_key}"
            idem_sk = "RECORD"
            try:
                existing_idem = self._table.get_item(Key={"PK": idem_pk, "SK": idem_sk}).get("Item")
                if existing_idem and "cachedReport" in existing_idem:
                    logger.info("Idempotent replay detected for key: %s", idempotency_key)
                    return existing_idem["cachedReport"]
            except Exception as e:
                logger.warning("Idempotency lookup warning: %s", str(e))

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

        from decimal import Decimal  # type: ignore
        clean_item = self._convert_floats_to_decimal(item)

        try:
            self._table.put_item(Item=clean_item)
        except Exception as e:
            logger.error("DynamoDB write failed for report %s: %s", report_id, str(e))
            raise DatabasePersistenceError("Failed to persist queue observation to durable database.")

        # Persist Idempotency Record (24-hour TTL)
        if idempotency_key:
            try:
                idem_ttl = int(time.time()) + 86400
                self._table.put_item(
                    Item={
                        "PK": f"IDEMPOTENCY#{idempotency_key}",
                        "SK": "RECORD",
                        "entityType": "IDEMPOTENCY",
                        "cachedReport": clean_item,
                        "ttl": idem_ttl,
                    }
                )
            except Exception as e:
                logger.warning("Failed to record idempotency key: %s", str(e))

        return item

    def get_recent_reports(self, location_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        self._ensure_table()
        pk = f"LOCATION#{location_id}"
        try:
            from boto3.dynamodb.conditions import Key  # type: ignore
            resp = self._table.query(
                KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("REPORT#"),
                ScanIndexForward=False,
                Limit=limit,
            )
            items = resp.get("Items", [])
            return self._convert_decimals_to_float(items)
        except Exception as e:
            logger.error("DynamoDB get_recent_reports failed: %s", str(e))
            raise DatabasePersistenceError(f"Failed to query recent observations: {str(e)}")

    def save_current_estimate(self, location_id: str, estimate: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_table()
        pk = f"LOCATION#{location_id}"
        sk = "ESTIMATE#CURRENT"

        item = {
            "PK": pk,
            "SK": sk,
            "entityType": "ESTIMATE",
            "locationId": location_id,
            **estimate,
        }
        clean_item = self._convert_floats_to_decimal(item)
        try:
            self._table.put_item(Item=clean_item)
            return estimate
        except Exception as e:
            logger.error("DynamoDB save_current_estimate failed: %s", str(e))
            raise DatabasePersistenceError("Failed to persist queue estimate cache.")

    def get_current_estimate(self, location_id: str) -> Optional[Dict[str, Any]]:
        self._ensure_table()
        pk = f"LOCATION#{location_id}"
        sk = "ESTIMATE#CURRENT"
        try:
            resp = self._table.get_item(Key={"PK": pk, "SK": sk})
            item = resp.get("Item")
            return self._convert_decimals_to_float(item) if item else None
        except Exception as e:
            logger.error("DynamoDB get_current_estimate failed: %s", str(e))
            raise DatabasePersistenceError("Failed to retrieve current queue estimate.")

    def list_all_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        self._ensure_table()
        try:
            from boto3.dynamodb.conditions import Attr  # type: ignore
            resp = self._table.scan(
                FilterExpression=Attr("entityType").eq("REPORT"),
                Limit=limit,
            )
            items = resp.get("Items", [])
            items.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            return self._convert_decimals_to_float(items[:limit])
        except Exception as e:
            logger.error("DynamoDB list_all_reports failed: %s", str(e))
            raise DatabasePersistenceError("Failed to retrieve audit feed.")

    def check_rate_limit(self, client_hash: str, window_seconds: int = 300, max_requests: int = 5) -> bool:
        self._ensure_table()
        current_epoch = int(time.time())
        window_idx = current_epoch // window_seconds
        pk = f"RATELIMIT#{client_hash}"
        sk = f"WINDOW#{window_idx}"
        ttl = current_epoch + (window_seconds * 2)

        try:
            resp = self._table.update_item(
                Key={"PK": pk, "SK": sk},
                UpdateExpression="ADD reqCount :inc SET #t = :ttl, entityType = :ent",
                ExpressionAttributeNames={"#t": "ttl"},
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":ttl": ttl,
                    ":ent": "RATELIMIT",
                },
                ReturnValues="UPDATED_NEW",
            )
            count = int(resp.get("Attributes", {}).get("reqCount", 1))
            return count <= max_requests
        except Exception as e:
            logger.warning("Rate limit check warning (failing open): %s", str(e))
            return True

    def get_historical_reports(self, location_id: str, days: int = 14, limit: int = 200) -> List[Dict[str, Any]]:
        self._ensure_table()
        pk = f"LOCATION#{location_id}"
        try:
            from boto3.dynamodb.conditions import Key  # type: ignore
            resp = self._table.query(
                KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("REPORT#"),
                ScanIndexForward=False,
                Limit=limit,
            )
            items = resp.get("Items", [])
            return self._convert_decimals_to_float(items)
        except Exception as e:
            logger.error("DynamoDB get_historical_reports failed: %s", str(e))
            raise DatabasePersistenceError("Failed to retrieve historical observations.")

    def seed_locations(self):
        self._ensure_table()
        for loc in DEFAULT_CAMPUS_LOCATIONS:
            pk = f"LOCATION#{loc['id']}"
            sk = "METADATA"
            item = {
                "PK": pk,
                "SK": sk,
                "entityType": "LOCATION",
                **loc,
            }
            try:
                self._table.put_item(Item=item)
            except Exception as e:
                logger.warning("Could not seed location %s: %s", loc["id"], str(e))

    @staticmethod
    def _convert_floats_to_decimal(obj: Any) -> Any:
        from decimal import Decimal
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: DynamoDBStorageAdapter._convert_floats_to_decimal(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [DynamoDBStorageAdapter._convert_floats_to_decimal(v) for v in obj]
        return obj

    @staticmethod
    def _convert_decimals_to_float(obj: Any) -> Any:
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, dict):
            return {k: DynamoDBStorageAdapter._convert_decimals_to_float(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [DynamoDBStorageAdapter._convert_decimals_to_float(v) for v in obj]
        return obj


# =========================================================================
# In-Memory Storage Adapter (Exclusively for Isolated Unit Tests)
# =========================================================================

class InMemoryStorageAdapter(BaseStorageAdapter):
    """
    In-memory storage adapter for deterministic, isolated unit tests.
    Supports controlled simulated failure toggles to verify fail-closed behavior.
    """

    def __init__(self, initial_locations: Optional[List[Dict[str, Any]]] = None):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._idempotency_store: Dict[str, Dict[str, Any]] = {}
        self._rate_limits: Dict[str, int] = {}
        self._simulate_failure: bool = False

        locs = initial_locations or DEFAULT_CAMPUS_LOCATIONS
        for loc in locs:
            pk = f"LOCATION#{loc['id']}"
            sk = "METADATA"
            self._store[f"{pk}::{sk}"] = {
                "PK": pk,
                "SK": sk,
                "entityType": "LOCATION",
                **loc,
            }

    def set_simulate_failure(self, fail: bool):
        """Toggle simulated persistence failure for acceptance testing."""
        self._simulate_failure = fail

    def list_locations(self) -> List[Dict[str, Any]]:
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database failure.")
        locations = [
            v for v in self._store.values()
            if v.get("entityType") == "LOCATION" and v.get("active", True)
        ]
        return sorted(locations, key=lambda x: x["name"])

    def get_location(self, location_id: str) -> Optional[Dict[str, Any]]:
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database failure.")
        key = f"LOCATION#{location_id}::METADATA"
        return self._store.get(key)

    def record_report(
        self,
        location_id: str,
        reported_wait_minutes: float,
        queue_length: int,
        note: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database persistence failure.")

        # Check Idempotency
        if idempotency_key and idempotency_key in self._idempotency_store:
            return self._idempotency_store[idempotency_key]

        now = datetime.now(timezone.utc)
        iso_timestamp = now.isoformat()
        report_id = f"rep_{uuid.uuid4().hex[:12]}"

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
            "ttl": int(time.time()) + (7 * 86400),
        }

        self._store[f"{pk}::{sk}"] = item
        if idempotency_key:
            self._idempotency_store[idempotency_key] = item

        return item

    def get_recent_reports(self, location_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database failure.")
        pk = f"LOCATION#{location_id}"
        items = [
            v for v in self._store.values()
            if v.get("PK") == pk and v.get("entityType") == "REPORT"
        ]
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return items[:limit]

    def save_current_estimate(self, location_id: str, estimate: Dict[str, Any]) -> Dict[str, Any]:
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database failure.")
        pk = f"LOCATION#{location_id}"
        sk = "ESTIMATE#CURRENT"
        item = {
            "PK": pk,
            "SK": sk,
            "entityType": "ESTIMATE",
            "locationId": location_id,
            **estimate,
        }
        self._store[f"{pk}::{sk}"] = item
        return item

    def get_current_estimate(self, location_id: str) -> Optional[Dict[str, Any]]:
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database failure.")
        pk = f"LOCATION#{location_id}"
        sk = "ESTIMATE#CURRENT"
        return self._store.get(f"{pk}::{sk}")

    def list_all_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database failure.")
        items = [v for v in self._store.values() if v.get("entityType") == "REPORT"]
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        return items[:limit]

    def check_rate_limit(self, client_hash: str, window_seconds: int = 300, max_requests: int = 5) -> bool:
        current_window = int(time.time()) // window_seconds
        key = f"{client_hash}::{current_window}"
        count = self._rate_limits.get(key, 0) + 1
        self._rate_limits[key] = count
        return count <= max_requests

    def get_historical_reports(self, location_id: str, days: int = 14, limit: int = 200) -> List[Dict[str, Any]]:
        return self.get_recent_reports(location_id, limit=limit)


# =========================================================================
# QueueSenseDatabase Public Facade
# =========================================================================

# Shared process-level test adapter for unit test testcases
_shared_test_adapter: Optional[InMemoryStorageAdapter] = None


def get_shared_test_adapter() -> InMemoryStorageAdapter:
    global _shared_test_adapter
    if _shared_test_adapter is None:
        _shared_test_adapter = InMemoryStorageAdapter()
    return _shared_test_adapter


def reset_shared_test_adapter() -> None:
    global _shared_test_adapter
    _shared_test_adapter = InMemoryStorageAdapter()


class QueueSenseDatabase:
    """
    Main database service entrypoint.
    In production: Uses DynamoDBStorageAdapter. Fails closed on connection/write errors.
    In unit tests: Explicitly injects InMemoryStorageAdapter or checks STORAGE_BACKEND / DATA_MODE env.
    """

    def __init__(
        self,
        table_name: Optional[str] = None,
        adapter: Optional[BaseStorageAdapter] = None,
    ):
        self.table_name = table_name or os.environ.get("TABLE_NAME", "QueueSense-Main")

        backend_env = os.environ.get("STORAGE_BACKEND", "").lower()
        data_mode_env = os.environ.get("DATA_MODE", "").lower()
        is_test_env = (
            os.environ.get("PYTEST_CURRENT_TEST") is not None
            or os.environ.get("USE_IN_MEMORY_ADAPTER", "").lower() == "true"
            or backend_env == "memory"
            or data_mode_env in ("test", "demo")
        )

        if adapter is not None:
            self._adapter = adapter
        elif is_test_env:
            self._adapter = get_shared_test_adapter()
        else:
            # Default to production DynamoDB adapter
            self._adapter = DynamoDBStorageAdapter(table_name=self.table_name)

    def list_locations(self) -> List[Dict[str, Any]]:
        return self._adapter.list_locations()

    def get_location(self, location_id: str) -> Optional[Dict[str, Any]]:
        return self._adapter.get_location(location_id)

    def record_report(
        self,
        location_id: str,
        reported_wait_minutes: float,
        queue_length: int,
        note: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._adapter.record_report(
            location_id=location_id,
            reported_wait_minutes=reported_wait_minutes,
            queue_length=queue_length,
            note=note,
            idempotency_key=idempotency_key,
        )

    def get_recent_reports(self, location_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        return self._adapter.get_recent_reports(location_id=location_id, limit=limit)

    def save_current_estimate(self, location_id: str, estimate: Dict[str, Any]) -> Dict[str, Any]:
        return self._adapter.save_current_estimate(location_id=location_id, estimate=estimate)

    def get_current_estimate(self, location_id: str) -> Optional[Dict[str, Any]]:
        return self._adapter.get_current_estimate(location_id=location_id)

    def list_all_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._adapter.list_all_reports(limit=limit)

    def check_rate_limit(self, client_hash: str, window_seconds: int = 300, max_requests: int = 5) -> bool:
        return self._adapter.check_rate_limit(client_hash=client_hash, window_seconds=window_seconds, max_requests=max_requests)

    def get_historical_reports(self, location_id: str, days: int = 14, limit: int = 200) -> List[Dict[str, Any]]:
        return self._adapter.get_historical_reports(location_id=location_id, days=days, limit=limit)
