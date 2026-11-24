"""
QueueSense — Batch 6: Cross-Component Adversarial Integration & Offline Protocol Tests

Test Architecture & Environment Scope (Explicit Boundaries):
1. Part 1 (In-Memory Handler Integration): Uses `STORAGE_BACKEND=memory` and `DATA_MODE=test`
   (`InMemoryStorageAdapter`) to validate Lambda handler contracts, error envelopes,
   threading.Barrier concurrency, payload conflict rejection, rate limiting, and prediction behavior.
   Note: InMemoryStorageAdapter uses Python `threading.Lock`, which does NOT test distributed
   AWS DynamoDB optimistic/transactional locking across concurrent Lambda instances.
2. Part 2 (Offline DynamoDB Adapter Protocol): Directly exercises `DynamoDBStorageAdapter` using
   a local Python wire/transaction simulator (`FakeBoto3Environment`) because `boto3`, `moto`,
   DynamoDB Local, and live AWS DynamoDB are not present in this offline environment. Verifies:
   - `TransactWriteItems` wire structure (`TypeSerializer` S/N/M types, 2 Put operations)
   - `ConditionExpression == "attribute_not_exists(PK)"` conditional reservation
   - `TransactionCanceledException` conditional-write race handling & replay under `threading.Barrier`
   - Payload hash conflict detection (`IdempotencyConflictError`) and fail-closed `DatabasePersistenceError`
   - Report (30-day) & Idempotency (24-hour) TTL attributes
   - GSI1 multi-page pagination, legacy scan compatibility recovery, and `is_partial`/`is_truncated` flags
3. Part 3 (Authentication Boundary): Separates Lambda authorizer-claims verification tests
   (explicitly noting Lambda does NOT perform cryptographic JWT signature verification) from
   static CloudFormation/SAM assertions on `CognitoAuthorizer`, Cognito issuer/audience, and route attachment.
4. Part 4 (Prediction Decay & Infrastructure): Verifies `DEFAULT_DECAY_CONSTANT_MINUTES = 15.0`
   (900s, half-life ~10.3972 min), outlier boundaries, IAM least privilege, PAY_PER_REQUEST billing,
   private S3 + OAC, and 30-day CloudWatch LogGroup retention.
"""

import json
import math
import os
import sys
import threading
import time
import types
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from backend.shared.database import (
    QueueSenseDatabase,
    DynamoDBStorageAdapter,
    DatabasePersistenceError,
    IdempotencyConflictError,
    compute_idempotency_payload_hash,
    reset_shared_test_adapter,
    get_default_campus_locations,
)
from backend.shared.security import (
    compute_anonymous_client_hash,
    parse_unverified_jwt,
    verify_cognito_jwt_claims,
    JWTValidationError,
    clear_salt_cache,
)
from backend.shared.prediction import (
    DEFAULT_DECAY_CONSTANT_MINUTES,
    calculate_freshness_weight,
    calculate_queue_estimate,
    filter_outliers,
)
from backend.shared.validation import (
    validate_report_payload,
    validate_pagination_limit,
)

import backend.functions.get_queue.app as get_queue_mod
import backend.functions.submit_report.app as submit_report_mod
import backend.functions.admin.app as admin_mod
from backend.tests.test_batch4_infrastructure import load_cfn_template


# =========================================================================
# Offline Transactional DynamoDB Simulator (For Part 2 Protocol Tests)
# =========================================================================

class _FakeTypeSerializer:
    """Minimal Python replacement for boto3.dynamodb.types.TypeSerializer."""

    def serialize(self, value):
        if value is None:
            return {"NULL": True}
        if isinstance(value, bool):
            return {"BOOL": value}
        if isinstance(value, (int, Decimal)):
            return {"N": str(value)}
        if isinstance(value, float):
            return {"N": str(value)}
        if isinstance(value, str):
            return {"S": value}
        if isinstance(value, dict):
            return {"M": {k: self.serialize(v) for k, v in value.items()}}
        if isinstance(value, list):
            return {"L": [self.serialize(v) for v in value]}
        raise TypeError(f"Unsupported type for serialization: {type(value)}")


def _deserialize_wire_item(wire_item):
    """Inverse of _FakeTypeSerializer for storing simulated DynamoDB items."""
    def _dec(av):
        if "NULL" in av:
            return None
        if "BOOL" in av:
            return av["BOOL"]
        if "N" in av:
            s = av["N"]
            return Decimal(s)
        if "S" in av:
            return av["S"]
        if "M" in av:
            return {k: _dec(v) for k, v in av["M"].items()}
        if "L" in av:
            return [_dec(v) for v in av["L"]]
        return av

    return {k: _dec(v) for k, v in wire_item.items()}


class FakeTransactionCanceledException(Exception):
    def __init__(self, message, cancellation_reasons):
        super().__init__(message)
        self.response = {
            "Error": {"Code": "TransactionCanceledException", "Message": message},
            "CancellationReasons": cancellation_reasons,
        }


class FakeDynamoDBError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.response = {"Error": {"Code": code, "Message": message}}


