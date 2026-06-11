"""Application settings via pydantic-settings.

Sub-models inherit from BaseModel (not BaseSettings) to ensure
nested env var resolution works correctly through the root Settings class.
Only the root Settings class inherits from BaseSettings.
"""

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseModel):
    """Gateway server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080


class EtcdSettings(BaseModel):
    """etcd service discovery configuration."""

    endpoints: list[str] = ["http://localhost:2379"]
    node_prefix: str = "/nodes/"

    @field_validator("endpoints")
    @classmethod
    def endpoints_must_be_non_empty(cls, v: list[str]) -> list[str]:
        """Ensure at least one etcd endpoint is configured."""
        if not v:
            raise ValueError("At least one etcd endpoint must be configured")
        return v


class RoutingSettings(BaseModel):
    """Request routing and load balancing configuration."""

    strategy: str = "least_connections"
    health_check_interval: int = 30
    max_retries: int = 3
    timeout: int = 30


class LoggingSettings(BaseModel):
    """Logging configuration."""

    json_output: bool = False
    level: str = "INFO"


class Settings(BaseSettings):
    """Root application settings.

    Loads configuration from environment variables with the prefix
    ``INFERENCE_PROXY_`` and nested delimiter ``__``.

    Example env var: ``INFERENCE_PROXY_GATEWAY__PORT=9090``
    """

    model_config = SettingsConfigDict(
        env_prefix="INFERENCE_PROXY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    gateway: GatewaySettings = GatewaySettings()
    etcd: EtcdSettings = EtcdSettings()
    routing: RoutingSettings = RoutingSettings()
    logging: LoggingSettings = LoggingSettings()
