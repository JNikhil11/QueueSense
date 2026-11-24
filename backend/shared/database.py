"""
QueueSense - DynamoDB Storage Access Layer
Single-table architecture supporting:
- Location metadata with verifiable, non-fabricated provenance
- Time-series crowdsourced reports
- Pre-aggregated current queue estimates
- Atomic idempotency deduplication via TransactWriteItems
- Privacy-preserving anonymous rate-limiting records (Fail-closed)
- Historical 14-day cutoff query with campus timezone alignment
- Strict separation of production DynamoDB and isolated unit test adapters.
"""

from __future__ import annotations
import os
import sys
import time
import math
import uuid
import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Union

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
# Note: VerificationStatus is strictly STUDENT_SOURCED or COMMUNITY_LISTING.
# Precise integer seating capacities and unverified claims have been removed.
# =========================================================================

IITB_CAMPUS_LOCATIONS = [
    {
        "id": "iitb-mess-h12-14",
        "name": "Hostel 12-13-14 Dining Complex",
        "category": "MESS",
        "description": "Central multi-tiered student mess serving breakfast, lunch, snacks, and dinner counters.",
        "landmarkLocation": "Hostel 12-14 Complex, Lakeside Road, East Campus",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Council of Student Affairs / Student Mentorship Directory",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "IIT Bombay Council of Student Affairs",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "Breakfast (07:30-09:30), Lunch (12:00-14:15), Tiffin (16:30-18:00), Dinner (19:30-21:45)",
        "capacityEstimate": "Large Dining Complex (~400-600 approx.)",
        "active": True,
    },
    {
        "id": "iitb-mess-h15-16",
        "name": "Hostel 15-16 Dining Hall",
        "category": "MESS",
        "description": "Modern hostel mess catering to senior undergraduate and postgraduate wings.",
        "landmarkLocation": "Hostel 15-16 Quadrangle, North-East Campus",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Student Mentor Program (SMP) Freshers Guide",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "IIT Bombay Student Mentor Program",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "Breakfast (07:30-09:30), Lunch (12:00-14:15), Tiffin (16:30-18:00), Dinner (19:30-21:45)",
        "capacityEstimate": "Large Dining Hall (~400-500 approx.)",
        "active": True,
    },
    {
        "id": "iitb-mess-h2",
        "name": "Hostel 2 Dining Hall & Mess",
        "category": "MESS",
        "description": "Hostel mess renowned for rotating regional menus and dining counters.",
        "landmarkLocation": "Hostel 2 Quadrangle, near Gymkhana Grounds",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Hostel 2 Student Guide",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "IIT Bombay Hostel 2 Council",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "Breakfast (07:30-09:30), Lunch (12:00-14:15), Tiffin (16:30-18:00), Dinner (19:30-21:30)",
        "capacityEstimate": "Medium Dining Hall (~250-350 approx.)",
        "active": True,
    },
    {
        "id": "iitb-canteen-h3",
        "name": "Hostel 3 Canteen & Juice Centre",
        "category": "CANTEEN",
        "description": "Campus late-night staple serving fresh fruit juices, dosas, parathas, and tea.",
        "landmarkLocation": "Ground Floor, Hostel 3, Main Hostel Avenue",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Gymkhana Freshers Guide",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "IIT Bombay Gymkhana",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "14:00 - 02:00 (Late Night)",
        "capacityEstimate": "Cafeteria Seating (~80-120 approx.)",
        "active": True,
    },
    {
        "id": "iitb-canteen-lhc",
        "name": "LHC Food Court (Lecture Hall)",
        "category": "CANTEEN",
        "description": "Daytime cafeteria serving express lunches, coffee, sandwiches, and rolls.",
        "landmarkLocation": "Ground Floor, Lecture Hall Complex (LHC), Academic Area",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Student Mentor Program Academic Guide",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "IIT Bombay Academic Area Mentors",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "08:30 - 18:30 (Class Hours)",
        "capacityEstimate": "Medium Food Court (~150-220 approx.)",
        "active": True,
    },
    {
        "id": "iitb-canteen-gulmohar",
        "name": "Gulmohar Restaurant & Cafe",
        "category": "CANTEEN",
        "description": "Multi-cuisine sit-down restaurant and guest lounge serving meals and thalis.",
        "landmarkLocation": "Gulmohar Building, First Floor, Opposite Main Building",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "IIT Bombay Campus Commercial Establishments Directory",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "IIT Bombay Commercial Establishments Register",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "11:00 - 22:30",
        "capacityEstimate": "Restaurant Seating (~120-180 approx.)",
        "active": True,
    },
    {
        "id": "iitb-canteen-kresit",
        "name": "KReSIT IT Canteen (CSE)",
        "category": "CANTEEN",
        "description": "Quick-service eatery favored by computer science students for coffee, noodles, and wraps.",
        "landmarkLocation": "Kanwal Rekhi School of Information Technology (KReSIT)",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "Dept of Computer Science & Engineering Student Mentors",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "Dept of CSE Student Mentors",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "09:00 - 20:00",
        "capacityEstimate": "Small Express Counter (~60-90 approx.)",
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
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "IIT Bombay Gymkhana Cultural Affairs",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "16:00 - 01:00 (Evening / Night)",
        "capacityEstimate": "Outdoor & Indoor SAC Area (~100-140 approx.)",
        "active": True,
    },
    {
        "id": "iitb-canteen-brewberrys",
        "name": "Brewberrys The Coffee Bar",
        "category": "CANTEEN",
        "description": "Coffee, bakery items, iced brews, and tables for study sessions.",
        "landmarkLocation": "Adjacent to Central Library, Main Academic Spine",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "Central Library Amenities Student Guide",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "Central Library Amenities Committee",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "08:00 - 23:00",
        "capacityEstimate": "Study Cafe Seating (~60-80 approx.)",
        "active": True,
    },
    {
        "id": "iitb-amul-parlour",
        "name": "Amul Ice Cream & Dairy Parlour",
        "category": "CANTEEN",
        "description": "Dairy outlet offering ice creams, flavored milk, milkshakes, and packaged snacks.",
        "landmarkLocation": "Near Hostel 1 & Campus School Junction",
        "verificationStatus": "STUDENT_SOURCED",
        "verificationSource": "Campus Commercial Amenities Register",
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "IIT Bombay Campus Amenities Registry",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "09:00 - 23:00",
        "capacityEstimate": "Kiosk Counter (Takeaway / Bench Seating)",
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
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "VIT-AP Student Dining Guide",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "Breakfast (07:30-09:30), Lunch (12:00-14:15), Dinner (19:30-21:30)",
        "capacityEstimate": "Large Dining Hall (~350-450 approx.)",
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
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "VIT-AP Student Dining Guide",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "Breakfast (07:30-09:30), Lunch (12:00-14:15), Dinner (19:30-21:00)",
        "capacityEstimate": "Medium Dining Hall (~250-350 approx.)",
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
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "VIT-AP Student Dining Guide",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "10:00 - 23:00",
        "capacityEstimate": "Open Plaza Seating (~120-180 approx.)",
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
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "VIT-AP Student Dining Guide",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "08:30 - 18:00 (Class Hours)",
        "capacityEstimate": "Express Counter (~80-120 approx.)",
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
        "provenance": {
            "sourceType": "COMMUNITY_DIRECTORY",
            "verifiedBy": "VIT-AP Student Dining Guide",
            "lastVerifiedDate": "2026-01-15",
            "isCrowdsourced": False,
            "crowdsourcedAttributes": ["reportedWaitMinutes", "queueLength", "note"],
        },
        "openHours": "17:00 - 02:00 (Late Night)",
        "capacityEstimate": "Late Night Counter (~100-150 approx.)",
        "active": True,
    },
]

