"""Unit tests for configuration settings loading and env var overrides."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings

from inference_proxy.config.settings import (
    DashboardSettings,
    EtcdSettings,
    GatewaySettings,
    ProvisioningSettings,
    RoutingSettings,
    SSHSettings,
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


class TestDefaultSSHSettings:
    """D-01, D-02, D-04: SSHSettings defaults."""

    def test_default_key_path(self) -> None:
        from pathlib import Path

        settings = Settings(_env_file=None)
        assert settings.ssh.key_path == Path("~/.ssh/id_rsa")

    def test_default_username(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.ssh.username == "root"

    def test_default_connect_timeout(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.ssh.connect_timeout == 10


class TestDefaultProvisioningSettings:
    """D-09, D-17: ProvisioningSettings defaults."""

    def test_default_health_poll_timeout(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.provisioning.health_poll_timeout == 600

    def test_default_health_poll_interval(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.provisioning.health_poll_interval == 10

    def test_default_vllm_port(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.provisioning.vllm_port == 8000


class TestEnvVarOverrideSSHUsername:
    def test_env_var_override_ssh_username(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_SSH__USERNAME", "deploy")
        settings = Settings(_env_file=None)
        assert settings.ssh.username == "deploy"


class TestEnvVarOverrideProvisioningTimeout:
    def test_env_var_override_provisioning_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_PROVISIONING__HEALTH_POLL_TIMEOUT", "300")
        settings = Settings(_env_file=None)
        assert settings.provisioning.health_poll_timeout == 300


class TestSSHAndProvisioningAreNotBaseSettings:
    def test_ssh_settings_is_base_model_not_base_settings(self) -> None:
        assert not issubclass(SSHSettings, BaseSettings)
        assert issubclass(SSHSettings, BaseModel)

    def test_provisioning_settings_is_base_model_not_base_settings(self) -> None:
        assert not issubclass(ProvisioningSettings, BaseSettings)
        assert issubclass(ProvisioningSettings, BaseModel)


class TestSettingsIsBaseSettings:
    def test_settings_is_base_settings(self) -> None:
        assert issubclass(Settings, BaseSettings)
