"""Shared test fixtures for the inference proxy test suite."""

from __future__ import annotations

from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inference_proxy.config.dependencies import get_settings
from inference_proxy.config.settings import (
    EtcdSettings,
    GatewaySettings,
    RoutingSettings,
    Settings,
)
from inference_proxy.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    """Return a Settings instance with test-safe defaults."""
    return Settings(
        gateway=GatewaySettings(host="127.0.0.1", port=9999),
        etcd=EtcdSettings(endpoints=["http://localhost:2379"], node_prefix="/test-nodes/"),
        routing=RoutingSettings(strategy="least_connections", max_retries=1, timeout=5),
    )


@pytest.fixture
def app(test_settings: Settings) -> Generator[FastAPI, None, None]:
    """Create a FastAPI app with test settings injected."""
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: test_settings
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Return a TestClient bound to the test app."""
    return TestClient(app)
