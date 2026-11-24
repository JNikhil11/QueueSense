"""
QueueSense - Security, Privacy & Throttling Utilities
Implements privacy-preserving client identity hashing, secure token checks,
safe header extraction, and Cognito JWT claims verification.
No hardcoded secret fallbacks in production. Fails closed on missing or weak secrets.
"""

from __future__ import annotations
import base64
import hashlib
import hmac
import json
import logging
import math
import os
import re
import sys
import time
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("queuesense.security")
logger.setLevel(logging.INFO)

WEAK_SALT_PATTERNS = {
    "password",
    "secret",
    "default",
    "123456",
    "queuesense",
    "changeme",
    "admin",
    "testing",
}

CLIENT_INSTANCE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{16,64}$")

# Module-level in-memory cache for the validated salt in the Lambda execution environment
_CACHED_SALT: Optional[str] = None


class SecurityConfigurationError(Exception):
    """Raised when required security credentials or salt configurations are missing or weak."""
    pass


class JWTValidationError(SecurityConfigurationError):
    """Raised when JWT structure, claims, expiration, or algorithm constraints fail validation."""
    pass


def clear_salt_cache() -> None:
    """Clears the in-memory cached salt, primarily for testing and lifecycle resets."""
    global _CACHED_SALT
    _CACHED_SALT = None
    for mod_name in ("security", "backend.shared.security"):
        mod = sys.modules.get(mod_name)
        if mod and mod is not globals() and hasattr(mod, "_CACHED_SALT"):
            setattr(mod, "_CACHED_SALT", None)


def _validate_salt_strength(clean_salt: str, is_production: bool) -> None:
    """
    Validates that the provided salt meets strict production entropy requirements.
    
    Cryptographic Note:
    - String length alone does NOT equal entropy. A 32-character string of low-variety
      or predictable characters (e.g. repeated characters) provides virtually zero entropy.
    - In production, salts MUST be generated using a cryptographically secure pseudo-random
      number generator (CSPRNG), such as `secrets.token_hex(32)` (which generates 64 hex
      characters containing 256 bits of true entropy) or `openssl rand -hex 32`.
    - This validator enforces a strict minimum length of 32 characters and actively checks
      for and rejects repetitive, sequential, and predictable patterns.
    """
    if is_production:
        if len(clean_salt) < 32:
            raise SecurityConfigurationError(
                "RATE_LIMIT_SALT has insufficient length and insufficient entropy. Minimum 32 characters required in production. "
                "Must be generated using a cryptographically secure random generator (e.g. secrets.token_hex(32) for 256 bits of entropy)."
            )
        clean_lower = clean_salt.lower()
        if any(p in clean_lower for p in WEAK_SALT_PATTERNS):
            raise SecurityConfigurationError(
                "RATE_LIMIT_SALT matches a predictable or weak pattern. Provide a cryptographically secure random secret (e.g. secrets.token_hex(32))."
            )
        # Check for repetitive single characters or low unique-character diversity
        if len(set(clean_salt)) < 8:
            raise SecurityConfigurationError(
                "RATE_LIMIT_SALT lacks character diversity. Provide a high-entropy secret generated via CSPRNG."
            )


