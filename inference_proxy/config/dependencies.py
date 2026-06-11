"""Dependency injection providers for application configuration and services.

Settings are provided via ``@lru_cache`` so the same instance is reused
across requests.  The node registry is stored in ``app.state`` during
lifespan and exposed via ``get_registry()`` -- a per-request dependency
that reads from the current application instance.

In tests, use ``app.dependency_overrides[get_settings]`` or
``app.dependency_overrides[get_registry]`` to inject test-specific
instances.
"""

from functools import lru_cache

from fastapi import Request

from inference_proxy.discovery.registry import NodeRegistry

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
