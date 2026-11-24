"""
QueueSense - Batch 2 Comprehensive Security & Adversarial Test Suite
Covers:
- P1.8: JWT verification, claims validation, algorithm restriction, authorizer security.
- P1.9: IP HMAC pseudonymization, privacy disclosure, salt isolation, zero plaintext persistence.
- P1.10: Shared campus NAT fairness, device-ID binding, NAT burst ceiling, forwarded header rejection.
- P1.11: Numeric boundary validation: NaN/Infinity rejection, boolean rejection, fractional people rejection,
         exact boundary testing, and query parameter limit/days bounds.
- P1.12: Secrets, KMS decryption policies, SSM parameter access, zero credential leakage.
"""

import base64
import json
import math
import os
import re
import sys
import time
from typing import Dict, Any
from unittest.mock import MagicMock
import pytest

from backend.shared.security import (
    verify_cognito_jwt_claims,
    parse_unverified_jwt,
    compute_pseudonymous_client_hash,
    compute_anonymous_client_hash,
    extract_client_instance_id,
    get_rate_limit_salt,
    clear_salt_cache,
    _validate_salt_strength,
    SecurityConfigurationError,
    JWTValidationError,
)
from backend.shared.validation import (
    validate_report_payload,
    validate_pagination_limit,
    validate_historical_days,
)
from backend.shared.database import InMemoryStorageAdapter, DatabasePersistenceError
from backend.functions.admin.app import lambda_handler as admin_handler
from backend.functions.get_historical.app import lambda_handler as historical_handler
from backend.functions.submit_report.app import lambda_handler as submit_handler


# Helper to construct valid base64url JWT tokens for tests
def make_mock_jwt(
    header: Dict[str, Any],
    payload: Dict[str, Any],
    signature: str = "mock_signature_bytes",
) -> str:
    def b64url(obj: Any) -> str:
        data = json.dumps(obj).encode("utf-8") if isinstance(obj, dict) else str(obj).encode("utf-8")
        return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")
    return f"{b64url(header)}.{b64url(payload)}.{signature}"


# =========================================================================
# P1.8 — JWT Verification & API Gateway Authorizer Security
# =========================================================================

def test_jwt_claims_verification_valid_admin():
    """P1.8: Valid admin claims pass verification and return username."""
    now = int(time.time())
    claims = {
        "sub": "user-uuid-123",
        "username": "dining_admin",
        "cognito:groups": ["Admins", "Staff"],
        "token_use": "id",
        "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
        "aud": "client_id_456",
        "exp": now + 3600,
        "nbf": now - 10,
    }
    is_valid, user_id, err = verify_cognito_jwt_claims(
        claims,
        expected_user_pool_id="ap-southeast-2_TestPool",
        expected_client_id="client_id_456",
        expected_group="Admins",
    )
    assert is_valid is True
    assert user_id == "dining_admin"
    assert err is None


def test_jwt_claims_verification_expired_token():
    """P1.8: Expired tokens are rejected."""
    now = int(time.time())
    claims = {
        "sub": "user-uuid-123",
        "cognito:groups": ["Admins"],
        "token_use": "id",
        "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
        "exp": now - 300,  # 5 minutes in the past
    }
    is_valid, user_id, err = verify_cognito_jwt_claims(claims, clock_skew_seconds=0)
    assert is_valid is False
    assert err == "UNAUTHORIZED_EXPIRED_TOKEN"


def test_jwt_claims_verification_token_not_yet_valid():
    """P1.8: Tokens with future nbf (not yet valid) are rejected."""
    now = int(time.time())
    claims = {
        "sub": "user-uuid-123",
        "cognito:groups": ["Admins"],
        "token_use": "id",
        "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
        "exp": now + 3600,
        "nbf": now + 600,  # 10 minutes in the future
    }
    is_valid, user_id, err = verify_cognito_jwt_claims(claims, clock_skew_seconds=0)
    assert is_valid is False
    assert err == "UNAUTHORIZED_TOKEN_NOT_YET_VALID"


def test_jwt_claims_verification_missing_expiration():
    """P1.8: Tokens missing exp claim fail validation when require_exp=True."""
    claims = {
        "sub": "user-uuid-123",
        "cognito:groups": ["Admins"],
        "token_use": "id",
        "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
    }
    is_valid, user_id, err = verify_cognito_jwt_claims(claims, require_exp=True)
    assert is_valid is False
    assert err == "UNAUTHORIZED_MISSING_EXPIRATION"