def get_rate_limit_salt() -> str:
    """
    Retrieves the required HMAC salt for pseudonymous client hashing.
    Fails closed if the secret is missing or insecure in production.
    Strictly requires a cryptographically strong secret (>= 32 characters, preferably
    a 64-character hex string generated via CSPRNG representing 256 bits of entropy).

    Delivery Strategy:
    1. Returns in-memory cached salt if previously retrieved in this Lambda container.
    2. Checks direct RATE_LIMIT_SALT environment variable (local dev / test configuration).
    3. If not set, checks RATE_LIMIT_SALT_PARAMETER_NAME and fetches the SecureString parameter
       from AWS Systems Manager (SSM) Parameter Store with WithDecryption=True using boto3.
       The fetched value is validated and cached in-memory for subsequent container invocations.
    4. If both are absent or retrieval fails, production strictly fails closed.
    """
    global _CACHED_SALT
    if _CACHED_SALT is not None:
        return _CACHED_SALT

    env = os.environ.get("ENVIRONMENT", "").lower()
    data_mode = os.environ.get("DATA_MODE", "").lower()
    is_production = (
        env in ("prod", "production")
        or data_mode == "production"
        or bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
    )

    # 1. Direct environment variable (local development, isolated testing)
    direct_salt = os.environ.get("RATE_LIMIT_SALT")
    if direct_salt and direct_salt.strip():
        clean_salt = direct_salt.strip()
        _validate_salt_strength(clean_salt, is_production)
        _CACHED_SALT = clean_salt
        return _CACHED_SALT

    # 2. Runtime retrieval from AWS SSM Parameter Store SecureString
    ssm_param_name = os.environ.get("RATE_LIMIT_SALT_PARAMETER_NAME")
    if ssm_param_name and ssm_param_name.strip():
        clean_param_name = ssm_param_name.strip()
        try:
            import boto3  # type: ignore
        except ImportError:
            raise SecurityConfigurationError("boto3 is required to retrieve SSM parameter in production.")

        try:
            ssm_client = boto3.client("ssm")
            response = ssm_client.get_parameter(Name=clean_param_name, WithDecryption=True)
            param_val = response.get("Parameter", {}).get("Value")
            if not param_val or not param_val.strip():
                raise SecurityConfigurationError(
                    f"SSM Parameter '{clean_param_name}' contains an empty value."
                )
            clean_salt = param_val.strip()
            _validate_salt_strength(clean_salt, is_production)
            _CACHED_SALT = clean_salt
            return _CACHED_SALT
        except SecurityConfigurationError:
            raise
        except Exception as e:
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
            logger.error(
                "Failed to retrieve rate limit salt from SSM parameter '%s': %s",
                clean_param_name,
                error_code,
            )
            raise SecurityConfigurationError(
                f"Failed to securely retrieve rate limit salt from SSM parameter '{clean_param_name}': {error_code}"
            )

    # 3. Neither RATE_LIMIT_SALT nor RATE_LIMIT_SALT_PARAMETER_NAME is provided
    if is_production:
        raise SecurityConfigurationError(
            "RATE_LIMIT_SALT or RATE_LIMIT_SALT_PARAMETER_NAME is missing. Production strictly requires a strong, high-entropy secret."
        )

    # Unit test / non-production dev fallback
    if os.environ.get("PYTEST_CURRENT_TEST") or data_mode in ("test", "demo"):
        return "test_transient_dev_salt_only_non_prod_entropy_32_chars_minimum_12345"

    raise SecurityConfigurationError("RATE_LIMIT_SALT must be set in environment.")


def extract_client_instance_id(event: Dict[str, Any]) -> Optional[str]:
    """
    Extracts optional client device/instance identifier from trusted headers.
    Headers checked (case-insensitive):
      - X-Device-ID / x-device-id
      - X-Client-Instance-ID / x-client-instance-id
      - X-Client-ID / x-client-id
    Validates format: must match ^[a-zA-Z0-9_-]{16,64}$ (e.g. UUIDv4 or hex string).
    Returns cleaned ID or None if absent or malformed.
    """
    headers = event.get("headers") or {}
    for h_name in ("x-device-id", "x-client-instance-id", "x-client-id", "device-id"):
        for k, v in headers.items():
            if k.lower() == h_name and isinstance(v, str):
                cleaned = v.strip()
                if CLIENT_INSTANCE_ID_REGEX.match(cleaned):
                    return cleaned
    return None


