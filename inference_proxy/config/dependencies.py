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
from inference_proxy.proxy.client import ProxyClient
from inference_proxy.routing.node_selector import NodeSelector

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


def get_node_selector(request: Request) -> NodeSelector:
    """Return the node selector from the current application state.

    The node selector is created during lifespan startup and stored in
    ``app.state.node_selector``.  This dependency makes it available to
    FastAPI route handlers via ``Depends(get_node_selector)``.
    """
    return request.app.state.node_selector  # type: ignore[no-any-return]