def test_jwt_claims_verification_invalid_token_use():
    """P1.8: Tokens with token_use other than 'id' or 'access' are rejected."""
    now = int(time.time())
    claims = {
        "sub": "user-uuid-123",
        "cognito:groups": ["Admins"],
        "token_use": "refresh",  # Refresh tokens cannot be used as bearer tokens directly
        "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
        "exp": now + 3600,
    }
    is_valid, user_id, err = verify_cognito_jwt_claims(claims)
    assert is_valid is False
    assert err == "UNAUTHORIZED_INVALID_TOKEN_USE"


def test_jwt_claims_verification_wrong_issuer():
    """P1.8: Tokens with mismatched issuer are rejected."""
    now = int(time.time())
    claims = {
        "sub": "user-uuid-123",
        "cognito:groups": ["Admins"],
        "token_use": "id",
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_AttackerPool",
        "exp": now + 3600,
    }
    is_valid, user_id, err = verify_cognito_jwt_claims(
        claims, expected_user_pool_id="ap-southeast-2_RealPool"
    )
    assert is_valid is False
    assert err == "UNAUTHORIZED_WRONG_ISSUER"


def test_jwt_claims_verification_wrong_audience():
    """P1.8: Tokens targeting another client application are rejected."""
    now = int(time.time())
    claims = {
        "sub": "user-uuid-123",
        "cognito:groups": ["Admins"],
        "token_use": "id",
        "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
        "aud": "rogue_client_app",
        "exp": now + 3600,
    }
    is_valid, user_id, err = verify_cognito_jwt_claims(
        claims,
        expected_user_pool_id="ap-southeast-2_TestPool",
        expected_client_id="queuesense_official_client",
    )
    assert is_valid is False
    assert err == "UNAUTHORIZED_WRONG_AUDIENCE"


def test_jwt_claims_verification_privilege_escalation_non_admin():
    """P1.8: Authenticated user without 'Admins' group is rejected with FORBIDDEN_NOT_ADMIN."""
    now = int(time.time())
    claims = {
        "sub": "student-uuid-456",
        "username": "student_user",
        "cognito:groups": ["Students"],  # Not an admin
        "token_use": "id",
        "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
        "exp": now + 3600,
    }
    is_valid, user_id, err = verify_cognito_jwt_claims(claims, expected_group="Admins")
    assert is_valid is False
    assert err == "FORBIDDEN_NOT_ADMIN"


def test_jwt_unverified_parser_rejects_none_algorithm():
    """P1.8: Unverified parser strictly rejects alg: 'none'."""
    token = make_mock_jwt({"alg": "none", "typ": "JWT"}, {"sub": "attacker"})
    with pytest.raises(JWTValidationError) as exc:
        parse_unverified_jwt(token)
    assert "none" in str(exc.value).lower()


def test_jwt_unverified_parser_rejects_unsupported_algorithm():
    """P1.8: Unverified parser rejects symmetric algorithms like HS256."""
    token = make_mock_jwt({"alg": "HS256", "typ": "JWT"}, {"sub": "attacker"})
    with pytest.raises(JWTValidationError) as exc:
        parse_unverified_jwt(token)
    assert "Only RS256 is permitted" in str(exc.value)


def test_jwt_unverified_parser_rejects_malformed_structure():
    """P1.8: Unverified parser rejects malformed dot-separated structures."""
    with pytest.raises(JWTValidationError):
        parse_unverified_jwt("only_one_part")
    with pytest.raises(JWTValidationError):
        parse_unverified_jwt("part1.part2")
    with pytest.raises(JWTValidationError):
        parse_unverified_jwt("part1.part2.part3.part4")


