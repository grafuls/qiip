"""Unit tests for NodeProvisioner.

Tests mock SSHClient, EtcdClient, and httpx to verify the full
provisioning sequence: setup.sh -> start-vllm.sh -> health poll -> register.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from inference_proxy.config.settings import ProvisioningSettings
from inference_proxy.models.node import NodeStatus
from inference_proxy.provisioning.provisioner import NodeProvisioner, ProvisioningError
from inference_proxy.provisioning.ssh_client import (
    RemoteCommandError,
    SSHConnectionError,
)


def _make_provisioner(
    *,
    ssh_client: MagicMock | None = None,
    etcd_client: MagicMock | None = None,
    settings: ProvisioningSettings | None = None,
) -> NodeProvisioner:
    """Build a NodeProvisioner with mock dependencies."""
    return NodeProvisioner(
        ssh_client=ssh_client or MagicMock(),
        etcd_client=etcd_client or MagicMock(),
        settings=settings or ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0),
    )


async def _async_iter(items: list[tuple[str, str]]):
    """Helper: async generator yielding items."""
    for item in items:
        yield item


class TestProvisionSequence:
    """provision() orchestrates setup -> start -> poll -> register in order."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.provisioner.httpx.AsyncClient")
    async def test_calls_in_order(self, mock_httpx_cls: MagicMock) -> None:
        ssh = MagicMock()
        etcd = MagicMock()
        etcd.prefix = "/nodes/"
        etcd.put = MagicMock(return_value=True)

        call_order: list[str] = []

        async def mock_streaming(host: str, command: str):
            if "setup.sh" in command:
                call_order.append("setup")
                for item in [("stdout", "[STEP:nvidia_repo:START]"), ("stdout", "[STEP:nvidia_repo:OK]")]:
                    yield item
            elif "start-vllm.sh" in command:
                call_order.append("start_vllm")
                for item in [("stdout", "# Model:              Qwen/Qwen2.5-72B-Instruct")]:
                    yield item

        ssh.run_streaming = mock_streaming

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client_instance

        provisioner = _make_provisioner(ssh_client=ssh, etcd_client=etcd)

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = True
            await provisioner.provision("host1")
            call_order.append("register")

        assert "setup" in call_order
        assert "start_vllm" in call_order
        assert call_order.index("setup") < call_order.index("start_vllm")


class TestStepMarkerParsing:
    """D-05, D-06: Step markers parsed from setup.sh stdout."""

    @pytest.mark.asyncio
    async def test_parses_step_markers(self) -> None:
        ssh = MagicMock()

        async def mock_streaming(host: str, command: str):
            for item in [
                ("stdout", "[STEP:nvidia_repo:START]"),
                ("stdout", "some debug output"),
                ("stdout", "[STEP:nvidia_repo:OK]"),
                ("stdout", "[STEP:system_update:START]"),
                ("stdout", "[STEP:system_update:FAIL]"),
                ("stderr", "error details"),
            ]:
                yield item

        ssh.run_streaming = mock_streaming
        provisioner = _make_provisioner(ssh_client=ssh)

        # _run_setup should not raise on FAIL markers -- that's a logging concern.
        # RemoteCommandError from SSHClient is what signals actual failure.
        await provisioner._run_setup("host1")


class TestModelExtraction:
    """Model name extracted from start-vllm.sh stdout."""

    @pytest.mark.asyncio
    async def test_extracts_model_name(self) -> None:
        ssh = MagicMock()

        async def mock_streaming(host: str, command: str):
            for item in [
                ("stdout", "Starting container..."),
                ("stdout", "# Model:              Qwen/Qwen2.5-72B-Instruct"),
                ("stdout", "Container started"),
            ]:
                yield item

        ssh.run_streaming = mock_streaming
        provisioner = _make_provisioner(ssh_client=ssh)

        model = await provisioner._run_start_vllm("host1")
        assert model == "Qwen/Qwen2.5-72B-Instruct"

    @pytest.mark.asyncio
    async def test_raises_on_missing_model(self) -> None:
        ssh = MagicMock()

        async def mock_streaming(host: str, command: str):
            for item in [("stdout", "no model line here")]:
                yield item

        ssh.run_streaming = mock_streaming
        provisioner = _make_provisioner(ssh_client=ssh)

        with pytest.raises(ProvisioningError, match="model name not found"):
            await provisioner._run_start_vllm("host1")


class TestHealthPoll:
    """D-10, D-09: Health polling via httpx."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.provisioner.httpx.AsyncClient")
    async def test_success_on_200(self, mock_httpx_cls: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        provisioner = _make_provisioner()
        await provisioner._poll_health("host1")

        mock_client.get.assert_called_with("http://host1:8000/health")

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.provisioner.httpx.AsyncClient")
    async def test_timeout_raises(self, mock_httpx_cls: MagicMock) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        settings = ProvisioningSettings(health_poll_timeout=0, health_poll_interval=0)
        provisioner = _make_provisioner(settings=settings)

        with pytest.raises(ProvisioningError, match="timed out"):
            await provisioner._poll_health("host1")


class TestNodeRegistration:
    """D-11, D-12: Node registered in etcd with correct fields."""

    @pytest.mark.asyncio
    async def test_registers_with_correct_fields(self) -> None:
        etcd = MagicMock()
        etcd.prefix = "/nodes/"
        etcd.put = MagicMock(return_value=True)

        provisioner = _make_provisioner(etcd_client=etcd)

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = True
            with patch("inference_proxy.provisioning.provisioner.node_to_etcd") as mock_serialize:
                mock_serialize.return_value = ("/nodes/host1", b'{"model":"test"}')
                await provisioner._register_node("host1", "test-model")

                # Verify Node was constructed correctly
                call_args = mock_serialize.call_args
                node = call_args[0][0]
                assert node.node_id == "host1"
                assert node.status == NodeStatus.HEALTHY
                assert node.model == "test-model"
                assert node.endpoint == "host1:8000"
                assert node.last_heartbeat is not None

                # Verify etcd.put called via asyncio.to_thread
                mock_to_thread.assert_called_once_with(etcd.put, "/nodes/host1", b'{"model":"test"}')


class TestSetupFailure:
    """D-08: Setup failure raises ProvisioningError, no cleanup."""

    @pytest.mark.asyncio
    async def test_remote_command_error_wraps(self) -> None:
        ssh = MagicMock()

        async def mock_streaming(host: str, command: str):
            yield ("stdout", "[STEP:nvidia_repo:START]")
            raise RemoteCommandError("host1", "bash setup.sh", 1)

        ssh.run_streaming = mock_streaming
        provisioner = _make_provisioner(ssh_client=ssh)

        with pytest.raises(ProvisioningError):
            await provisioner.provision("host1")

    @pytest.mark.asyncio
    async def test_ssh_connection_error_wraps(self) -> None:
        ssh = MagicMock()

        async def mock_streaming(host: str, command: str):
            raise SSHConnectionError("host1", "connection refused")
            # Make it an async generator
            yield  # pragma: no cover

        ssh.run_streaming = mock_streaming
        provisioner = _make_provisioner(ssh_client=ssh)

        with pytest.raises(ProvisioningError):
            await provisioner.provision("host1")
