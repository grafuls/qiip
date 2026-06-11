"""Unit tests for configuration settings loading and env var overrides."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings

from inference_proxy.config.settings import (
    EtcdSettings,
    GatewaySettings,
    RoutingSettings,
    Settings,
)


class TestDefaultGatewaySettings:
    def test_default_gateway_settings(self) -> None:
        settings = Settings()
        assert settings.gateway.host == "0.0.0.0"
        assert settings.gateway.port == 8080


class TestDefaultEtcdSettings:
    def test_default_etcd_settings(self) -> None:
        settings = Settings()
        assert settings.etcd.endpoints == ["http://localhost:2379"]
        assert settings.etcd.node_prefix == "/nodes/"


class TestDefaultRoutingSettings:
    def test_default_routing_settings(self) -> None:
        settings = Settings()
        assert settings.routing.strategy == "least_connections"
        assert settings.routing.health_check_interval == 30
        assert settings.routing.max_retries == 3
        assert settings.routing.timeout == 30


class TestEnvVarOverrideGatewayPort:
    def test_env_var_override_gateway_port(self, monkeypatch: object) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_GATEWAY__PORT", "9090")  # type: ignore[attr-defined]
        settings = Settings()
        assert settings.gateway.port == 9090


class TestEnvVarOverrideEtcdPrefix:
    def test_env_var_override_etcd_prefix(self, monkeypatch: object) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_ETCD__NODE_PREFIX", "/test-nodes/")  # type: ignore[attr-defined]
        settings = Settings()
        assert settings.etcd.node_prefix == "/test-nodes/"


class TestEnvVarOverrideRoutingStrategy:
    def test_env_var_override_routing_strategy(self, monkeypatch: object) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_ROUTING__STRATEGY", "round_robin")  # type: ignore[attr-defined]
        settings = Settings()
        assert settings.routing.strategy == "round_robin"


class TestSubModelsAreNotBaseSettings:
    def test_sub_models_are_not_base_settings(self) -> None:
        assert not issubclass(GatewaySettings, BaseSettings)
        assert not issubclass(EtcdSettings, BaseSettings)
        assert not issubclass(RoutingSettings, BaseSettings)
        assert issubclass(GatewaySettings, BaseModel)
        assert issubclass(EtcdSettings, BaseModel)
        assert issubclass(RoutingSettings, BaseModel)


class TestSettingsIsBaseSettings:
    def test_settings_is_base_settings(self) -> None:
        assert issubclass(Settings, BaseSettings)