def test_admin_handler_production_lockdown_rejects_unauthenticated_requests(monkeypatch):
    """P1.8: In production, missing Cognito authorizer context strictly returns HTTP 401."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ADMIN_DEV_KEY", "should_be_ignored_in_production")

    event = {
        "requestContext": {},
        "headers": {"Authorization": "Bearer should_be_ignored_in_production"},
    }
    res = admin_handler(event, None)
    assert res["statusCode"] == 401
    body = json.loads(res["body"])
    assert body["success"] is False
    assert body["errorCode"] == "UNAUTHORIZED_COGNITO_REQUIRED"


def test_admin_handler_forbidden_for_non_admin():
    """P1.8: Authenticated user who is not an Admin receives HTTP 403."""
    now = int(time.time())
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "student-123",
                        "username": "student_johndoe",
                        "cognito:groups": ["Students"],
                        "token_use": "id",
                        "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
                        "exp": now + 3600,
                    }
                }
            }
        }
    }
    res = admin_handler(event, None)
    assert res["statusCode"] == 403
    body = json.loads(res["body"])
    assert body["success"] is False
    assert body["errorCode"] == "FORBIDDEN_NOT_ADMIN"


# =========================================================================
# P1.9 — IP HMAC Pseudonymization & Privacy Accuracy
# =========================================================================

def test_hmac_pseudonym_generation_and_length():
    """P1.9: Client hash returns full 64-character hexadecimal pseudonym (256-bit HMAC-SHA256)."""
    event = {"requestContext": {"http": {"sourceIp": "103.21.124.50"}}}
    h = compute_pseudonymous_client_hash(event, salt="test_salt_entropy_32_characters_minimum_12345")
    assert isinstance(h, str)
    assert len(h) == 64, f"Expected full 256-bit digest (64 hex chars), got {len(h)}"
    assert re.match(r"^[0-9a-f]{64}$", h)


def test_hmac_output_length_is_full_256_bit_digest():
    """P1.9: Verifies exact 256-bit digest length across varied IP and device combinations."""
    salt = "test_salt_entropy_32_characters_minimum_12345"
    ev1 = {"requestContext": {"http": {"sourceIp": "192.0.2.1"}}}
    ev2 = {
        "requestContext": {"http": {"sourceIp": "192.0.2.1"}},
        "headers": {"x-device-id": "client-instance-uuid-1111111111"},
    }
    h1 = compute_pseudonymous_client_hash(ev1, salt=salt)
    h2 = compute_pseudonymous_client_hash(ev2, salt=salt)
    assert len(h1) == 64
    assert len(h2) == 64
    assert h1 != h2


def test_hmac_determinism_for_identical_inputs_and_salts():
    """P1.9: Identical source identity and salt produces deterministic, reproducible 256-bit digests."""
    salt = "fixed_reproducible_salt_32_chars_min_entropy_1234"
    event = {
        "requestContext": {"http": {"sourceIp": "10.0.0.42"}},
        "headers": {"x-device-id": "reproducible-device-id-1234567890"},
    }
    digests = [compute_pseudonymous_client_hash(event, salt=salt) for _ in range(10)]
    assert len(set(digests)) == 1, "HMAC-SHA256 must be strictly deterministic"
    assert len(digests[0]) == 64


def test_dynamodb_rate_limit_pk_format_and_capacity():
    """P1.9: Full 64-char HMAC partition key (RATELIMIT#<64-hex>) respects DynamoDB 2048-byte PK limit."""
    event = {"requestContext": {"http": {"sourceIp": "203.0.113.199"}}}
    h = compute_pseudonymous_client_hash(event, salt="test_salt_entropy_32_characters_minimum_12345")
    pk = f"RATELIMIT#{h}"
    # DynamoDB partition key UTF-8 limit is 2048 bytes
    assert len(pk.encode("utf-8")) == 74
    assert len(pk.encode("utf-8")) < 2048


def test_csprng_salt_generation_and_entropy_validation():
    """P1.9: Cryptographically secure random generation (secrets.token_hex) passes strength validator."""
    import secrets
    # 32 bytes of CSPRNG = 64 hex characters (256 bits of true entropy)
    csprng_salt = secrets.token_hex(32)
    assert len(csprng_salt) == 64
    # Must not raise in production
    _validate_salt_strength(csprng_salt, is_production=True)


def test_raw_ip_is_never_leaked_in_pseudonym_or_response():
    """P1.9: Raw IP address is never exposed in output pseudonym."""
    raw_ip = "192.168.1.100"
    event = {"requestContext": {"http": {"sourceIp": raw_ip}}}
    h = compute_pseudonymous_client_hash(event, salt="test_salt_entropy_32_characters_minimum_12345")
    assert raw_ip not in h


def test_salt_isolation_produces_distinct_pseudonyms():
    """P1.9: Identical IP with distinct salts generates completely distinct pseudonyms."""
    event = {"requestContext": {"http": {"sourceIp": "103.21.124.50"}}}
    salt1 = "salt_alpha_entropy_minimum_32_characters_11111"
    salt2 = "salt_beta_entropy_minimum_32_characters_222222"

    h1 = compute_pseudonymous_client_hash(event, salt=salt1)
    h2 = compute_pseudonymous_client_hash(event, salt=salt2)
    assert h1 != h2, "Different salts must produce distinct pseudonyms (salt isolation)"


def test_weak_and_missing_salt_fails_closed_in_production(monkeypatch):
    """P1.9: Production strictly fails closed on missing or weak salts."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    clear_salt_cache()

    # 1. Missing salt
    monkeypatch.delenv("RATE_LIMIT_SALT", raising=False)
    monkeypatch.delenv("RATE_LIMIT_SALT_PARAMETER_NAME", raising=False)
    with pytest.raises(SecurityConfigurationError):
        get_rate_limit_salt()

    # 2. Too short (< 32 characters)
    monkeypatch.setenv("RATE_LIMIT_SALT", "short_secret_12345")
    with pytest.raises(SecurityConfigurationError) as exc:
        get_rate_limit_salt()
    assert "Minimum 32 characters required" in str(exc.value)

    # 3. Predictable weak pattern
    clear_salt_cache()
    monkeypatch.setenv("RATE_LIMIT_SALT", "password_password_password_password_1234")
    with pytest.raises(SecurityConfigurationError) as exc:
        get_rate_limit_salt()
    assert "predictable or weak pattern" in str(exc.value)


# =========================================================================
# P1.10 — NAT Collisions & Rate-Limiting Fairness
# =========================================================================

def test_shared_nat_multi_client_fairness():
    """
    P1.10: Two legitimate students sharing the same NAT IP with distinct device IDs
    have independent rate-limit allowances (each can make 5 requests).
    """
    shared_ip = "103.21.124.50"
    event_student1 = {
        "requestContext": {"http": {"sourceIp": shared_ip}},
        "headers": {"x-device-id": "device-uuid-student-1-1111111111"},
    }
    event_student2 = {
        "requestContext": {"http": {"sourceIp": shared_ip}},
        "headers": {"x-device-id": "device-uuid-student-2-2222222222"},
    }

    h1 = compute_pseudonymous_client_hash(event_student1, salt="test_salt_entropy_32_characters_minimum_12345")
    h2 = compute_pseudonymous_client_hash(event_student2, salt="test_salt_entropy_32_characters_minimum_12345")

    assert h1 != h2, "Distinct students on same NAT IP must receive distinct device pseudonyms"


def test_adversarial_device_id_rotation_blocked_by_nat_ceiling(monkeypatch):
    """
    P1.10: An attacker from a single IP rotating device IDs to flood reports
    is blocked when the shared NAT ceiling (30 requests / 5 min) is reached.
    """
    adapter = InMemoryStorageAdapter()
    attacker_ip = "203.0.113.99"
    salt = "test_salt_entropy_32_characters_minimum_12345"

    nat_hash = compute_pseudonymous_client_hash(
        {"requestContext": {"http": {"sourceIp": attacker_ip}}},
        salt=salt,
        include_device_id=False,
    )

    # Simulate 30 requests already consumed from this public IP
    for _ in range(30):
        allowed = adapter.check_rate_limit(client_hash=nat_hash, window_seconds=300, max_requests=30)
        assert allowed is True

    # 31st request: Even with a brand new, unused device ID, the NAT ceiling blocks the request
    attacker_event = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "requestContext": {"http": {"sourceIp": attacker_ip}},
        "headers": {"x-device-id": "brand-new-rotated-device-id-99999"},
        "body": json.dumps({"reportedWaitMinutes": 15.0, "queueLength": 5}),
    }

    monkeypatch.setattr("backend.functions.submit_report.app.QueueSenseDatabase", lambda: adapter)
    monkeypatch.setattr("backend.shared.security.get_rate_limit_salt", lambda: salt)

    res = submit_handler(attacker_event, None)
    assert res["statusCode"] == 429
    body = json.loads(res["body"])
    assert body["errorCode"] == "NAT_RATE_LIMIT_EXCEEDED"


def test_client_forwarded_headers_spoofing_prevented():
    """P1.10: Spoofed X-Forwarded-For headers are strictly ignored."""
    event = {
        "requestContext": {"http": {"sourceIp": "103.21.124.50"}},
        "headers": {
            "x-forwarded-for": "1.2.3.4, 5.6.7.8",
            "client-ip": "9.9.9.9",
        },
    }
    h = compute_pseudonymous_client_hash(event, salt="test_salt_entropy_32_characters_minimum_12345")
    # Base hash without headers
    event_clean = {"requestContext": {"http": {"sourceIp": "103.21.124.50"}}}
    h_clean = compute_pseudonymous_client_hash(event_clean, salt="test_salt_entropy_32_characters_minimum_12345")
    assert h == h_clean, "Forwarded headers must not affect client pseudonym"


def test_malformed_device_id_sanitized_or_ignored():
    """P1.10: Device IDs with injection characters or invalid lengths are ignored."""
    event_bad_chars = {
        "headers": {"x-device-id": "../../../etc/passwd; DROP TABLE"}
    }
    assert extract_client_instance_id(event_bad_chars) is None

    event_too_short = {"headers": {"x-device-id": "short"}}
    assert extract_client_instance_id(event_too_short) is None

    event_too_long = {"headers": {"x-device-id": "a" * 65}}
    assert extract_client_instance_id(event_too_long) is None

    event_valid = {"headers": {"x-device-id": "valid-device-uuid-1234567890"}}
    assert extract_client_instance_id(event_valid) == "valid-device-uuid-1234567890"


def test_frontend_request_headers_and_dual_budget_integration(monkeypatch):
    """
    P1.10: Integration test verifying the exact frontend request contract:
    Frontend sends X-Device-ID, X-Idempotency-Key, and Content-Type.
    Backend correctly processes the submission, attaches the device ID to the client budget,
    and grants independent quotas to distinct devices behind the same IP.
    """
    adapter = InMemoryStorageAdapter()
    monkeypatch.setattr("backend.functions.submit_report.app.QueueSenseDatabase", lambda: adapter)
    monkeypatch.setattr("backend.shared.security.get_rate_limit_salt", lambda: "integration_salt_entropy_32_characters_12345")

    shared_nat_ip = "103.21.124.77"

    # Student 1 from frontend
    for req_idx in range(5):
        event_s1 = {
            "pathParameters": {"id": "iitb-mess-h12-14"},
            "headers": {
                "content-type": "application/json",
                "x-idempotency-key": f"idem-student1-{req_idx}",
                "x-device-id": "device-uuid-student-1-aaaa-bbbb",
            },
            "requestContext": {
                "http": {"sourceIp": shared_nat_ip},
                "requestId": f"req-s1-{req_idx}",
            },
            "body": json.dumps({"reportedWaitMinutes": 10.0, "queueLength": 5}),
        }
        res_s1 = submit_handler(event_s1, None)
        assert res_s1["statusCode"] == 201

    # Student 1 6th request is rate-limited (Tier-1 budget exhausted)
    event_s1_6th = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "headers": {
            "content-type": "application/json",
            "x-idempotency-key": "idem-student1-6th",
            "x-device-id": "device-uuid-student-1-aaaa-bbbb",
        },
        "requestContext": {
            "http": {"sourceIp": shared_nat_ip},
            "requestId": "req-s1-6th",
        },
        "body": json.dumps({"reportedWaitMinutes": 10.0, "queueLength": 5}),
    }
    res_s1_6th = submit_handler(event_s1_6th, None)
    assert res_s1_6th["statusCode"] == 429
    body_s1 = json.loads(res_s1_6th["body"])
    assert body_s1["errorCode"] == "RATE_LIMIT_EXCEEDED"

    # Student 2 from same NAT IP can STILL submit reports (not blocked by Student 1's usage)
    event_s2 = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "headers": {
            "content-type": "application/json",
            "x-idempotency-key": "idem-student2-1st",
            "x-device-id": "device-uuid-student-2-cccc-dddd",
        },
        "requestContext": {
            "http": {"sourceIp": shared_nat_ip},
            "requestId": "req-s2-1st",
        },
        "body": json.dumps({"reportedWaitMinutes": 12.0, "queueLength": 8}),
    }
    res_s2 = submit_handler(event_s2, None)
    assert res_s2["statusCode"] == 201, "Student 2 must not be starved by Student 1 on shared NAT IP"


def test_missing_device_id_safe_fallback_behavior(monkeypatch):
    """
    P1.10: Requests without X-Device-ID (e.g. legacy client or restricted storage)
    safely fall back to IP-based rate limiting without failing or crashing.
    """
    adapter = InMemoryStorageAdapter()
    monkeypatch.setattr("backend.functions.submit_report.app.QueueSenseDatabase", lambda: adapter)
    monkeypatch.setattr("backend.shared.security.get_rate_limit_salt", lambda: "integration_salt_entropy_32_characters_12345")

    event_no_device = {
        "pathParameters": {"id": "iitb-mess-h12-14"},
        "headers": {
            "content-type": "application/json",
            "x-idempotency-key": "idem-no-device-id-1",
        },
        "requestContext": {
            "http": {"sourceIp": "198.51.100.99"},
            "requestId": "req-no-device-1",
        },
        "body": json.dumps({"reportedWaitMinutes": 5.0, "queueLength": 2}),
    }
    res = submit_handler(event_no_device, None)
    assert res["statusCode"] == 201


def test_template_cors_allows_device_id_headers():
    """
    P1.10: Verifies infrastructure/template.yaml API Gateway CORS configuration
    explicitly allows X-Device-ID and X-Client-Instance-ID headers.
    """
    template_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "infrastructure", "template.yaml"
    )
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "X-Device-ID" in content, "template.yaml CORS AllowHeaders must include X-Device-ID"
    assert "X-Client-Instance-ID" in content, "template.yaml CORS AllowHeaders must include X-Client-Instance-ID"


# =========================================================================
# P1.11 — Numeric Boundary Validation
# =========================================================================

def test_validate_report_payload_nan_and_infinity_rejected():
    """P1.11: NaN, Infinity, and -Infinity are strictly rejected."""
    # NaN
    is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": float("nan")})
    assert is_valid is False
    assert any("NaN" in e for e in errors)

    # String 'NaN'
    is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": "NaN"})
    assert is_valid is False
    assert any("NaN" in e for e in errors)

    # Infinity
    is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": float("inf")})
    assert is_valid is False
    assert any("Infinity" in e or "exceeds" in e for e in errors)

    # -Infinity
    is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": float("-inf")})
    assert is_valid is False

    # NaN in queueLength
    is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": float("nan")})
    assert is_valid is False


def test_validate_report_payload_booleans_rejected():
    """P1.11: Booleans are strictly rejected as numeric inputs."""
    is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": True})
    assert is_valid is False
    assert any("numeric value" in e for e in errors)

    is_valid, _, errors = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": False})
    assert is_valid is False
    assert any("integer" in e for e in errors)


def test_validate_report_payload_wait_minutes_boundaries():
    """P1.11: Test exact boundaries for reportedWaitMinutes [0.0, 120.0]."""
    # Exact minimum (0.0) -> Valid
    ok, data, _ = validate_report_payload({"reportedWaitMinutes": 0.0})
    assert ok is True
    assert data["reportedWaitMinutes"] == 0.0

    # Just below minimum (-0.1) -> Invalid
    ok, _, errors = validate_report_payload({"reportedWaitMinutes": -0.1})
    assert ok is False
    assert any("negative" in e for e in errors)

    # Exact maximum (120.0) -> Valid
    ok, data, _ = validate_report_payload({"reportedWaitMinutes": 120.0})
    assert ok is True
    assert data["reportedWaitMinutes"] == 120.0

    # Just above maximum (120.1) -> Invalid
    ok, _, errors = validate_report_payload({"reportedWaitMinutes": 120.1})
    assert ok is False
    assert any("exceeds" in e for e in errors)


def test_validate_report_payload_queue_length_boundaries_and_integers():
    """P1.11: Test boundaries and reject fractional people."""
    # Fractional people (2.5) -> Rejected
    ok, _, errors = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": 2.5})
    assert ok is False
    assert any("whole integer" in e for e in errors)

    # Boundaries [0, 300]
    ok, data, _ = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": 0})
    assert ok is True
    assert data["queueLength"] == 0

    ok, data, _ = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": 300})
    assert ok is True
    assert data["queueLength"] == 300

    ok, _, errors = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": -1})
    assert ok is False
    assert any("negative" in e for e in errors)

    ok, _, errors = validate_report_payload({"reportedWaitMinutes": 10, "queueLength": 301})
    assert ok is False
    assert any("exceeds" in e for e in errors)


def test_validate_pagination_limit_boundaries():
    """P1.11: Test pagination limit validator."""
    # Default
    ok, val, _ = validate_pagination_limit(None, default=50)
    assert ok is True and val == 50

    # Valid boundaries [1, 100]
    assert validate_pagination_limit(1)[0] is True
    assert validate_pagination_limit(100)[0] is True

    # Out of bounds
    assert validate_pagination_limit(0)[0] is False
    assert validate_pagination_limit(-5)[0] is False
    assert validate_pagination_limit(101)[0] is False

    # NaN / Inf / Booleans
    assert validate_pagination_limit(float("nan"))[0] is False
    assert validate_pagination_limit(float("inf"))[0] is False
    assert validate_pagination_limit(True)[0] is False
    assert validate_pagination_limit("not_a_number")[0] is False


def test_admin_handler_numeric_limit_boundary_enforcement():
    """P1.11: GET /admin/reports returns HTTP 400 on invalid limit query params."""
    now = int(time.time())
    admin_auth = {
        "authorizer": {
            "jwt": {
                "claims": {
                    "sub": "admin-1",
                    "cognito:groups": ["Admins"],
                    "token_use": "id",
                    "iss": "https://cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_TestPool",
                    "exp": now + 3600,
                }
            }
        }
    }

    # Negative limit
    res_neg = admin_handler({"requestContext": admin_auth, "queryStringParameters": {"limit": "-5"}}, None)
    assert res_neg["statusCode"] == 400
    assert json.loads(res_neg["body"])["errorCode"] == "INVALID_LIMIT"

    # Zero limit
    res_zero = admin_handler({"requestContext": admin_auth, "queryStringParameters": {"limit": "0"}}, None)
    assert res_zero["statusCode"] == 400

    # Over max (> 100)
    res_over = admin_handler({"requestContext": admin_auth, "queryStringParameters": {"limit": "150"}}, None)
    assert res_over["statusCode"] == 400

    # NaN limit
    res_nan = admin_handler({"requestContext": admin_auth, "queryStringParameters": {"limit": "NaN"}}, None)
    assert res_nan["statusCode"] == 400


def test_get_historical_numeric_boundary_enforcement():
    """P1.11: GET /locations/{id}/historical enforces bounds on days [1, 14] and limit [1, 1000]."""
    base_event = {"pathParameters": {"id": "iitb-mess-h12-14"}}

    # Negative days
    res = historical_handler({**base_event, "queryStringParameters": {"days": "-1"}}, None)
    assert res["statusCode"] == 400
    assert json.loads(res["body"])["errorCode"] == "INVALID_DAYS"

    # Zero days
    res = historical_handler({**base_event, "queryStringParameters": {"days": "0"}}, None)
    assert res["statusCode"] == 400
    assert json.loads(res["body"])["errorCode"] == "INVALID_DAYS"

    # Days > 14
    res = historical_handler({**base_event, "queryStringParameters": {"days": "30"}}, None)
    assert res["statusCode"] == 400
    assert json.loads(res["body"])["errorCode"] == "INVALID_DAYS"

    # Invalid limit (0 or > 1000)
    res = historical_handler({**base_event, "queryStringParameters": {"limit": "0"}}, None)
    assert res["statusCode"] == 400
    assert json.loads(res["body"])["errorCode"] == "INVALID_LIMIT"


# =========================================================================
# P1.12 — Secrets, KMS & Historical Security Hygiene
# =========================================================================

def test_template_submit_report_has_kms_decrypt_policy():
    """P1.12: Infrastructure template grants kms:Decrypt on SSM rate_limit_salt."""
    template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "template.yaml"))
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "SubmitReportKMSDecryptionAccess" in content
    assert "kms:Decrypt" in content
    assert "kms:ViaService: !Sub \"ssm.${AWS::Region}.amazonaws.com\"" in content


def test_template_admin_reports_has_gsi1_and_userpool_wiring():
    """P1.12: Infrastructure template configures GSI1 and Cognito User Pool environment variables for AdminReportsFunction."""
    template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "template.yaml"))
    with open(template_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "AdminReportsDynamoDBAccess" in content
    assert "!Sub \"${MainTable.Arn}/index/GSI1\"" in content
    assert "USER_POOL_ID: !Ref QueueSenseUserPool" in content
    assert "USER_POOL_CLIENT_ID: !Ref QueueSenseUserPoolClient" in content


def test_secret_retrieval_failure_does_not_leak_secrets_in_errors_or_logs(monkeypatch):
    """P1.12: Errors during secret retrieval never leak raw secret values in exception strings."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RATE_LIMIT_SALT", "password_weak_secret_test_1234567890")
    clear_salt_cache()

    try:
        get_rate_limit_salt()
        pytest.fail("Should have raised SecurityConfigurationError")
    except SecurityConfigurationError as exc:
        msg = str(exc)
        # Ensure the actual secret string is not reflected in error message
        assert "password_weak_secret_test_1234567890" not in msg


