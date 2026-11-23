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


class SecurityConfigurationError(Exception):
    """Raised when required security credentials or salt configurations are missing."""
    pass


def get_rate_limit_salt() -> str:
    """
    Retrieves the required HMAC salt for anonymous client hashing.
    Fails closed if the secret is missing or insecure in production.
    """
    salt = os.environ.get("RATE_LIMIT_SALT")
    env = os.environ.get("ENVIRONMENT", "").lower()
    data_mode = os.environ.get("DATA_MODE", "").lower()
    is_production = env in ("prod", "production") or data_mode == "production" or bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    if not salt or not salt.strip():
        if is_production:
            raise SecurityConfigurationError(
                "RATE_LIMIT_SALT environment variable is missing. Production strictly requires a strong, high-entropy secret."
            )
        # Check if running in a unit test environment
        if os.environ.get("PYTEST_CURRENT_TEST") or data_mode in ("test", "demo"):
            return "test_transient_dev_salt_only_non_prod_123456"
        raise SecurityConfigurationError("RATE_LIMIT_SALT must be set in environment.")

    clean_salt = salt.strip()
    if is_production and len(clean_salt) < 16:
        raise SecurityConfigurationError(
            "RATE_LIMIT_SALT is insufficiently secure. Minimum 16 characters required in production."
        )

    return clean_salt


def compute_anonymous_client_hash(
    event: Dict[str, Any],
    salt: Optional[str] = None,
) -> str:
    """
    Computes an anonymous, privacy-preserving 16-character hash of the client
    based on the source IP and User-Agent.
    The raw IP address is NEVER logged, stored, or persisted.
    """
    effective_salt = salt if (salt and salt.strip()) else get_rate_limit_salt()
    secret = effective_salt.encode("utf-8")

    # Extract source IP from HTTP API v2 or REST API event
    request_context = event.get("requestContext") or {}
    http_ctx = request_context.get("http") or {}
    source_ip = http_ctx.get("sourceIp") or request_context.get("identity", {}).get("sourceIp", "unknown_ip")

    headers = event.get("headers") or {}
    user_agent = headers.get("user-agent", "unknown_agent")

    raw_identity = f"{source_ip}::{user_agent}".encode("utf-8")
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