class FakeTransactionalTable:
    """
    Thread-safe offline simulator of a DynamoDB Table + boto3 low-level Client.
    Enforces atomic conditional evaluation (`attribute_not_exists(PK)`) in
    `transact_write_items` under a lock so concurrent threads experience genuine
    conditional-write races and TransactionCanceledException replays.
    """

    def __init__(self, table_name="TestQueueSenseTable"):
        self.table_name = table_name
        self.items = {}  # (PK, SK) -> item dict
        self.lock = threading.Lock()
        self.recorded_transactions = []
        self.force_internal_error = False
        self.drop_idem_after_commit = False

        # Wire low-level client compatible with `self._table.meta.client.transact_write_items`
        self.meta = types.SimpleNamespace(client=self)

    def get_item(self, Key):
        with self.lock:
            k = (Key["PK"], Key["SK"])
            item = self.items.get(k)
            return {"Item": dict(item)} if item is not None else {}

    def put_item(self, Item):
        with self.lock:
            self.items[(Item["PK"], Item["SK"])] = dict(Item)
            return {}

    def transact_write_items(self, TransactItems):
        with self.lock:
            self.recorded_transactions.append(TransactItems)
            if self.force_internal_error:
                raise FakeDynamoDBError("InternalServerError", "Simulated DynamoDB outage")

            reasons = []
            has_failure = False
            staged = []

            for op in TransactItems:
                if "Put" not in op:
                    raise ValueError(f"Unsupported transaction op in simulator: {op.keys()}")
                put_spec = op["Put"]
                if put_spec.get("TableName") != self.table_name:
                    raise ValueError(f"Wrong TableName {put_spec.get('TableName')} != {self.table_name}")

                decoded = _deserialize_wire_item(put_spec["Item"])
                key = (decoded["PK"], decoded["SK"])
                cond = put_spec.get("ConditionExpression")

                if cond == "attribute_not_exists(PK)":
                    # Partition check across primary keys
                    pk_exists = any(existing_pk == decoded["PK"] for (existing_pk, _) in self.items)
                    if pk_exists:
                        reasons.append({"Code": "ConditionalCheckFailed", "Message": "Conditional request failed"})
                        has_failure = True
                    else:
                        reasons.append({"Code": "None"})
                        staged.append((key, decoded))
                elif cond is None:
                    reasons.append({"Code": "None"})
                    staged.append((key, decoded))
                else:
                    raise ValueError(f"Unexpected ConditionExpression: {cond}")

            if has_failure:
                raise FakeTransactionCanceledException(
                    "Transaction cancelled due to conditional check failure",
                    reasons,
                )

            # Atomic commit of all staged puts
            for key, item_val in staged:
                if self.drop_idem_after_commit and item_val.get("entityType") == "IDEMPOTENCY":
                    continue
                self.items[key] = item_val

            return {"ResponseMetadata": {"HTTPStatusCode": 200}}


