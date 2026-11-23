"""
QueueSense - Security, Privacy & Throttling Utilities
Implements privacy-preserving client identity hashing, secure token checks,
and safe header extraction without exposing student IP addresses.
No hardcoded secret fallbacks in production.
"""

from __future__ import annotations
import hmac
import hashlib
import os
from typing import Dict, Any, Optional

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


class SecurityConfigurationError(Exception):
    """Raised when required security credentials or salt configurations are missing or weak."""
    pass


def get_rate_limit_salt() -> str:
    """
    Retrieves the required HMAC salt for anonymous client hashing.
    Fails closed if the secret is missing or insecure in production.
    Strictly requires a cryptographically strong secret (>= 32 characters, e.g. 256-bit hex).
    """
    salt = os.environ.get("RATE_LIMIT_SALT")
    env = os.environ.get("ENVIRONMENT", "").lower()
    data_mode = os.environ.get("DATA_MODE", "").lower()
    is_production = (
        env in ("prod", "production")
        or data_mode == "production"
        or bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
    )

    if not salt or not salt.strip():
        if is_production:
            raise SecurityConfigurationError(
                "RATE_LIMIT_SALT environment variable is missing. Production strictly requires a strong, high-entropy secret."
            )
        # Unit test / non-production dev fallback
        if os.environ.get("PYTEST_CURRENT_TEST") or data_mode in ("test", "demo"):
            return "test_transient_dev_salt_only_non_prod_entropy_32_chars_minimum_12345"
        raise SecurityConfigurationError("RATE_LIMIT_SALT must be set in environment.")

    clean_salt = salt.strip()
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

    return clean_salt


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