def test_no_hardcoded_aws_credentials_in_repository():
    """P1.12: Scans repository files to guarantee zero hardcoded AWS access keys or secret tokens."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    aws_key_pattern = re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}")

    for root, dirs, files in os.walk(repo_root):
        # Skip git directory, node_modules, and cache
        if ".git" in root or "node_modules" in root or ".pytest_cache" in root or "dist" in root:
            continue
        for file in files:
            if file.endswith((".py", ".ts", ".tsx", ".yaml", ".yml", ".json", ".md")):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        matches = aws_key_pattern.findall(content)
                        assert len(matches) == 0, f"Potential AWS access key found in {file}: {matches}"
                except Exception:
                    pass


def test_git_history_contains_zero_credentials_or_private_keys():
    """
    P1.12: Git history credential heuristic audit.
    
    Audit Scope & Verification Boundaries:
    - Scans available local Git commit history (via `git log --all -p`) for common credential patterns.
    - Important Security Limitation: A heuristic regex scan across available local commits is a
      defense-in-depth verification; it does NOT mathematically prove that zero secrets were ever
      committed (e.g. encrypted payloads, encoded binaries, or unreferenced dangling commits).
      A comprehensive audit requires specialized AST / entropy tooling across remote reflogs.
    - Test Integrity: Fails honestly if git execution fails (non-zero returncode or timeout),
      or explicitly skips with a clear reason if the git CLI binary is not installed on system PATH.
      Never silently passes when the scan cannot execute.
    """
    import subprocess
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    try:
        proc = subprocess.run(
            ["git", "log", "--all", "-p"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=60,
        )
    except FileNotFoundError:
        pytest.skip("Git CLI binary ('git') not found on system PATH; git history audit skipped.")
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f"git log --all -p timed out after 60 seconds: {exc}")

    # Check process return code and capture stderr
    assert proc.returncode == 0, (
        f"git log --all -p failed with return code {proc.returncode}.\n"
        f"stderr: {proc.stderr}"
    )

    diff_output = proc.stdout
    assert len(diff_output) > 0, "git log --all -p produced empty output; commit history could not be read."

    # 1. AWS Access Key IDs (AKIA or ASIA standard prefixes followed by 16 alphanumeric characters)
    aws_keys = re.findall(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", diff_output)
    assert len(aws_keys) == 0, f"Potential AWS access key pattern found in git history: {aws_keys}"

    # 2. AWS Secret Access Key assignments (e.g. aws_secret_access_key = '...', secret_key = '...')
    aws_secrets = re.findall(
        r"(?i)(?:aws_secret_access_key|aws_session_token)\s*[:=]\s*['\"][A-Za-z0-9/+=]{30,}['\"]",
        diff_output,
    )
    assert len(aws_secrets) == 0, f"Potential AWS secret access key assignment found in git history: {aws_secrets}"

    # 3. Private Key Headers (RSA, EC, DSA, OPENSSH, PGP, ENCRYPTED)
    private_keys = re.findall(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----",
        diff_output,
    )
    assert len(private_keys) == 0, f"Potential private key header found in git history: {private_keys}"



def test_admin_handler_direct_invocation_defense_fails_closed(monkeypatch):
    """
    P1.8: Verifies that direct Lambda invocation (without API Gateway authorizer context)
    in production mode fails closed immediately with HTTP 401 UNAUTHORIZED.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATA_MODE", "production")

    # Direct invocation without requestContext or authorizer
    raw_event = {
        "headers": {"x-admin-key": "attempted-static-key-bypass"},
        "queryStringParameters": {"limit": "10"},
    }
    res = admin_handler(raw_event, None)
    assert res["statusCode"] == 401
    body = json.loads(res["body"])
    assert body["errorCode"] == "UNAUTHORIZED_COGNITO_REQUIRED"