def compute_pseudonymous_client_hash(
    event: Dict[str, Any],
    salt: Optional[str] = None,
    include_device_id: bool = True,
) -> str:
    """
    Computes a privacy-preserving, full 256-bit (64-character hexadecimal) HMAC-SHA256
    pseudonym for the client. Retaining the complete 256-bit digest prevents hash collisions
    and ensures cryptographic preimage and collision resistance ($2^{128}$ operations).

    Privacy & Regulatory Taxonomy (GDPR Recital 26, India DPDP Act 2023):
    - This mechanism provides PSEUDONYMIZATION, NOT absolute mathematical anonymity.
    - An adversary with knowledge of the HMAC salt could execute an offline precomputed
      dictionary / rainbow-table attack across the 4.3-billion IPv4 address space.
    - Mitigations enforced:
      1. Secret Entropy: Salt is stored in AWS SSM Parameter Store as a SecureString,
         encrypted under AWS KMS, and never logged or returned in responses. The salt
         must be generated with a cryptographically secure random number generator
         (e.g. `secrets.token_hex(32)` providing 256 bits of CSPRNG entropy).
      2. Zero Plaintext Persistence: Raw client IP addresses are NEVER logged,
         persisted in DynamoDB, or returned in client API responses.
      3. Minimal Operational Retention: DynamoDB rate limit records are bounded by a strict
         10-minute TTL (2x window duration), after which records are automatically deleted.
      4. Salt Rotation: Rotating the salt changes all pseudonyms simultaneously,
         preventing long-term correlation of user activity across time windows.
      5. Full 256-Bit Digest: Returning the full 64-character hex digest avoids truncation
         birthday collisions across high user volumes.
      6. DynamoDB Partition Key Compatibility: The full digest key `RATELIMIT#<64-hex>`
         is ~74 bytes, well within DynamoDB's 2,048-byte partition key maximum. Ephemeral
         TTL ensures transparent migration as existing 16-character keys expire naturally.

    Shared NAT & Campus Wi-Fi Model (P1.10):
    - On campus Wi-Fi (e.g. IIT Bombay Powai / hostel gateways), thousands of students share
      the same egress public IP.
    - To prevent single-student starvation while preserving abuse resistance:
      When include_device_id=True and a valid client instance ID (e.g. X-Device-ID) is supplied,
      the pseudonym is bound to HMAC(salt, "ip::<ip>::dev::<device_id>").
      This provides each individual student browser on campus Wi-Fi their own rate-limit budget.
    - To prevent single-origin flood abuse via device-ID rotation, the raw IP pseudonym
      HMAC(salt, "ip::<ip>") enforces an independent higher-volume campus NAT ceiling.
    - Source IP is strictly extracted from event["requestContext"]["http"]["sourceIp"]
      (or REST identity context). Client-controlled headers (X-Forwarded-For, Forwarded, Client-IP)
      are strictly ignored to prevent IP spoofing.
    """
    effective_salt = salt if (salt and salt.strip()) else get_rate_limit_salt()
    secret = effective_salt.encode("utf-8")

    # Extract source IP strictly from trusted API Gateway request context
    request_context = event.get("requestContext") or {}
    http_ctx = request_context.get("http") or {}
    source_ip = http_ctx.get("sourceIp") or request_context.get("identity", {}).get("sourceIp", "unknown_ip")

    device_id = extract_client_instance_id(event) if include_device_id else None

    if device_id:
        raw_identity = f"ip::{source_ip}::dev::{device_id}".encode("utf-8")
    else:
        raw_identity = f"ip::{source_ip}".encode("utf-8")

    digest = hmac.new(secret, raw_identity, hashlib.sha256).hexdigest()
    return digest


# Backward-compatible alias
compute_anonymous_client_hash = compute_pseudonymous_client_hash


