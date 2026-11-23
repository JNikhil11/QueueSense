"""
QueueSense - Security, Privacy & Throttling Utilities
Implements privacy-preserving client identity hashing, secure token checks,
and safe header extraction without exposing student IP addresses.
No hardcoded secret fallbacks in production.
"""

from __future__ import annotations
import hmac
import hashlib
import logging
import os
import sys
from typing import Dict, Any, Optional

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

# Module-level in-memory cache for the validated salt in the Lambda execution environment
_CACHED_SALT: Optional[str] = None


class SecurityConfigurationError(Exception):
    """Raised when required security credentials or salt configurations are missing or weak."""
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
    """Validates that the provided salt meets strict production entropy requirements."""
    if is_production:
        if len(clean_salt) < 32:
            raise SecurityConfigurationError(
                "RATE_LIMIT_SALT has insufficient entropy. Minimum 32 characters required in production (e.g. 256-bit hex)."
            )
        clean_lower = clean_salt.lower()
        if any(p in clean_lower for p in WEAK_SALT_PATTERNS):
            raise SecurityConfigurationError(
                "RATE_LIMIT_SALT matches a predictable or weak pattern. Provide a cryptographically random secret."
            )


def get_rate_limit_salt() -> str:
    """
    Retrieves the required HMAC salt for anonymous client hashing.
    Fails closed if the secret is missing or insecure in production.
    Strictly requires a cryptographically strong secret (>= 32 characters, e.g. 256-bit hex).

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
            from botocore.exceptions import ClientError  # type: ignore
        except ImportError:
            ClientError = Exception  # type: ignore

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
            # ClientError, AccessDenied, ParameterNotFound, KMS decryption failure, etc.
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


def compute_anonymous_client_hash(
    event: Dict[str, Any],
    salt: Optional[str] = None,
) -> str:
    """
    Computes an anonymous, privacy-preserving 16-character HMAC-SHA256 hash
    of the client based exclusively on the trusted source IP address.

    Security & Privacy Model:
    1. Source IP is extracted exclusively from the trusted AWS API Gateway request context:
       - HTTP API v2: event["requestContext"]["http"]["sourceIp"]
       - REST API: event["requestContext"]["identity"]["sourceIp"]
       Client-supplied headers (such as X-Forwarded-For or Forwarded) are strictly ignored
       to prevent IP spoofing.
    2. Client-controlled User-Agent is deliberately EXCLUDED from the hash to prevent
       adversaries from trivially resetting their rate-limit window by rotating headers.
    3. The raw IP address is NEVER logged, persisted, or stored in plaintext. Only the
       one-way HMAC digest is used as the rate-limiting partition key.
    4. Campus NAT / Shared IP Trade-off:
       In campus Wi-Fi environments (e.g., IIT Bombay Powai / hostel gateways), multiple students
       may share a common public egress NAT IP. The rate-limit window (5 requests per 5 minutes)
       accommodates normal group arrivals while mitigating automated submission floods.
       Independent route-level throttling at API Gateway (Burst 20, Rate 10) provides independent
       protection against volumetric spikes.
    """
    effective_salt = salt if (salt and salt.strip()) else get_rate_limit_salt()
    secret = effective_salt.encode("utf-8")

    # Extract source IP strictly from trusted API Gateway request context
    request_context = event.get("requestContext") or {}
    http_ctx = request_context.get("http") or {}
    source_ip = http_ctx.get("sourceIp") or request_context.get("identity", {}).get("sourceIp", "unknown_ip")

    # Identity is strictly bound to trusted source IP and one-way HMAC salt
    raw_identity = f"ip::{source_ip}".encode("utf-8")
    digest = hmac.new(secret, raw_identity, hashlib.sha256).hexdigest()
    return digest[:16]


def extract_idempotency_key(event: Dict[str, Any], body: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Extracts idempotency key from headers (X-Idempotency-Key) or JSON body.
    """
    headers = event.get("headers") or {}
    header_key = headers.get("x-idempotency-key") or headers.get("X-Idempotency-Key")
    if header_key and isinstance(header_key, str) and len(header_key.strip()) >= 8:
        return header_key.strip()[:64]

    if body and isinstance(body, dict):
        body_key = body.get("idempotencyKey")
        if body_key and isinstance(body_key, str) and len(body_key.strip()) >= 8:
            return body_key.strip()[:64]

    return None


# Module aliasing to prevent dual-import identity mismatch between
# `import security` and `from backend.shared import security` in test suites
if "security" in sys.modules and "backend.shared.security" not in sys.modules:
    sys.modules["backend.shared.security"] = sys.modules["security"]
elif "backend.shared.security" in sys.modules and "security" not in sys.modules:
    sys.modules["security"] = sys.modules["backend.shared.security"]

