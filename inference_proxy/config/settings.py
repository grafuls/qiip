"""Application settings via pydantic-settings.

Sub-models inherit from BaseModel (not BaseSettings) to ensure
nested env var resolution works correctly through the root Settings class.
Only the root Settings class inherits from BaseSettings.
"""

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseModel):
    """Gateway server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080


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