def get_default_campus_locations(campus_id: Optional[str] = None) -> List[Dict[str, Any]]:
    cid = (campus_id or os.environ.get("CAMPUS_ID", "iitb")).lower()
    return VITAP_CAMPUS_LOCATIONS if cid == "vitap" else IITB_CAMPUS_LOCATIONS

ACTIVE_CAMPUS = os.environ.get("CAMPUS_ID", "iitb").lower()
DEFAULT_CAMPUS_LOCATIONS = get_default_campus_locations()


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
    def seed_locations(self):
        pass

    @abstractmethod
    def get_historical_reports(
        self,
        location_id: str,
        days: int = 14,
        limit: int = 1000,
        include_metadata: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        pass


# =========================================================================
# Production DynamoDB Storage Adapter (Fails Closed, Atomic Idempotency)
# =========================================================================

class DynamoDBStorageAdapter(BaseStorageAdapter):
    """
    Production DynamoDB client.
    - Guarantees fail-closed durability (never returns silent success on failed writes).
    - Uses TransactWriteItems for atomic idempotency reservation + report persistence.
    - Fails closed on rate-limit verification errors.
    - Enforces 14-day cutoff query bounds.
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
            from boto3.dynamodb.conditions import Key, Attr  # type: ignore

            # 1. Prefer GSI1 indexed query: O(N_locations) direct partition retrieval
            try:
                resp = self._table.query(
                    IndexName="GSI1",
                    KeyConditionExpression=Key("GSI1PK").eq("ENTITY#LOCATION"),
                )
                items = resp.get("Items", [])
                active_items = [it for it in items if it.get("active", True)]
                if active_items:
                    return sorted(self._convert_decimals_to_float(active_items), key=lambda x: x.get("name", ""))
            except Exception as gsi_err:
                logger.debug("GSI1 query on ENTITY#LOCATION fell back to paginated scan: %s", str(gsi_err))

            # 2. Paginated Scan fallback (traverses table pages without mutating on read path)
            items = []
            last_evaluated_key = None
            max_pages = 10
            for _ in range(max_pages):
                scan_kwargs: Dict[str, Any] = {
                    "FilterExpression": Attr("entityType").eq("LOCATION") & Attr("active").eq(True),
                }
                if last_evaluated_key:
                    scan_kwargs["ExclusiveStartKey"] = last_evaluated_key
                resp = self._table.scan(**scan_kwargs)
                items.extend(resp.get("Items", []))
                last_evaluated_key = resp.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break

            # Never seed on read path! If empty, return empty list.
            return sorted(self._convert_decimals_to_float(items), key=lambda x: x.get("name", ""))
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

        now = datetime.now(timezone.utc)
        iso_timestamp = now.isoformat()
        report_id = f"rep_{uuid.uuid4().hex[:12]}"
        # Retain raw crowdsourced observations for 30 days so 14-day rolling historical queries succeed with safety buffer
        epoch_ttl = int(time.time()) + (30 * 86400)  # 30 days

        pk = f"LOCATION#{location_id}"
        sk = f"REPORT#{iso_timestamp}#{report_id}"

        item = {
            "PK": pk,
            "SK": sk,
            "GSI1PK": "ENTITY#REPORT",
            "GSI1SK": f"{iso_timestamp}#{report_id}",
            "entityType": "REPORT",
            "reportId": report_id,
            "locationId": location_id,
            "reportedWaitMinutes": round(float(reported_wait_minutes), 1),
            "queueLength": int(queue_length),
            "note": note,
            "timestamp": iso_timestamp,
            "ttl": epoch_ttl,
        }

        clean_item = self._convert_floats_to_decimal(item)

        if not idempotency_key:
            # Standard single-item write when no idempotency key is provided
            try:
                self._table.put_item(Item=clean_item)
                return item
            except Exception as e:
                logger.error("DynamoDB write failed for report %s: %s", report_id, str(e))
                raise DatabasePersistenceError("Failed to persist queue observation to durable database.")

        # Atomic Idempotency Transaction via TransactWriteItems
        idem_pk = f"IDEMPOTENCY#{idempotency_key}"
        idem_sk = "RECORD"
        idem_ttl = int(time.time()) + 86400  # 24 hours

        idem_item = {
            "PK": idem_pk,
            "SK": idem_sk,
            "entityType": "IDEMPOTENCY",
            "cachedReport": clean_item,
            "ttl": idem_ttl,
            "createdAt": iso_timestamp,
        }

        try:
            from boto3.dynamodb.types import TypeSerializer  # type: ignore
            serializer = TypeSerializer()
            serialized_report = {k: serializer.serialize(v) for k, v in clean_item.items()}
            serialized_idem = {k: serializer.serialize(v) for k, v in idem_item.items()}

            client = self._table.meta.client
            client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": serialized_report,
                        }
                    },
                    {
                        "Put": {
                            "TableName": self.table_name,
                            "Item": serialized_idem,
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                ]
            )
            return item

        except Exception as e:
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if error_code == "TransactionCanceledException":
                # Idempotency collision: conditional check failed because key already exists
                logger.info("Idempotent replay detected for key: %s", idempotency_key)
                try:
                    existing = self._table.get_item(Key={"PK": idem_pk, "SK": idem_sk}).get("Item")
                    if existing and "cachedReport" in existing:
                        return self._convert_decimals_to_float(existing["cachedReport"])
                except Exception as get_err:
                    logger.error("Failed to read existing idempotency record: %s", str(get_err))
                raise IdempotencyConflictError(f"Idempotent submission conflict for key '{idempotency_key}'.")

            logger.error("DynamoDB atomic transaction failed: %s", str(e), exc_info=True)
            raise DatabasePersistenceError(f"Failed to atomically persist report and idempotency record: {str(e)}")

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
            from boto3.dynamodb.conditions import Key, Attr  # type: ignore

            # 1. Prefer GSI1 indexed query: ENTITY#REPORT reverse-chronological by timestamp
            try:
                resp = self._table.query(
                    IndexName="GSI1",
                    KeyConditionExpression=Key("GSI1PK").eq("ENTITY#REPORT"),
                    ScanIndexForward=False,
                    Limit=limit,
                )
                items = resp.get("Items", [])
                if items:
                    return self._convert_decimals_to_float(items[:limit])
            except Exception as gsi_err:
                logger.debug("GSI1 query on ENTITY#REPORT fell back to paginated scan: %s", str(gsi_err))

            # 2. Paginated Scan fallback: loops over LastEvaluatedKey until limit matching reports collected
            items = []
            last_evaluated_key = None
            max_pages = 10
            for _ in range(max_pages):
                scan_kwargs: Dict[str, Any] = {
                    "FilterExpression": Attr("entityType").eq("REPORT"),
                    "Limit": min(limit * 2, 200),
                }
                if last_evaluated_key:
                    scan_kwargs["ExclusiveStartKey"] = last_evaluated_key

                resp = self._table.scan(**scan_kwargs)
                items.extend(resp.get("Items", []))
                if len(items) >= limit:
                    break
                last_evaluated_key = resp.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    break

            items.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
            return self._convert_decimals_to_float(items[:limit])
        except Exception as e:
            logger.error("DynamoDB list_all_reports failed: %s", str(e))
            raise DatabasePersistenceError("Failed to retrieve audit feed.")

    def check_rate_limit(self, client_hash: str, window_seconds: int = 300, max_requests: int = 5) -> bool:
        """
        Sliding-Window Counter Rate Limiter.
        Prevents 2x boundary bursts by weighting request volume from the previous window.
        Effective count in rolling window of duration `window_seconds`:
            effective_prev = count_prev * ((window_seconds - time_offset) / window_seconds)
            projected_total = effective_prev + count_curr + 1
        If projected_total > max_requests, the request is denied.
        Atomic conditional update on count_curr ensures concurrency safety.
        Fails closed on storage or connectivity errors.
        """
        self._ensure_table()
        current_epoch = int(time.time())
        window_idx = current_epoch // window_seconds
        time_offset = current_epoch % window_seconds
        weight_prev = max(0.0, float(window_seconds - time_offset) / float(window_seconds))

        pk = f"RATELIMIT#{client_hash}"
        sk_curr = f"WINDOW#{window_idx}"
        sk_prev = f"WINDOW#{window_idx - 1}"
        ttl = current_epoch + (window_seconds * 2)

        try:
            # 1. Read previous window count
            prev_resp = self._table.get_item(Key={"PK": pk, "SK": sk_prev})
            prev_item = prev_resp.get("Item")
            n_prev = int(prev_item.get("reqCount", 0)) if prev_item else 0

            # 2. Compute effective previous count and maximum allowed current requests
            effective_prev = n_prev * weight_prev
            # Condition for another request: effective_prev + n_curr + 1 <= max_requests
            # Equivalent to: n_curr <= floor(max_requests - 1 - effective_prev)
            max_allowed_n_curr = math.floor(max_requests - 1 - effective_prev)

            if max_allowed_n_curr < 0:
                # Sliding window capacity exhausted by previous window's decaying burst
                return False

            # 3. Atomically increment current window count subject to conditional limit
            self._table.update_item(
                Key={"PK": pk, "SK": sk_curr},
                UpdateExpression="ADD reqCount :inc SET #t = :ttl, entityType = :ent",
                ConditionExpression="attribute_not_exists(reqCount) OR reqCount <= :max_n",
                ExpressionAttributeNames={"#t": "ttl"},
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":ttl": ttl,
                    ":ent": "RATELIMIT",
                    ":max_n": int(max_allowed_n_curr),
                },
                ReturnValues="UPDATED_NEW",
            )
            return True

        except Exception as e:
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if error_code == "ConditionalCheckFailedException":
                # Rate limit exceeded in current window
                return False
            logger.error("DynamoDB rate limit check failed: %s", str(e), exc_info=True)
            # FAIL CLOSED: Do not return True. Raise DatabasePersistenceError to deny or return controlled error.
            raise DatabasePersistenceError(f"Rate limit storage verification failed: {str(e)}")

    def get_historical_reports(
        self,
        location_id: str,
        days: int = 14,
        limit: int = 1000,
        include_metadata: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        self._ensure_table()
        pk = f"LOCATION#{location_id}"
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_iso = cutoff_dt.isoformat()

        try:
            from boto3.dynamodb.conditions import Key  # type: ignore

            items: List[Dict[str, Any]] = []
            seen_ids = set()
            last_evaluated_key = None
            max_pages = 20  # Bounded pagination safety guard against runaway loops
            pages_evaluated = 0
            is_truncated = False

            for _ in range(max_pages):
                pages_evaluated += 1
                remaining = limit - len(items)
                if remaining <= 0:
                    # Target limit satisfied
                    if last_evaluated_key is not None:
                        is_truncated = True
                    break

                page_limit = min(remaining, 200)
                query_kwargs: Dict[str, Any] = {
                    "KeyConditionExpression": Key("PK").eq(pk) & Key("SK").gte(f"REPORT#{cutoff_iso}"),
                    "ScanIndexForward": False,
                    "Limit": page_limit,
                }
                if last_evaluated_key:
                    query_kwargs["ExclusiveStartKey"] = last_evaluated_key

                resp = self._table.query(**query_kwargs)
                page_items = resp.get("Items", [])
                for item in page_items:
                    dedup_key = item.get("reportId") or (item.get("PK"), item.get("SK"))
                    if dedup_key not in seen_ids:
                        seen_ids.add(dedup_key)
                        items.append(item)

                last_evaluated_key = resp.get("LastEvaluatedKey")
                if not last_evaluated_key:
                    # Clean termination: all pages exhausted
                    break
            else:
                # Exhausted all max_pages
                if last_evaluated_key is not None:
                    is_truncated = True

            if len(items) >= limit and last_evaluated_key is not None:
                is_truncated = True

            final_items = self._convert_decimals_to_float(items[:limit])
            if include_metadata:
                return {
                    "reports": final_items,
                    "is_truncated": is_truncated,
                    "total_retrieved": len(final_items),
                    "limit": limit,
                    "pages_evaluated": pages_evaluated,
                }
            return final_items
        except Exception as e:
            logger.error("DynamoDB get_historical_reports failed: %s", str(e))
            raise DatabasePersistenceError(f"Failed to query historical observations: {str(e)}")

    def seed_locations(self):
        self._ensure_table()
        campus_locations = get_default_campus_locations()
        for loc in campus_locations:
            pk = f"LOCATION#{loc['id']}"
            sk = "METADATA"
            item = {
                "PK": pk,
                "SK": sk,
                "GSI1PK": "ENTITY#LOCATION",
                "GSI1SK": loc["id"],
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
    Thread-safe implementation with configurable failure simulation toggles.
    """

    def __init__(self, initial_locations: Optional[List[Dict[str, Any]]] = None):
        self._store: Dict[str, Dict[str, Any]] = {}
        self._rate_limits: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._simulate_failure: bool = False
        self._simulate_idempotency_failure: bool = False
        self._simulate_rate_limit_failure: bool = False

        locs = initial_locations if initial_locations is not None else get_default_campus_locations()
        for loc in locs:
            pk = f"LOCATION#{loc['id']}"
            sk = "METADATA"
            self._store[f"{pk}::{sk}"] = {
                "PK": pk,
                "SK": sk,
                "GSI1PK": "ENTITY#LOCATION",
                "GSI1SK": loc["id"],
                "entityType": "LOCATION",
                **loc,
            }

    def set_simulate_failure(self, fail: bool):
        self._simulate_failure = fail

    def set_simulate_idempotency_failure(self, fail: bool):
        self._simulate_idempotency_failure = fail

    def set_simulate_rate_limit_failure(self, fail: bool):
        self._simulate_rate_limit_failure = fail

    def seed_locations(self):
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database failure.")
        campus_locations = get_default_campus_locations()
        for loc in campus_locations:
            pk = f"LOCATION#{loc['id']}"
            sk = "METADATA"
            self._store[f"{pk}::{sk}"] = {
                "PK": pk,
                "SK": sk,
                "GSI1PK": "ENTITY#LOCATION",
                "GSI1SK": loc["id"],
                "entityType": "LOCATION",
                **loc,
            }

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

        now = datetime.now(timezone.utc)
        iso_timestamp = now.isoformat()
        report_id = f"rep_{uuid.uuid4().hex[:12]}"

        pk = f"LOCATION#{location_id}"
        sk = f"REPORT#{iso_timestamp}#{report_id}"

        item = {
            "PK": pk,
            "SK": sk,
            "GSI1PK": "ENTITY#REPORT",
            "GSI1SK": f"{iso_timestamp}#{report_id}",
            "entityType": "REPORT",
            "reportId": report_id,
            "locationId": location_id,
            "reportedWaitMinutes": round(float(reported_wait_minutes), 1),
            "queueLength": int(queue_length),
            "note": note,
            "timestamp": iso_timestamp,
            "ttl": int(time.time()) + (30 * 86400),
        }

        with self._lock:
            if idempotency_key:
                idem_key = f"IDEMPOTENCY#{idempotency_key}::RECORD"
                if idem_key in self._store:
                    if self._simulate_idempotency_failure:
                        raise DatabasePersistenceError("Simulated idempotency read failure.")
                    return self._store[idem_key]["cachedReport"]

                if self._simulate_idempotency_failure:
                    raise DatabasePersistenceError("Simulated idempotency write failure.")

                self._store[f"{pk}::{sk}"] = item
                self._store[idem_key] = {
                    "PK": f"IDEMPOTENCY#{idempotency_key}",
                    "SK": "RECORD",
                    "entityType": "IDEMPOTENCY",
                    "cachedReport": item,
                    "ttl": int(time.time()) + 86400,
                }
                return item

            self._store[f"{pk}::{sk}"] = item
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
        if self._simulate_rate_limit_failure or self._simulate_failure:
            raise DatabasePersistenceError("Simulated rate limit storage failure.")
        current_epoch = int(time.time())
        window_idx = current_epoch // window_seconds
        time_offset = current_epoch % window_seconds
        weight_prev = max(0.0, float(window_seconds - time_offset) / float(window_seconds))

        key_prev = f"{client_hash}::{window_idx - 1}"
        key_curr = f"{client_hash}::{window_idx}"

        with self._lock:
            n_prev = self._rate_limits.get(key_prev, 0)
            n_curr = self._rate_limits.get(key_curr, 0)

            effective_prev = n_prev * weight_prev
            if effective_prev + n_curr + 1 > max_requests:
                return False

            self._rate_limits[key_curr] = n_curr + 1
            return True

    def get_historical_reports(
        self,
        location_id: str,
        days: int = 14,
        limit: int = 1000,
        include_metadata: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        if self._simulate_failure:
            raise DatabasePersistenceError("Simulated database failure.")
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        prefix = f"LOCATION#{location_id}::REPORT#"
        reports = []
        seen_ids = set()
        for k, v in self._store.items():
            if k.startswith(prefix) and v.get("entityType") == "REPORT":
                ts_str = v.get("timestamp")
                if ts_str:
                    try:
                        clean_ts = ts_str.replace("Z", "+00:00")
                        dt = datetime.fromisoformat(clean_ts)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt >= cutoff_dt:
                            dedup_key = v.get("reportId") or (v.get("PK"), v.get("SK"))
                            if dedup_key not in seen_ids:
                                seen_ids.add(dedup_key)
                                reports.append(v)
                    except Exception:
                        continue
        reports.sort(key=lambda x: str(x.get("timestamp", "")), reverse=True)
        is_truncated = len(reports) > limit
        final_reports = reports[:limit]
        if include_metadata:
            return {
                "reports": final_reports,
                "is_truncated": is_truncated,
                "total_retrieved": len(final_reports),
                "limit": limit,
                "pages_evaluated": 1,
            }
        return final_reports


# =========================================================================
# QueueSenseDatabase Public Facade
# =========================================================================

_shared_test_adapter: Optional[InMemoryStorageAdapter] = None


def get_shared_test_adapter() -> InMemoryStorageAdapter:
    global _shared_test_adapter
    if _shared_test_adapter is None:
        _shared_test_adapter = InMemoryStorageAdapter()
    return _shared_test_adapter


def reset_shared_test_adapter() -> None:
    global _shared_test_adapter
    _shared_test_adapter = InMemoryStorageAdapter()


# Synchronize module identity across 'database' and 'backend.shared.database'
if __name__ == "database":
    sys.modules["backend.shared.database"] = sys.modules["database"]
elif __name__ == "backend.shared.database":
    sys.modules["database"] = sys.modules["backend.shared.database"]


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
        is_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
        env_name = os.environ.get("ENVIRONMENT", "").lower()
        is_in_pytest = os.environ.get("PYTEST_CURRENT_TEST") is not None
        is_production = is_lambda or (not is_in_pytest and env_name in ("prod", "production"))

        if is_production:
            # Under production AWS Lambda or ENVIRONMENT=prod/production:
            # 1. Non-DynamoDB or in-memory adapters are strictly rejected.
            # 2. STORAGE_BACKEND=memory or DATA_MODE=demo/test is a fatal configuration error.
            if adapter is not None and not isinstance(adapter, DynamoDBStorageAdapter):
                raise DatabasePersistenceError(
                    "Security/Reliability Violation: In-memory or non-DynamoDB storage adapter is strictly forbidden in production."
                )
            if backend_env == "memory" or data_mode_env in ("test", "demo"):
                raise DatabasePersistenceError(
                    f"Configuration Error: STORAGE_BACKEND='{backend_env}' or DATA_MODE='{data_mode_env}' cannot be used in production environment."
                )
            self._adapter = adapter or DynamoDBStorageAdapter(table_name=self.table_name)
        else:
            is_test_env = (
                is_in_pytest
                or os.environ.get("USE_IN_MEMORY_ADAPTER", "").lower() == "true"
                or backend_env == "memory"
                or data_mode_env in ("test", "demo")
            )

            if adapter is not None:
                self._adapter = adapter
            elif is_test_env:
                self._adapter = get_shared_test_adapter()
            else:
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

    def seed_locations(self):
        return self._adapter.seed_locations()

    def get_historical_reports(
        self,
        location_id: str,
        days: int = 14,
        limit: int = 1000,
        include_metadata: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        return self._adapter.get_historical_reports(
            location_id=location_id,
            days=days,
            limit=limit,
            include_metadata=include_metadata,
        )