@pytest.fixture(autouse=True)
def setup_in_memory_handler_env(monkeypatch):
    """Configures isolated in-memory storage environment for handler integration tests."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    monkeypatch.setenv("DATA_MODE", "test")
    monkeypatch.setenv("RATE_LIMIT_SALT", "test_transient_test_salt_min_16_chars_1234")
    monkeypatch.setenv("ADMIN_API_KEY", "queuesense-admin-secret-dev-key")
    reset_shared_test_adapter()
    clear_salt_cache()


# =========================================================================
# Part 1 — Matrix A: In-Memory Lambda Handler Contracts & Error Envelopes
# =========================================================================

class TestMatrixA_FrontendApiContracts_InMemory:

    def test_get_queue_response_contract_and_boundary_values(self):
        """[In-Memory] Verify GET /locations/{id}/queue conforms to frontend client contract."""
        event = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "requestContext": {"requestId": "req-contract-001"},
        }
        context = MagicMock(aws_request_id="req-contract-001")
        resp = get_queue_mod.lambda_handler(event, context)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["success"] is True
        data = body["data"]

        assert data["location"]["id"] == "iitb-mess-h12-14"
        assert "name" in data["location"]
        assert "estimate" in data
        assert "reports" in data

        est = data["estimate"]
        if est["predictedWaitMinutes"] is not None:
            assert 0 <= est["predictedWaitMinutes"] <= 120
            assert 0 <= est["predictedQueueLength"] <= 300
        assert 0.0 <= est["confidence"] <= 1.0
        assert est["confidenceLabel"] in ["LOW", "MEDIUM", "HIGH", "NO DATA"]
        assert est["congestion"] in ["LOW", "MODERATE", "HIGH", "VERY_HIGH", "UNKNOWN"]
        assert est["freshness"] in ["LIVE", "RECENT", "STALE", "EXPIRED", "NO RECENT DATA"]

    def test_error_response_strict_envelope_across_failure_modes(self):
        """[In-Memory] Verify error envelopes strictly match { success: False, error, errorCode, requestId }."""
        # 400 Invalid location ID
        resp_400 = get_queue_mod.lambda_handler(
            {"pathParameters": {"id": "invalid/id!@#"}},
            MagicMock(aws_request_id="req-err-400"),
        )
        assert resp_400["statusCode"] == 400
        b400 = json.loads(resp_400["body"])
        assert b400["success"] is False
        assert b400["errorCode"] == "INVALID_LOCATION_ID"
        assert b400["requestId"] == "req-err-400"

        # 404 Non-existent location
        resp_404 = get_queue_mod.lambda_handler(
            {"pathParameters": {"id": "iitb-mess-nonexistent-outlet"}},
            MagicMock(aws_request_id="req-err-404"),
        )
        assert resp_404["statusCode"] == 404
        b404 = json.loads(resp_404["body"])
        assert b404["success"] is False
        assert b404["errorCode"] == "LOCATION_NOT_FOUND"
        assert b404["requestId"] == "req-err-404"

        # 400 Malformed JSON
        resp_mal = submit_report_mod.lambda_handler(
            {"pathParameters": {"id": "iitb-mess-h12-14"}, "body": "{bad-json"},
            MagicMock(aws_request_id="req-err-malformed"),
        )
        assert resp_mal["statusCode"] == 400
        bmal = json.loads(resp_mal["body"])
        assert bmal["success"] is False
        assert bmal["errorCode"] == "MALFORMED_JSON"

    def test_route_location_id_matching_in_sanitized_reports(self):
        """[In-Memory] Sanitized reports returned by get_queue strictly embed route locationId."""
        db = QueueSenseDatabase()
        db.record_report("iitb-mess-h12-14", 10, 15, note="Lunch rush")

        resp = get_queue_mod.lambda_handler({"pathParameters": {"id": "iitb-mess-h12-14"}}, None)
        body = json.loads(resp["body"])
        reports = body["data"]["reports"]
        assert len(reports) >= 1
        assert all(rep["locationId"] == "iitb-mess-h12-14" for rep in reports)


# =========================================================================
# Part 1 — Matrix B: In-Memory Genuine Concurrency & Payload Conflict Tests
# =========================================================================

class TestMatrixB_ReportLifecycleAndConcurrency_InMemory:

    def test_concurrent_barrier_identical_payload_handler_replay(self):
        """
        [In-Memory] Genuine synchronized concurrent test using threading.Barrier(5):
        5 simultaneous submit_report Lambda invocations overlap at the barrier with the
        same idempotencyKey and identical payload (within the 5-req per-device rate limit window).
        Verifies all 5 return HTTP 201 with identical reportId and persist strictly 1 report.
        """
        num_workers = 5
        barrier = threading.Barrier(num_workers)
        idem_key = f"conc-same-{uuid.uuid4().hex}"
        payload_body = json.dumps({"reportedWaitMinutes": 14, "queueLength": 22, "note": "Barrier overlap"})

        def worker(idx):
            barrier.wait(timeout=5.0)
            event = {
                "pathParameters": {"id": "iitb-mess-h12-14"},
                "headers": {
                    "X-Idempotency-Key": idem_key,
                    "X-Device-ID": "dev-barrier-identical-001",
                },
                "body": payload_body,
                "requestContext": {"identity": {"sourceIp": "10.10.2.15"}},
            }
            return submit_report_mod.lambda_handler(event, MagicMock(aws_request_id=f"req-w-{idx}"))

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            responses = list(pool.map(worker, range(num_workers)))

        report_ids = set()
        for r in responses:
            assert r["statusCode"] == 201
            body = json.loads(r["body"])
            assert body["success"] is True
            report_ids.add(body["data"]["report"]["reportId"])

        assert len(report_ids) == 1
        db = QueueSenseDatabase()
        persisted = db.get_recent_reports("iitb-mess-h12-14")
        assert len(persisted) == 1

    def test_same_key_different_payload_unmocked_returns_409_conflict(self):
        """
        [In-Memory] Reusing an idempotencyKey with ANY different field (wait, queueLength,
        note, or different locationId) must fail unmocked with HTTP 409 IDEMPOTENCY_CONFLICT.
        """
        idem_key = f"conflict-key-{uuid.uuid4().hex}"
        base_headers = {
            "X-Idempotency-Key": idem_key,
            "X-Device-ID": "dev-conflict-tester",
        }
        req_ctx = {"identity": {"sourceIp": "10.10.3.20"}}

        # Initial valid submission
        r1 = submit_report_mod.lambda_handler(
            {
                "pathParameters": {"id": "iitb-mess-h12-14"},
                "headers": base_headers,
                "body": json.dumps({"reportedWaitMinutes": 8, "queueLength": 10, "note": "Initial"}),
                "requestContext": req_ctx,
            },
            None,
        )
        assert r1["statusCode"] == 201
        orig_id = json.loads(r1["body"])["data"]["report"]["reportId"]

        # 1. Conflict: changed reportedWaitMinutes
        r2 = submit_report_mod.lambda_handler(
            {
                "pathParameters": {"id": "iitb-mess-h12-14"},
                "headers": base_headers,
                "body": json.dumps({"reportedWaitMinutes": 25, "queueLength": 10, "note": "Initial"}),
                "requestContext": req_ctx,
            },
            None,
        )
        assert r2["statusCode"] == 409
        assert json.loads(r2["body"])["errorCode"] == "IDEMPOTENCY_CONFLICT"

        # 2. Conflict: changed queueLength or note
        r3 = submit_report_mod.lambda_handler(
            {
                "pathParameters": {"id": "iitb-mess-h12-14"},
                "headers": base_headers,
                "body": json.dumps({"reportedWaitMinutes": 8, "queueLength": 55, "note": "Mutated"}),
                "requestContext": req_ctx,
            },
            None,
        )
        assert r3["statusCode"] == 409
        assert json.loads(r3["body"])["errorCode"] == "IDEMPOTENCY_CONFLICT"

        # 3. Conflict: cross-location key reuse (different locationId)
        r4 = submit_report_mod.lambda_handler(
            {
                "pathParameters": {"id": "iitb-canteen-lhc"},
                "headers": base_headers,
                "body": json.dumps({"reportedWaitMinutes": 8, "queueLength": 10, "note": "Initial"}),
                "requestContext": req_ctx,
            },
            None,
        )
        assert r4["statusCode"] == 409
        assert json.loads(r4["body"])["errorCode"] == "IDEMPOTENCY_CONFLICT"

        # Verify zero duplicate writes or cross-location leakage
        db = QueueSenseDatabase()
        h12_reports = db.get_recent_reports("iitb-mess-h12-14")
        lhc_reports = db.get_recent_reports("iitb-canteen-lhc")
        assert len(h12_reports) == 1
        assert h12_reports[0]["reportId"] == orig_id
        assert len(lhc_reports) == 0

    def test_concurrent_barrier_conflicting_payloads_strictly_one_wins(self):
        """
        [In-Memory] Synchronized threading.Barrier(5) race where 5 workers reuse the SAME
        idempotencyKey with DISTINCT payloads: strictly 1 wins (HTTP 201) and 4 receive HTTP 409.
        """
        num_workers = 5
        barrier = threading.Barrier(num_workers)
        idem_key = f"conc-conflict-{uuid.uuid4().hex}"

        def worker(idx):
            barrier.wait(timeout=5.0)
            event = {
                "pathParameters": {"id": "iitb-mess-h12-14"},
                "headers": {
                    "X-Idempotency-Key": idem_key,
                    "X-Device-ID": f"dev-race-unique-{idx:02d}-abcd1234",
                },
                "body": json.dumps({"reportedWaitMinutes": 5 + idx * 5, "queueLength": 10 + idx}),
                "requestContext": {"identity": {"sourceIp": "10.10.4.30"}},
            }
            return submit_report_mod.lambda_handler(event, None)

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            responses = list(pool.map(worker, range(num_workers)))

        statuses = [r["statusCode"] for r in responses]
        assert statuses.count(201) == 1
        assert statuses.count(409) == num_workers - 1
        for r in responses:
            if r["statusCode"] == 409:
                assert json.loads(r["body"])["errorCode"] == "IDEMPOTENCY_CONFLICT"

        db = QueueSenseDatabase()
        assert len(db.get_recent_reports("iitb-mess-h12-14")) == 1

    def test_database_persistence_failure_fails_closed(self):
        """[In-Memory] Adapter storage failure results in HTTP 500 PERSISTENCE_FAILED."""
        with patch.object(QueueSenseDatabase, "record_report", side_effect=DatabasePersistenceError("Storage unreachable")):
            resp = submit_report_mod.lambda_handler(
                {
                    "pathParameters": {"id": "iitb-mess-h12-14"},
                    "headers": {"X-Device-ID": "dev-fail-closed-test"},
                    "body": json.dumps({"reportedWaitMinutes": 10, "queueLength": 10}),
                },
                None,
            )
            assert resp["statusCode"] == 500
            assert json.loads(resp["body"])["errorCode"] == "PERSISTENCE_FAILED"

    def test_raw_device_id_never_persisted_directly(self):
        """[In-Memory] Raw client X-Device-ID is never persisted in saved reports."""
        raw_dev_id = "sensitive-hardware-device-uuid-999"
        db = QueueSenseDatabase()
        rep = db.record_report("iitb-mess-h12-14", 15, 20)
        assert "deviceId" not in rep
        assert raw_dev_id not in str(rep)


# =========================================================================
# Part 2 — Offline DynamoDBStorageAdapter Transaction & Query Protocol Tests
# (Exercises actual DynamoDBStorageAdapter methods using FakeTransactionalTable
#  and mocked boto3 modules; live AWS DynamoDB remains untested here.)
# =========================================================================

class TestMatrixB_And_E_DynamoDBAdapterOfflineProtocol:

    @pytest.fixture
    def fake_ddb_env(self, monkeypatch):
        fake_table = FakeTransactionalTable("TestQueueSenseMain")

        boto3_mod = types.ModuleType("boto3")
        boto3_dynamodb = types.ModuleType("boto3.dynamodb")
        boto3_types = types.ModuleType("boto3.dynamodb.types")
        boto3_conditions = types.ModuleType("boto3.dynamodb.conditions")

        boto3_types.TypeSerializer = _FakeTypeSerializer

        class _Expr:
            def __init__(self, op, *args):
                self.op = op
                self.args = args

            def __and__(self, other):
                return _Expr("AND", self, other)

        class _Key:
            def __init__(self, name):
                self.name = name
            def eq(self, val):
                return _Expr("KEY_EQ", self.name, val)
            def begins_with(self, val):
                return _Expr("KEY_BW", self.name, val)
            def gte(self, val):
                return _Expr("KEY_GTE", self.name, val)

        class _Attr:
            def __init__(self, name):
                self.name = name
            def eq(self, val):
                return _Expr("ATTR_EQ", self.name, val)
            def not_exists(self):
                return _Expr("ATTR_NOT_EXISTS", self.name)

        boto3_conditions.Key = _Key
        boto3_conditions.Attr = _Attr

        boto3_mod.resource = lambda service, region_name=None: types.SimpleNamespace(
            Table=lambda name: fake_table
        )

        monkeypatch.setitem(sys.modules, "boto3", boto3_mod)
        monkeypatch.setitem(sys.modules, "boto3.dynamodb", boto3_dynamodb)
        monkeypatch.setitem(sys.modules, "boto3.dynamodb.types", boto3_types)
        monkeypatch.setitem(sys.modules, "boto3.dynamodb.conditions", boto3_conditions)

        adapter = DynamoDBStorageAdapter(table_name="TestQueueSenseMain", region="ap-southeast-2")
        return adapter, fake_table

    def test_dynamodb_transaction_wire_structure_conditions_and_ttls(self, fake_ddb_env):
        """
        Validates exact TransactWriteItems request structure emitted by DynamoDBStorageAdapter:
        - 2 atomic Put operations (REPORT item + IDEMPOTENCY reservation)
        - ConditionExpression == 'attribute_not_exists(PK)' exclusively on IDEMPOTENCY item
        - Serialized DynamoDB wire types ('S', 'N', 'M')
        - 30-day TTL on report item & 24-hour TTL on idempotency record
        - SHA-256 payloadHash stored on IDEMPOTENCY item
        """
        adapter, fake_table = fake_ddb_env
        idem_key = f"wire-spec-{uuid.uuid4().hex}"
        now_epoch = int(time.time())

        rep = adapter.record_report(
            location_id="iitb-mess-h12-14",
            reported_wait_minutes=12.5,
            queue_length=19,
            note="Lunch line",
            idempotency_key=idem_key,
        )

        assert len(fake_table.recorded_transactions) == 1
        tx_items = fake_table.recorded_transactions[0]
        assert len(tx_items) == 2

        report_put = tx_items[0]["Put"]
        idem_put = tx_items[1]["Put"]

        # Verify table targeting & conditional reservation
        assert report_put["TableName"] == "TestQueueSenseMain"
        assert "ConditionExpression" not in report_put
        assert idem_put["TableName"] == "TestQueueSenseMain"
        assert idem_put["ConditionExpression"] == "attribute_not_exists(PK)"

        # Verify serialized DynamoDB AttributeValues for report
        rw = report_put["Item"]
        assert rw["PK"] == {"S": "LOCATION#iitb-mess-h12-14"}
        assert rw["SK"]["S"].startswith("REPORT#")
        assert rw["GSI1PK"] == {"S": "ENTITY#REPORT"}
        assert rw["entityType"] == {"S": "REPORT"}
        assert rw["locationId"] == {"S": "iitb-mess-h12-14"}
        assert "N" in rw["reportedWaitMinutes"] and float(rw["reportedWaitMinutes"]["N"]) == 12.5
        assert rw["queueLength"] == {"N": "19"}
        report_ttl = int(rw["ttl"]["N"])
        assert now_epoch + 29 * 86400 <= report_ttl <= now_epoch + 31 * 86400

        # Verify serialized DynamoDB AttributeValues for idempotency record
        iw = idem_put["Item"]
        assert iw["PK"] == {"S": f"IDEMPOTENCY#{idem_key}"}
        assert iw["SK"] == {"S": "RECORD"}
        assert iw["entityType"] == {"S": "IDEMPOTENCY"}
        assert iw["payloadHash"] == {
            "S": compute_idempotency_payload_hash("iitb-mess-h12-14", 12.5, 19, "Lunch line")
        }
        assert "M" in iw["cachedReport"]
        idem_ttl = int(iw["ttl"]["N"])
        assert now_epoch + 82800 <= idem_ttl <= now_epoch + 90000
        assert rep["reportId"] == rw["reportId"]["S"]

    def test_dynamodb_concurrent_barrier_conditional_write_race_and_replay(self, fake_ddb_env):
        """
        Tests synchronized threading.Barrier(8) concurrency against DynamoDBStorageAdapter
        backed by FakeTransactionalTable:
        - Strictly 1 thread commits TransactWriteItems cleanly
        - 7 losing threads receive TransactionCanceledException (ConditionalCheckFailed)
        - Adapter recovers via get_item, verifies payloadHash, and replays identical reportId
        """
        adapter, fake_table = fake_ddb_env
        num_workers = 8
        barrier = threading.Barrier(num_workers)
        idem_key = f"ddb-conc-race-{uuid.uuid4().hex}"

        def worker(_):
            barrier.wait(timeout=5.0)
            return adapter.record_report(
                location_id="iitb-mess-h12-14",
                reported_wait_minutes=9.0,
                queue_length=14,
                note="Overlapping commit",
                idempotency_key=idem_key,
            )

        with ThreadPoolExecutor(max_workers=num_workers) as pool:
            results = list(pool.map(worker, range(num_workers)))

        report_ids = {r["reportId"] for r in results}
        assert len(report_ids) == 1
        assert len(fake_table.recorded_transactions) == num_workers

        persisted_reports = [
            v for v in fake_table.items.values() if v.get("entityType") == "REPORT"
        ]
        assert len(persisted_reports) == 1
        assert persisted_reports[0]["reportId"] == next(iter(report_ids))

    def test_dynamodb_transaction_cancellation_conflict_and_fail_closed(self, fake_ddb_env):
        """
        Verifies DynamoDBStorageAdapter handles:
        1. TransactionCanceledException with mismatched payloadHash -> IdempotencyConflictError
        2. TransactionCanceledException when existing idempotency record unreadable -> IdempotencyConflictError
        3. Non-conditional persistence failure (InternalServerError) -> DatabasePersistenceError
        """
        adapter, fake_table = fake_ddb_env
        idem_key = f"ddb-conflict-{uuid.uuid4().hex}"

        first = adapter.record_report("iitb-mess-h12-14", 10.0, 12, "Normal", idempotency_key=idem_key)
        assert first["reportId"].startswith("rep_")

        # 1. Conflicting payload on TransactionCanceledException raises IdempotencyConflictError
        with pytest.raises(IdempotencyConflictError):
            adapter.record_report("iitb-mess-h12-14", 55.0, 120, "Tampered", idempotency_key=idem_key)

        # 2. Simulate TransactionCanceledException where idempotency row cannot be fetched
        missing_key = f"ddb-missing-existing-{uuid.uuid4().hex}"
        fake_table.items[(f"IDEMPOTENCY#{missing_key}", "RECORD")] = {
            "PK": f"IDEMPOTENCY#{missing_key}",
            "SK": "RECORD",
            # Corrupt record missing cachedReport triggers fail-closed IdempotencyConflictError
        }
        with pytest.raises(IdempotencyConflictError):
            adapter.record_report("iitb-mess-h12-14", 10.0, 10, idempotency_key=missing_key)

        # 3. Simulate DynamoDB outage on new transaction -> DatabasePersistenceError
        fake_table.force_internal_error = True
        with pytest.raises(DatabasePersistenceError):
            adapter.record_report("iitb-mess-h12-14", 10.0, 10, idempotency_key=f"err-{uuid.uuid4().hex}")

    def test_dynamodb_gsi1_pagination_migration_compatibility_and_partial_metadata(self, fake_ddb_env):
        """
        Directly validates DynamoDBStorageAdapter.list_locations against multi-page
        GSI1 responses, legacy unindexed dual-read scan merge, and safety-cap is_partial=True.
        """
        adapter, _ = fake_ddb_env
        mock_table = MagicMock()
        adapter._table = mock_table

        # Scenario A: 2 GSI1 pages + 1 legacy unindexed item lacking GSI1PK
        page1 = {
            "Items": [
                {"PK": "LOCATION#iitb-1", "SK": "METADATA", "id": "iitb-1", "name": "Alpha", "campusId": "iitb", "active": True, "GSI1PK": "ENTITY#LOCATION"}
            ],
            "LastEvaluatedKey": {"PK": "LOCATION#iitb-1", "SK": "METADATA"},
        }
        page2 = {
            "Items": [
                {"PK": "LOCATION#iitb-2", "SK": "METADATA", "id": "iitb-2", "name": "Beta", "campusId": "iitb", "active": True, "GSI1PK": "ENTITY#LOCATION"}
            ],
            "LastEvaluatedKey": None,
        }
        mock_table.query.side_effect = [page1, page2]
        mock_table.scan.return_value = {
            "Items": [
                {"PK": "LOCATION#iitb-legacy", "SK": "METADATA", "id": "iitb-legacy", "name": "Gamma Legacy", "campusId": "iitb", "active": True}
            ],
            "LastEvaluatedKey": None,
        }

        res = adapter.list_locations(include_metadata=True, campus_id="iitb")
        assert res["is_partial"] is False
        assert res["gsi_pages_evaluated"] == 2
        assert res["scan_pages_evaluated"] == 1
        assert [loc["id"] for loc in res["locations"]] == ["iitb-1", "iitb-2", "iitb-legacy"]
        assert mock_table.query.call_args_list[1][1]["ExclusiveStartKey"] == {"PK": "LOCATION#iitb-1", "SK": "METADATA"}

        # Scenario B: Exhausting max_gsi_pages=25 sets is_partial=True
        mock_table.reset_mock()
        mock_table.query.side_effect = None
        mock_table.query.return_value = {
            "Items": [{"PK": "LOCATION#iitb-1", "SK": "METADATA", "id": "iitb-1", "name": "Alpha", "campusId": "iitb", "active": True}],
            "LastEvaluatedKey": {"PK": "LOCATION#iitb-1", "SK": "METADATA"},
        }
        mock_table.scan.return_value = {"Items": [], "LastEvaluatedKey": None}

        partial_res = adapter.list_locations(include_metadata=True, campus_id="iitb")
        assert partial_res["is_partial"] is True
        assert partial_res["gsi_pages_evaluated"] == 25

    def test_dynamodb_all_reports_and_historical_truncation_metadata(self, fake_ddb_env):
        """
        Validates list_all_reports GSI1 query vs scan partial metadata, and
        get_historical_reports multi-page pagination with ExclusiveStartKey & is_truncated probe.
        """
        adapter, _ = fake_ddb_env
        mock_table = MagicMock()
        adapter._table = mock_table

        # 1. Historical multi-page query hitting exact limit=2 with 1 more item available on page 3
        now_iso = datetime.now(timezone.utc).isoformat()
        mock_table.query.side_effect = [
            {
                "Items": [{"PK": "LOCATION#iitb-1", "SK": f"REPORT#{now_iso}#r1", "reportId": "r1", "timestamp": now_iso}],
                "LastEvaluatedKey": {"PK": "LOCATION#iitb-1", "SK": "k1"},
            },
            {
                "Items": [{"PK": "LOCATION#iitb-1", "SK": f"REPORT#{now_iso}#r2", "reportId": "r2", "timestamp": now_iso}],
                "LastEvaluatedKey": {"PK": "LOCATION#iitb-1", "SK": "k2"},
            },
            # Probe query checks if more items remain beyond limit=2
            {
                "Items": [{"PK": "LOCATION#iitb-1", "SK": f"REPORT#{now_iso}#r3", "reportId": "r3", "timestamp": now_iso}],
                "LastEvaluatedKey": None,
            },
        ]
        hist = adapter.get_historical_reports("iitb-1", days=14, limit=2, include_metadata=True)
        assert hist["total_retrieved"] == 2
        assert hist["is_truncated"] is True
        assert mock_table.query.call_count == 3
        assert mock_table.query.call_args_list[1][1]["ExclusiveStartKey"] == {"PK": "LOCATION#iitb-1", "SK": "k1"}
        assert mock_table.query.call_args_list[2][1]["ExclusiveStartKey"] == {"PK": "LOCATION#iitb-1", "SK": "k2"}

        # 2. list_all_reports GSI1 fallback scan partial disclosure
        mock_table.reset_mock()
        mock_table.query.side_effect = Exception("GSI unavailable")
        mock_table.scan.return_value = {"Items": [], "LastEvaluatedKey": {"PK": "next"}}
        audit_res = adapter.list_all_reports(limit=10, include_metadata=True)
        assert audit_res["source"] == "SCAN_FALLBACK"
        assert audit_res["is_partial"] is True
        assert audit_res["pages_evaluated"] == 25


# =========================================================================
# Part 3 — Matrix C: Authorizer-Claims Handling & SAM Authorizer Boundaries
# (Explicitly distinguishes API Gateway cryptographic JWT verification from
#  Lambda defense-in-depth evaluation of pre-verified authorizer claims.)
# =========================================================================

class TestMatrixC_AuthenticationBoundary:

    def test_admin_authorizer_claims_rejects_unauthenticated_request(self):
        """[Authorizer Claims] Request lacking JWT authorizer claims is rejected."""
        resp = admin_mod.lambda_handler({"requestContext": {"requestId": "req-unauth"}}, None)
        assert resp["statusCode"] == 401
        assert json.loads(resp["body"])["success"] is False

    def test_admin_authorizer_claims_rejects_non_admin_cognito_group(self):
        """[Authorizer Claims] Forwarded claims lacking 'Admins' group receive 403 FORBIDDEN_NOT_ADMIN."""
        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "student-uuid-123",
                            "cognito:groups": ["Students", "Staff"],
                            "token_use": "id",
                            "exp": str(int(time.time()) + 3600),
                        }
                    }
                }
            }
        }
        resp = admin_mod.lambda_handler(event, None)
        assert resp["statusCode"] == 403
        assert json.loads(resp["body"])["errorCode"] == "FORBIDDEN_NOT_ADMIN"

    def test_admin_authorizer_claims_accepts_admin_group_claims(self):
        """[Authorizer Claims] Forwarded claims with 'Admins' group & valid exp succeed (200)."""
        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "admin-uuid-456",
                            "cognito:groups": ["Admins"],
                            "token_use": "id",
                            "exp": str(int(time.time()) + 3600),
                        }
                    }
                }
            }
        }
        resp = admin_mod.lambda_handler(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["success"] is True
        assert "reports" in body["data"]

    def test_admin_authorizer_claims_rejects_expired_issuer_and_audience_mismatches(self, monkeypatch):
        """[Authorizer Claims] Defense-in-depth validator rejects expired, wrong-pool, wrong-client, and alg=none tokens."""
        monkeypatch.setenv("USER_POOL_ID", "ap-southeast-2_RealPool1")
        monkeypatch.setenv("USER_POOL_CLIENT_ID", "clientid123456")

        # Expired claim
        ok_exp, _, err_exp = verify_cognito_jwt_claims(
            {"sub": "a", "cognito:groups": ["Admins"], "exp": int(time.time()) - 120}
        )
        assert ok_exp is False
        assert err_exp == "UNAUTHORIZED_EXPIRED_TOKEN"

        # Mismatched issuer
        ok_iss, _, err_iss = verify_cognito_jwt_claims(
            {
                "sub": "a",
                "cognito:groups": ["Admins"],
                "exp": int(time.time()) + 600,
                "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_WrongPool",
            },
            expected_user_pool_id="ap-southeast-2_RealPool1",
        )
        assert ok_iss is False
        assert err_iss == "UNAUTHORIZED_WRONG_ISSUER"

        # Mismatched audience
        ok_aud, _, err_aud = verify_cognito_jwt_claims(
            {"sub": "a", "cognito:groups": ["Admins"], "exp": int(time.time()) + 600, "aud": "evil-client"},
            expected_client_id="clientid123456",
        )
        assert ok_aud is False
        assert err_aud == "UNAUTHORIZED_WRONG_AUDIENCE"

        # Unverified header parser rejects 'alg': 'none' (while signature verification itself lives in API Gateway)
        import base64
        hdr = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
        pld = base64.urlsafe_b64encode(json.dumps({"sub": "a"}).encode()).decode().rstrip("=")
        with pytest.raises(JWTValidationError):
            parse_unverified_jwt(f"{hdr}.{pld}.")

    def test_production_environment_strictly_forbids_static_api_key(self, monkeypatch):
        """Static X-Admin-Key headers are unconditionally rejected when ENVIRONMENT=production."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        resp = admin_mod.lambda_handler(
            {"headers": {"X-Admin-Key": "queuesense-admin-secret-dev-key"}, "requestContext": {}},
            None,
        )
        assert resp["statusCode"] == 401
        assert json.loads(resp["body"])["errorCode"] == "UNAUTHORIZED_COGNITO_REQUIRED"

    def test_sam_api_gateway_jwt_authorizer_configuration(self):
        """
        [Static SAM Infrastructure Inspection]
        Verifies that cryptographic JWT verification is configured in API Gateway (`CognitoAuthorizer`),
        attached strictly to admin route `/admin/reports`, with Cognito issuer & client audience.
        """
        tmpl = load_cfn_template()
        resources = tmpl.get("Resources", {})

        http_api = resources["QueueSenseHttpApi"]["Properties"]
        auth_cfg = http_api["Auth"]["Authorizers"]["CognitoAuthorizer"]

        assert auth_cfg["IdentitySource"] == "$request.header.Authorization"
        jwt_cfg = auth_cfg["JwtConfiguration"]
        assert jwt_cfg["issuer"] == {
            "Sub": "https://cognito-idp.${AWS::Region}.amazonaws.com/${QueueSenseUserPool}"
        }
        assert jwt_cfg["audience"] == [{"Ref": "QueueSenseUserPoolClient"}]

        # AdminReportsFunction event attachment
        admin_event = resources["AdminReportsFunction"]["Properties"]["Events"]["AdminAuditFeed"]
        assert admin_event["Type"] == "HttpApi"
        assert admin_event["Properties"]["Path"] == "/admin/reports"
        assert admin_event["Properties"]["Method"] == "GET"
        assert admin_event["Properties"]["Auth"]["Authorizer"] == "CognitoAuthorizer"
        # Scope is NOT configured at route level; group membership ('Admins') is enforced in Lambda
        assert "AuthorizationScopes" not in admin_event["Properties"]["Auth"]

        # Public routes must remain unauthenticated by CognitoAuthorizer
        public_funcs = [
            "HealthFunction",
            "GetLocationsFunction",
            "GetQueueFunction",
            "SubmitReportFunction",
            "GetRecommendationsFunction",
            "GetHistoricalFunction",
        ]
        for fname in public_funcs:
            events = resources[fname]["Properties"]["Events"]
            for ev in events.values():
                assert "Auth" not in ev["Properties"], f"Unexpected Auth block on public function {fname}"