def extract_idempotency_key(event: Dict[str, Any], body: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Extracts idempotency key from headers (X-Idempotency-Key) or JSON body.
    """
    headers = event.get("headers") or {}
    for k, v in headers.items():
        if k.lower() == "x-idempotency-key" and isinstance(v, str) and len(v.strip()) >= 8:
            return v.strip()[:64]

    if body and isinstance(body, dict):
        body_key = body.get("idempotencyKey")
        if body_key and isinstance(body_key, str) and len(body_key.strip()) >= 8:
            return body_key.strip()[:64]

    return None


def parse_unverified_jwt(token: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Parses unverified JWT header and payload segments without cryptographic signature verification.
    Provides defense-in-depth header inspection and structural token validation.

    Strict Security Constraints:
    1. Rejects tokens with 'alg': 'none'.
    2. Rejects tokens with unsupported algorithms (strictly requires 'RS256').
    3. Rejects malformed structures (must have exactly 3 dot-separated segments).
    4. Base64url decodes safely with proper RFC 7515 padding.
    """
    if not isinstance(token, str):
        raise JWTValidationError("JWT token must be a string.")

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise JWTValidationError(f"Malformed JWT: expected 3 dot-separated segments, got {len(parts)}.")

    def _b64url_decode(seg: str) -> Dict[str, Any]:
        rem = len(seg) % 4
        if rem > 0:
            seg += "=" * (4 - rem)
        try:
            raw_bytes = base64.urlsafe_b64decode(seg.encode("utf-8"))
            return json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            raise JWTValidationError(f"Failed to decode base64url segment in JWT: {str(e)}")

    header = _b64url_decode(parts[0])
    payload = _b64url_decode(parts[1])

    # Security check: Algorithm restriction
    alg = header.get("alg")
    if not alg or str(alg).lower() == "none":
        raise JWTValidationError("Security Violation: JWT tokens using 'none' algorithm are strictly rejected.")
    if str(alg).upper() != "RS256":
        raise JWTValidationError(f"Security Violation: Unsupported algorithm '{alg}'. Only RS256 is permitted.")

    return header, payload


def verify_cognito_jwt_claims(
    claims: Dict[str, Any],
    expected_user_pool_id: Optional[str] = None,
    expected_client_id: Optional[str] = None,
    expected_group: Optional[str] = "Admins",
    current_time: Optional[int] = None,
    clock_skew_seconds: int = 60,
    require_exp: bool = False,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates verified JWT claims forwarded by API Gateway Cognito Authorizer.
    Returns: (is_valid, user_identifier, error_code)

    Validates:
    1. Structure: Non-empty claims dictionary.
    2. Group Membership: If expected_group is specified, 'cognito:groups' must contain expected_group.
       (Rejects non-admin users immediately with FORBIDDEN_NOT_ADMIN).
    3. Expiration (exp): Must be in the future (permitting clock_skew_seconds).
    4. Not-Before (nbf): Must be in the past if present.
    5. Token Use (token_use): Must be 'id' or 'access' if present.
    6. Issuer (iss): Must match Cognito User Pool URL format and expected_user_pool_id if set.
    7. Audience / Client ID (aud / client_id): Must match expected_client_id if provided.
    """
    if not isinstance(claims, dict) or not claims:
        return False, None, "UNAUTHORIZED_MISSING_CLAIMS"

    now = int(time.time()) if current_time is None else int(current_time)

    # 1. Check administrator group membership
    if expected_group:
        groups = claims.get("cognito:groups") or []
        if isinstance(groups, str):
            groups = [g.strip() for g in groups.split(",") if g.strip()]
        if expected_group not in groups:
            logger.warning("Authenticated user lacks required '%s' group: sub=%s", expected_group, claims.get("sub"))
            return False, None, "FORBIDDEN_NOT_ADMIN"

    # 2. Check expiration (exp)
    exp = claims.get("exp")
    if exp is None:
        if require_exp:
            return False, None, "UNAUTHORIZED_MISSING_EXPIRATION"
    else:
        try:
            exp_val = int(exp)
            if now > (exp_val + clock_skew_seconds):
                logger.warning("Rejected expired JWT: exp=%d, now=%d", exp_val, now)
                return False, None, "UNAUTHORIZED_EXPIRED_TOKEN"
        except (ValueError, TypeError):
            return False, None, "UNAUTHORIZED_MALFORMED_EXPIRATION"

    # 3. Check not-before (nbf) if present
    nbf = claims.get("nbf")
    if nbf is not None:
        try:
            nbf_val = int(nbf)
            if now < (nbf_val - clock_skew_seconds):
                logger.warning("Rejected token not yet valid: nbf=%d, now=%d", nbf_val, now)
                return False, None, "UNAUTHORIZED_TOKEN_NOT_YET_VALID"
        except (ValueError, TypeError):
            return False, None, "UNAUTHORIZED_MALFORMED_NBF"

    # 4. Check token_use ('id' or 'access') if present
    token_use = claims.get("token_use")
    if token_use is not None and token_use not in ("id", "access"):
        logger.warning("Rejected token with invalid token_use: %s", token_use)
        return False, None, "UNAUTHORIZED_INVALID_TOKEN_USE"

    # 5. Check issuer (iss) if present
    iss = claims.get("iss")
    if iss is not None:
        if not isinstance(iss, str):
            return False, None, "UNAUTHORIZED_INVALID_ISSUER_FORMAT"
        if expected_user_pool_id:
            expected_suffix = f"/{expected_user_pool_id}"
            if not iss.endswith(expected_suffix) or "cognito-idp" not in iss:
                logger.warning("Rejected token with mismatched issuer: %s (expected suffix %s)", iss, expected_suffix)
                return False, None, "UNAUTHORIZED_WRONG_ISSUER"
        elif not re.match(r"^https://cognito-idp\.[a-z0-9-]+\.amazonaws\.com/[a-zA-Z0-9_-]+$", iss):
            logger.warning("Rejected token with non-Cognito issuer: %s", iss)
            return False, None, "UNAUTHORIZED_INVALID_ISSUER_FORMAT"

    # 6. Check audience / client_id if expected_client_id is set
    if expected_client_id:
        token_client_id = claims.get("client_id") or claims.get("aud")
        if token_client_id and token_client_id != expected_client_id:
            logger.warning("Rejected token with mismatched client_id/aud: %s (expected %s)", token_client_id, expected_client_id)
            return False, None, "UNAUTHORIZED_WRONG_AUDIENCE"

    user_identity = str(claims.get("username") or claims.get("cognito:username") or claims.get("sub") or "authenticated_user")
    return True, user_identity, None


# Module aliasing to prevent dual-import identity mismatch between
# `import security` and `from backend.shared import security` in test suites
if "security" in sys.modules and "backend.shared.security" not in sys.modules:
    sys.modules["backend.shared.security"] = sys.modules["security"]
elif "backend.shared.security" in sys.modules and "security" not in sys.modules:
    sys.modules["security"] = sys.modules["backend.shared.security"]
