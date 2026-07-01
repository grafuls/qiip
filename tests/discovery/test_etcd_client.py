"""Unit tests for the etcd client wrapper.

Tests verify that EtcdClient correctly parses endpoint URLs from
EtcdSettings and delegates operations to the underlying etcd3gw client.
All tests mock etcd3gw to avoid requiring a live etcd server.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from inference_proxy.config.settings import EtcdSettings
from inference_proxy.discovery.etcd_client import EtcdClient


class TestEtcdClientInit:
    """EtcdClient.__init__ parses endpoint URL and creates Etcd3Client."""

    @patch("inference_proxy.discovery.etcd_client.Etcd3Client")
    def test_parses_endpoint_url(self, mock_etcd3_cls: MagicMock) -> None:
        settings = EtcdSettings(
            endpoints=["http://etcd.internal:2379"],
            node_prefix="/nodes/",
        )

        EtcdClient(settings)

        mock_etcd3_cls.assert_called_once_with(
            host="etcd.internal",
            port=2379,
            protocol="http",
            timeout=5,
        )


class TestEtcdClientGetPrefix:
    """get_prefix() delegates to underlying client with configured prefix."""

    @patch("inference_proxy.discovery.etcd_client.Etcd3Client")
    def test_delegates_get_prefix(self, mock_etcd3_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.get_prefix.return_value = [
            (b'{"endpoint": "http://10.0.1.100:8000"}', {"key": b"/nodes/node-1"}),
        ]
        mock_etcd3_cls.return_value = mock_instance

        settings = EtcdSettings(
            endpoints=["http://localhost:2379"],
            node_prefix="/test-nodes/",
        )
        client = EtcdClient(settings)
        result = client.get_prefix()

        mock_instance.get_prefix.assert_called_once_with("/test-nodes/")
        assert len(result) == 1


class TestEtcdClientWatchPrefix:
    """watch_prefix() delegates to underlying client and returns (iter, cancel)."""

    @patch("inference_proxy.discovery.etcd_client.Etcd3Client")
    def test_delegates_watch_prefix(self, mock_etcd3_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_events = iter([{"kv": {"key": "/nodes/node-1"}}])
        mock_cancel = MagicMock()
        mock_instance.watch_prefix.return_value = (mock_events, mock_cancel)
        mock_etcd3_cls.return_value = mock_instance

        settings = EtcdSettings(
            endpoints=["http://localhost:2379"],
            node_prefix="/nodes/",
        )
        client = EtcdClient(settings)
        events_iter, cancel_fn = client.watch_prefix()

        mock_instance.watch_prefix.assert_called_once_with("/nodes/")
        assert cancel_fn is mock_cancel


class TestEtcdClientPrefixProperty:
    """EtcdClient exposes prefix property returning the configured node_prefix."""

    @patch("inference_proxy.discovery.etcd_client.Etcd3Client")
    def test_prefix_property(self, mock_etcd3_cls: MagicMock) -> None:
        settings = EtcdSettings(
            endpoints=["http://localhost:2379"],
            node_prefix="/custom-prefix/",
        )
        client = EtcdClient(settings)

        assert client.prefix == "/custom-prefix/"


class TestEtcdClientDefaultPort:
    """EtcdClient.__init__ handles endpoint without explicit port (defaults to 2379)."""

    @patch("inference_proxy.discovery.etcd_client.Etcd3Client")
    def test_default_port(self, mock_etcd3_cls: MagicMock) -> None:
        settings = EtcdSettings(
            endpoints=["http://etcd.internal"],
            node_prefix="/nodes/",
        )

        EtcdClient(settings)

        mock_etcd3_cls.assert_called_once_with(
            host="etcd.internal",
            port=2379,
            protocol="http",
            timeout=5,
        )


class TestEtcdClientHttpsProtocol:
    """EtcdClient.__init__ handles https protocol in endpoint URL."""

    @patch("inference_proxy.discovery.etcd_client.Etcd3Client")
    def test_https_protocol(self, mock_etcd3_cls: MagicMock) -> None:
        settings = EtcdSettings(
            endpoints=["https://secure-etcd.internal:2380"],
            node_prefix="/nodes/",
        )

        EtcdClient(settings)

        mock_etcd3_cls.assert_called_once_with(
            host="secure-etcd.internal",
            port=2380,
            protocol="https",
            timeout=5,
        )


class TestEtcdClientSchemelessEndpointRejected:
    """EtcdClient.__init__ raises ValueError for endpoint URLs missing a scheme."""

    def test_schemeless_endpoint_raises_value_error(self) -> None:
        settings = EtcdSettings(
            endpoints=["etcd.internal:2379"],
            node_prefix="/nodes/",
        )
        with pytest.raises(ValueError, match="Invalid etcd endpoint URL"):
            EtcdClient(settings)

    def test_hostname_only_endpoint_raises_value_error(self) -> None:
        settings = EtcdSettings(
            endpoints=["etcd.internal"],
            node_prefix="/nodes/",
        )
        with pytest.raises(ValueError, match="Invalid etcd endpoint URL"):
            EtcdClient(settings)


class TestEtcdClientPut:
    """EtcdClient.put() delegates to underlying etcd3gw client."""

    @patch("inference_proxy.discovery.etcd_client.Etcd3Client")
    def test_delegates_put(self, mock_etcd3_cls: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.put.return_value = True
        mock_etcd3_cls.return_value = mock_instance

        settings = EtcdSettings(
            endpoints=["http://localhost:2379"],
            node_prefix="/nodes/",
        )
        client = EtcdClient(settings)
        result = client.put("/nodes/host-1", b'{"endpoint": "http://host-1:8000"}')

        mock_instance.put.assert_called_once_with(
            "/nodes/host-1", b'{"endpoint": "http://host-1:8000"}'
        )
        assert result is True


class TestEtcdClientMultipleEndpointsWarning:
    """EtcdClient.__init__ logs warning when multiple endpoints configured."""

    @patch("inference_proxy.discovery.etcd_client.Etcd3Client")
    @patch("inference_proxy.discovery.etcd_client.logger")
    def test_multiple_endpoints_logs_warning(
        self, mock_logger: MagicMock, mock_etcd3_cls: MagicMock
    ) -> None:
        settings = EtcdSettings(
            endpoints=["http://etcd1:2379", "http://etcd2:2379"],
            node_prefix="/nodes/",
        )
        EtcdClient(settings)
        mock_logger.warning.assert_called_once_with(
            "multiple etcd endpoints configured but only the first is used",
            endpoint="http://etcd1:2379",
            ignored=["http://etcd2:2379"],
        )