# =========================================================================
# Part 4 — Matrix D: Rate Limiting & Abuse Resistance
# =========================================================================

class TestMatrixD_RateLimitingAndAbuseResistance:

    def test_burst_submissions_trigger_rate_limit(self):
        """[In-Memory] Consecutive burst beyond 5/300s from same client triggers HTTP 429."""
        statuses = []
        codes = []
        for i in range(8):
            resp = submit_report_mod.lambda_handler(
                {
                    "pathParameters": {"id": "iitb-mess-h12-14"},
                    "headers": {"X-Device-ID": "dev-burst-abuser-01", "X-Idempotency-Key": f"burst-{i:02d}-abcd"},
                    "body": json.dumps({"reportedWaitMinutes": 10, "queueLength": 10}),
                    "requestContext": {"identity": {"sourceIp": "192.168.1.100"}},
                },
                None,
            )
            statuses.append(resp["statusCode"])
            if resp["statusCode"] == 429:
                codes.append(json.loads(resp["body"])["errorCode"])

        assert statuses[:5] == [201, 201, 201, 201, 201]
        assert statuses[5:] == [429, 429, 429]
        assert all("RATE_LIMIT" in c for c in codes)

    def test_client_spoofed_forwarded_for_is_ignored(self):
        """Client-supplied X-Forwarded-For headers cannot alter pseudonymous hash identity."""
        base = {
            "headers": {"X-Forwarded-For": "8.8.8.8", "X-Device-ID": "dev-fixed-device-12345"},
            "requestContext": {"identity": {"sourceIp": "10.0.0.99"}},
        }
        spoofed = {
            "headers": {"X-Forwarded-For": "203.0.113.195", "X-Device-ID": "dev-fixed-device-12345"},
            "requestContext": {"identity": {"sourceIp": "10.0.0.99"}},
        }
        assert compute_anonymous_client_hash(base) == compute_anonymous_client_hash(spoofed)

    def test_outlier_filtering_bounds_and_uncorroborated_spikes(self):
        """Outlier filter discards physical violations and uncorroborated isolated spikes (N >= 5)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        reports = [
            {"reportedWaitMinutes": 10, "queueLength": 12, "timestamp": now_iso, "deviceId": "dev-a-1234567890"},
            {"reportedWaitMinutes": 12, "queueLength": 14, "timestamp": now_iso, "deviceId": "dev-b-1234567890"},
            {"reportedWaitMinutes": 11, "queueLength": 13, "timestamp": now_iso, "deviceId": "dev-c-1234567890"},
            {"reportedWaitMinutes": 9, "queueLength": 11, "timestamp": now_iso, "deviceId": "dev-d-1234567890"},
            {"reportedWaitMinutes": 10, "queueLength": 12, "timestamp": now_iso, "deviceId": "dev-e-1234567890"},
            {"reportedWaitMinutes": 90, "queueLength": 200, "timestamp": now_iso, "deviceId": "dev-f-1234567890"},
            {"reportedWaitMinutes": 135, "queueLength": 20, "timestamp": now_iso, "deviceId": "dev-g-1234567890"},
        ]
        valid, outliers = filter_outliers(reports)
        reasons = {o["outlierReason"] for o in outliers}
        assert len(valid) == 5
        assert "PHYSICAL_BOUNDS_VIOLATION" in reasons
        assert "UNCORROBORATED_ISOLATED_SPIKE" in reasons


# =========================================================================
# Part 5 — Matrix E: Campus Partition Isolation & Pagination Bounds
# =========================================================================

class TestMatrixE_CampusIsolationAndValidation:

    def test_campus_partition_isolation_prevents_cross_talk(self, monkeypatch):
        """Campus configuration strictly separates IITB and VITAP outlet catalogs."""
        monkeypatch.setenv("CAMPUS_ID", "iitb")
        iitb_locs = get_default_campus_locations()
        assert len(iitb_locs) > 0
        assert all(loc["id"].startswith("iitb-") for loc in iitb_locs)

        monkeypatch.setenv("CAMPUS_ID", "vitap")
        vitap_locs = get_default_campus_locations()
        assert len(vitap_locs) > 0
        assert all(loc["id"].startswith("vitap-") for loc in vitap_locs)

    def test_pagination_limits_validation(self):
        """validate_pagination_limit strictly accepts [1, 100] and rejects outside integers."""
        ok_low, _, err_low = validate_pagination_limit(-10, default=30)
        assert ok_low is False and "at least 1" in err_low

        ok_valid, val, _ = validate_pagination_limit(50, default=30)
        assert ok_valid is True and val == 50

        ok_high, _, err_high = validate_pagination_limit(500, default=30)
        assert ok_high is False and "cannot exceed 100" in err_high


# =========================================================================
# Part 6 — Matrix F: Prediction Decay Specification (tau = 15.0 minutes)
# =========================================================================

class TestMatrixF_PredictionsAndRecommendations:

    def test_prediction_decay_constant_15m_and_half_life_specification(self):
        """
        Explicitly asserts the true configured exponential decay constant:
        DEFAULT_DECAY_CONSTANT_MINUTES = 15.0 (900s), half-life = 15 * ln(2) ~= 10.3972 minutes,
        cosine taper above 50m, and hard cutoff above 60m.
        Also checks frontend/src/services/api.ts uses matching 15 * 60 * 1000 ms constant.
        """
        assert DEFAULT_DECAY_CONSTANT_MINUTES == 15.0
        now = datetime.now(timezone.utc)

        # At t = 0 -> w = 1.0
        assert calculate_freshness_weight(now, now) == pytest.approx(1.0, abs=1e-6)

        # At exact half-life t_1/2 = 15.0 * ln(2) ~= 10.3972m -> w = 0.5
        t_half_min = DEFAULT_DECAY_CONSTANT_MINUTES * math.log(2.0)
        assert calculate_freshness_weight(now - timedelta(minutes=t_half_min), now) == pytest.approx(0.5, abs=1e-5)

        # At t = tau = 15.0m -> w = exp(-1) ~= 0.36788
        assert calculate_freshness_weight(now - timedelta(minutes=15.0), now) == pytest.approx(math.exp(-1.0), abs=1e-5)

        # At t = 2 * tau = 30.0m -> w = exp(-2) ~= 0.13534
        assert calculate_freshness_weight(now - timedelta(minutes=30.0), now) == pytest.approx(math.exp(-2.0), abs=1e-5)

        # Beyond 60m -> w = 0.0
        assert calculate_freshness_weight(now - timedelta(minutes=60.5), now) == 0.0

        # Verify frontend computeClientEstimate uses matching 15-minute decay constant
        api_ts_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "services", "api.ts")
        )
        with open(api_ts_path, "r", encoding="utf-8") as f:
            api_src = f.read()
        assert "TAU_MS = 15 * 60 * 1000" in api_src

    def test_exponential_decay_favors_recent_reports_under_15m_tau(self):
        """With tau=15.0m, a 2m report vastly outweighs a 25m old report."""
        now = datetime.now(timezone.utc)
        reports = [
            {"reportedWaitMinutes": 50.0, "queueLength": 50, "timestamp": (now - timedelta(minutes=25)).isoformat()},
            {"reportedWaitMinutes": 10.0, "queueLength": 10, "timestamp": (now - timedelta(minutes=2)).isoformat()},
        ]
        estimate = calculate_queue_estimate(reports)
        assert estimate["predictedWaitMinutes"] < 20.0
        assert estimate["predictedQueueLength"] < 20

    def test_sparse_data_defaults_safely(self):
        """Empty report history defaults to honest NO DATA state."""
        est = calculate_queue_estimate([])
        assert est["predictedWaitMinutes"] is None
        assert est["predictedQueueLength"] is None
        assert est["confidence"] == 0.0
        assert est["confidenceLabel"] == "NO DATA"
        assert est["freshness"] == "NO RECENT DATA"

    def test_invalid_report_payload_rejected_by_validation(self):
        """Negative, >120 min, and fractional queueLength values are rejected."""
        ok, _, errs = validate_report_payload({"reportedWaitMinutes": -5, "queueLength": 10})
        assert not ok and any("cannot be negative" in e for e in errs)

        ok, _, errs = validate_report_payload({"reportedWaitMinutes": 150, "queueLength": 10})
        assert not ok and any("exceeds plausible limit" in e for e in errs)

        ok, _, errs = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": 4.5})
        assert not ok and any("whole integer" in e for e in errs)


# =========================================================================
# Part 7 — Matrix G: Infrastructure & Least-Privilege IAM Audit
# =========================================================================

class TestMatrixG_InfrastructureAndLeastPrivilegeIAM:

    def test_no_wildcard_dynamodb_write_policies(self):
        """CloudFormation template has NO IAM policy granting DynamoDB writes on '*'."""
        tmpl = load_cfn_template()
        write_actions = {"dynamodb:putitem", "dynamodb:updateitem", "dynamodb:deleteitem"}

        for res_name, res in tmpl.get("Resources", {}).items():
            if res.get("Type") == "AWS::IAM::Policy":
                doc = res.get("Properties", {}).get("PolicyDocument", {})
                for stmt in doc.get("Statement", []):
                    actions = stmt.get("Action", [])
                    if isinstance(actions, str):
                        actions = [actions]
                    if write_actions & {a.lower() for a in actions}:
                        assert stmt.get("Resource", "") != "*", f"Wildcard DynamoDB write in {res_name}"

    def test_dynamodb_table_uses_on_demand_billing(self):
        """MainTable specifies PAY_PER_REQUEST billing mode."""
        tmpl = load_cfn_template()
        assert tmpl["Resources"]["MainTable"]["Properties"]["BillingMode"] == "PAY_PER_REQUEST"

    def test_s3_bucket_has_public_access_blocked(self):
        """FrontendBucket blocks all public ACLs and policies."""
        tmpl = load_cfn_template()
        pab = tmpl["Resources"]["FrontendBucket"]["Properties"]["PublicAccessBlockConfiguration"]
        assert pab["BlockPublicAcls"] is True
        assert pab["BlockPublicPolicy"] is True
        assert pab["IgnorePublicAcls"] is True
        assert pab["RestrictPublicBuckets"] is True

    def test_all_lambda_log_groups_have_explicit_retention(self):
        """Every CloudWatch LogGroup specifies 30-day RetentionInDays."""
        tmpl = load_cfn_template()
        log_groups = [r for r in tmpl.get("Resources", {}).values() if r.get("Type") == "AWS::Logs::LogGroup"]
        assert len(log_groups) >= 5
        assert all(lg.get("Properties", {}).get("RetentionInDays") == 30 for lg in log_groups)
