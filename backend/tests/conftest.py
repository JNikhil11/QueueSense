import os
import pytest
from backend.shared.database import reset_shared_test_adapter

@pytest.fixture(autouse=True)
def configure_test_env(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "memory")
    monkeypatch.setenv("DATA_MODE", "test")
    monkeypatch.setenv("ADMIN_API_KEY", "queuesense-admin-secret-dev-key")
    reset_shared_test_adapter()
