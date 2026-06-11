"""Dependency injection providers for application configuration.

Settings are provided via ``@lru_cache`` so the same instance is reused
across requests.  In tests, use ``app.dependency_overrides[get_settings]``
to inject test-specific settings -- never call ``get_settings()`` directly
in application code.
"""

from functools import lru_cache

from .settings import Settings


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
