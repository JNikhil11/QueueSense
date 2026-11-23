import os
import pytest
from backend.shared.database import reset_shared_test_adapter

@pytest.fixture(autouse=True)
def configure_test_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    monkeypatch.setenv("DATA_MODE", "test")
    monkeypatch.setenv("ADMIN_API_KEY", "queuesense-admin-secret-dev-key")
    monkeypatch.setenv("RATE_LIMIT_SALT", "test_transient_test_salt_min_16_chars_1234")
    reset_shared_test_adapter()
