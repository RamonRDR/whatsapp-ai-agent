"""Deterministic isolated test environment. No external credentials or network."""

import pytest
from fastapi.testclient import TestClient

from whatsapp_ai_agent.api import create_app
from whatsapp_ai_agent.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        database_url="sqlite:///" + str(tmp_path / "test.db"),
        app_env="local",
        demo_enabled=True,
        admin_api_key="unit-test-admin-secret",
        webhook_verify_token="test-verify-token",
        meta_app_secret="test-app-secret",
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as browser:
        yield browser
