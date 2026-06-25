"""Shared test fixtures for the inference proxy test suite."""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inference_proxy.config.dependencies import (
    get_circuit_breaker_registry,
    get_node_selector,
    get_proxy_client,
    get_settings,
)
from inference_proxy.config.settings import (
    EtcdSettings,
    GatewaySettings,
    RoutingSettings,
    Settings,
)
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.main import create_app
from inference_proxy.proxy.client import ProxyClient
from inference_proxy.resilience.circuit_breaker import CircuitBreakerRegistry
from inference_proxy.routing.connection_tracker import ConnectionTracker
from inference_proxy.routing.node_selector import NodeSelector


@pytest.fixture
def test_settings() -> Settings:
    """Return a Settings instance with test-safe defaults."""
    return Settings(
        gateway=GatewaySettings(host="127.0.0.1", port=9999),
        etcd=EtcdSettings(endpoints=["http://localhost:2379"], node_prefix="/test-nodes/"),
        routing=RoutingSettings(strategy="least_connections", max_retries=3, timeout=5),
    )


@pytest.fixture
def test_registry() -> NodeRegistry:
    """Return a fresh empty NodeRegistry for testing."""
    return NodeRegistry()


@pytest.fixture
async def mock_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """Yield a real httpx.AsyncClient for use with httpx_mock."""
    client = httpx.AsyncClient()
    yield client
    await client.aclose()


@pytest.fixture
def proxy_client(mock_http_client: httpx.AsyncClient) -> ProxyClient:
    """Return a ProxyClient wrapping the mock HTTP client."""
    return ProxyClient(mock_http_client)


@pytest.fixture
def connection_tracker() -> ConnectionTracker:
    """Return a fresh ConnectionTracker for testing."""
    return ConnectionTracker()


@pytest.fixture
def circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Return a fresh CircuitBreakerRegistry for testing."""
    return CircuitBreakerRegistry()


@pytest.fixture
def node_selector(
    test_registry: NodeRegistry,
    connection_tracker: ConnectionTracker,
) -> NodeSelector:
    """Return a NodeSelector wired to the test registry and tracker."""
    return NodeSelector(test_registry, connection_tracker)


@pytest.fixture
def app(
    test_settings: Settings,
    test_registry: NodeRegistry,
    proxy_client: ProxyClient,
    node_selector: NodeSelector,
    circuit_breaker_registry: CircuitBreakerRegistry,
) -> Generator[FastAPI, None, None]:
    """Create a FastAPI app with test settings, registry, and proxy client injected."""
    application = create_app(settings=test_settings)
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.state.registry = test_registry
    application.state.proxy_client = proxy_client
    application.state.node_selector = node_selector
    application.state.circuit_breaker_registry = circuit_breaker_registry
    application.state.shutting_down = False
    application.dependency_overrides[get_proxy_client] = lambda: proxy_client
    application.dependency_overrides[get_node_selector] = lambda: node_selector
    application.dependency_overrides[get_circuit_breaker_registry] = (
        lambda: circuit_breaker_registry
    )
    yield application
    application.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Return a TestClient bound to the test app."""
    return TestClient(app)
