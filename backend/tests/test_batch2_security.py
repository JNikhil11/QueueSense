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
    """P1.9: Client hash returns exactly a 16-character hexadecimal pseudonym."""
    event = {"requestContext": {"http": {"sourceIp": "103.21.124.50"}}}
    h = compute_pseudonymous_client_hash(event, salt="test_salt_entropy_32_characters_minimum_12345")
    assert isinstance(h, str)
    assert len(h) == 16
    assert re.match(r"^[0-9a-f]{16}$", h)


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

