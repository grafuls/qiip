"""Unit tests for configuration settings loading and env var overrides."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings

from inference_proxy.config.settings import (
    DashboardSettings,
    EtcdSettings,
    GatewaySettings,
    RoutingSettings,
    Settings,
)


class TestDefaultGatewaySettings:
    def test_default_gateway_settings(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.gateway.host == "0.0.0.0"
        assert settings.gateway.port == 8080


class TestDefaultEtcdSettings:
    def test_default_etcd_settings(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.etcd.endpoints == ["http://localhost:2379"]
        assert settings.etcd.node_prefix == "/nodes/"


class TestDefaultRoutingSettings:
    def test_default_routing_settings(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.routing.strategy == "least_connections"
        assert settings.routing.health_check_interval == 30
        assert settings.routing.max_retries == 3
        assert settings.routing.timeout == 30


class TestEnvVarOverrideGatewayPort:
    def test_env_var_override_gateway_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_GATEWAY__PORT", "9090")
        settings = Settings(_env_file=None)
        assert settings.gateway.port == 9090


class TestEnvVarOverrideEtcdPrefix:
    def test_env_var_override_etcd_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_ETCD__NODE_PREFIX", "/test-nodes/")
        settings = Settings(_env_file=None)
        assert settings.etcd.node_prefix == "/test-nodes/"


class TestEnvVarOverrideRoutingStrategy:
    def test_env_var_override_routing_strategy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_ROUTING__STRATEGY", "round_robin")
        settings = Settings(_env_file=None)
        assert settings.routing.strategy == "round_robin"


class TestDefaultDashboardSettings:
    def test_default_dashboard_poll_interval(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.dashboard.poll_interval == 10


class TestEnvVarOverrideDashboardPollInterval:
    def test_env_var_override_dashboard_poll_interval(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_DASHBOARD__POLL_INTERVAL", "30")
        settings = Settings(_env_file=None)
        assert settings.dashboard.poll_interval == 30


class TestSubModelsAreNotBaseSettings:
    def test_sub_models_are_not_base_settings(self) -> None:
        assert not issubclass(GatewaySettings, BaseSettings)
        assert not issubclass(EtcdSettings, BaseSettings)
        assert not issubclass(RoutingSettings, BaseSettings)
        assert not issubclass(DashboardSettings, BaseSettings)
        assert issubclass(GatewaySettings, BaseModel)
        assert issubclass(EtcdSettings, BaseModel)
        assert issubclass(RoutingSettings, BaseModel)
        assert issubclass(DashboardSettings, BaseModel)


class TestEtcdSettingsEmptyEndpointsRejected:
    """EtcdSettings rejects an empty endpoints list with a validation error."""

    def test_empty_endpoints_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="At least one etcd endpoint must be configured"):
            EtcdSettings(endpoints=[])


class TestSettingsIsBaseSettings:
    def test_settings_is_base_settings(self) -> None:
        assert issubclass(Settings, BaseSettings)
