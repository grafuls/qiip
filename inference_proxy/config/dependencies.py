"""Dependency injection providers for application configuration and services.

Settings are provided via ``@lru_cache`` so the same instance is reused
across requests.  The node registry and proxy client are stored in
``app.state`` during lifespan and exposed via ``get_registry()`` and
``get_proxy_client()`` -- per-request dependencies that read from the
current application instance.

In tests, use ``app.dependency_overrides[get_settings]``,
``app.dependency_overrides[get_registry]``, or
``app.dependency_overrides[get_proxy_client]`` to inject test-specific
instances.
"""

from functools import lru_cache

from fastapi import Request

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.llmfit.runner import LLMFitRunner
from inference_proxy.provisioning.provisioner import NodeProvisioner
from inference_proxy.proxy.client import ProxyClient
from inference_proxy.quads.client import QUADSClient
from inference_proxy.quads.poller import QUADSPoller
from inference_proxy.redfish.client import RedfishClient
from inference_proxy.resilience.circuit_breaker import CircuitBreakerRegistry
from inference_proxy.routing.node_selector import NodeSelector
from inference_proxy.routing.request_metrics import RequestMetrics

from inference_proxy.services.unified_nodes import UnifiedNodeService

from .settings import Settings


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()


def get_registry(request: Request) -> NodeRegistry:
    """Return the node registry from the current application state.

    The registry is created during lifespan startup and stored in
    ``app.state.registry`` (per D-07).  This dependency makes it
    available to FastAPI route handlers via ``Depends(get_registry)``.
    """
    return request.app.state.registry  # type: ignore[no-any-return]


def get_proxy_client(request: Request) -> ProxyClient:
    """Return the proxy client from the current application state.

    The proxy client is created during lifespan startup and stored in
    ``app.state.proxy_client``.  This dependency makes it available to
    FastAPI route handlers via ``Depends(get_proxy_client)``.
    """
    return request.app.state.proxy_client  # type: ignore[no-any-return]


def get_circuit_breaker_registry(request: Request) -> CircuitBreakerRegistry:
    """Return the circuit breaker registry from the current application state.

    The registry is created during lifespan startup and stored in
    ``app.state.circuit_breaker_registry``.  This dependency makes it
    available to FastAPI route handlers via
    ``Depends(get_circuit_breaker_registry)``.
    """
    return request.app.state.circuit_breaker_registry  # type: ignore[no-any-return]


def get_request_metrics(request: Request) -> RequestMetrics:
    """Return the request metrics from the current application state.

    The metrics instance is created during lifespan startup and stored in
    ``app.state.request_metrics``.  This dependency makes it available to
    FastAPI route handlers via ``Depends(get_request_metrics)``.
    """
    return request.app.state.request_metrics  # type: ignore[no-any-return]


def get_node_selector(request: Request) -> NodeSelector:
    """Return the node selector from the current application state.

    The node selector is created during lifespan startup and stored in
    ``app.state.node_selector``.  This dependency makes it available to
    FastAPI route handlers via ``Depends(get_node_selector)``.
    """
    return request.app.state.node_selector  # type: ignore[no-any-return]


def get_provisioner(request: Request) -> NodeProvisioner:
    """Return the node provisioner from the current application state."""
    return request.app.state.provisioner  # type: ignore[no-any-return]


def get_quads_client(request: Request) -> QUADSClient | None:
    """Return the QUADS client, or None when QUADS is not configured (D-10)."""
    return request.app.state.quads_client  # type: ignore[no-any-return]


def get_llmfit_runner(request: Request) -> LLMFitRunner:
    """Return the LLMFit runner from the current application state."""
    return request.app.state.llmfit_runner  # type: ignore[no-any-return]


def get_redfish_client(request: Request) -> RedfishClient | None:
    """Return the Redfish client, or None when Redfish is not configured."""
    return request.app.state.redfish_client  # type: ignore[no-any-return]


def get_quads_poller(request: Request) -> QUADSPoller | None:
    """Return the QUADS poller, or None when QUADS is not configured.

    Phase 17 consumes this to merge QUADS hosts with etcd nodes.
    """
    return request.app.state.quads_poller  # type: ignore[no-any-return]


def get_unified_node_service(request: Request) -> UnifiedNodeService:
    """Build UnifiedNodeService from app.state components."""
    return UnifiedNodeService(
        registry=request.app.state.registry,
        poller=request.app.state.quads_poller,
        cb_registry=request.app.state.circuit_breaker_registry,
        tracker=request.app.state.node_selector.tracker,
    )
