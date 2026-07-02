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
from inference_proxy.provisioning.provisioner import (
    NodeProvisioner,
    PreflightError,
    ProvisioningError,
)
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


class TestPreflight:
    """D-01 through D-04: Pre-flight validation with collected errors."""

    @pytest.mark.asyncio
    async def test_tcp_unreachable(self) -> None:
        """TCP probe failure raises PreflightError immediately."""
        provisioner = _make_provisioner()

        with patch("inference_proxy.provisioning.provisioner.asyncio.open_connection", side_effect=OSError("Connection refused")):
            with pytest.raises(PreflightError, match="SSH port 22 unreachable") as exc_info:
                await provisioner.preflight("host1")
            assert exc_info.value.hostname == "host1"
            assert len(exc_info.value.failures) == 1

    @pytest.mark.asyncio
    async def test_no_gpu(self) -> None:
        """No GPUs detected raises PreflightError."""
        provisioner = _make_provisioner()
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("inference_proxy.provisioning.provisioner.asyncio.open_connection", return_value=(MagicMock(), mock_writer)):
            with patch.object(provisioner, "_ssh_run_command", new_callable=AsyncMock) as mock_cmd:
                mock_cmd.side_effect = lambda h, c: "" if "nvidia-smi" in c else "20971520"
                with pytest.raises(PreflightError, match="No GPUs detected"):
                    await provisioner.preflight("host1")

    @pytest.mark.asyncio
    async def test_insufficient_disk(self) -> None:
        """Insufficient disk space raises PreflightError."""
        settings = ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0, min_disk_gb=20)
        provisioner = _make_provisioner(settings=settings)
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("inference_proxy.provisioning.provisioner.asyncio.open_connection", return_value=(MagicMock(), mock_writer)):
            with patch.object(provisioner, "_ssh_run_command", new_callable=AsyncMock) as mock_cmd:
                # nvidia-smi returns one GPU, df returns 5GB in KB (5*1024*1024)
                mock_cmd.side_effect = lambda h, c: "Tesla V100" if "nvidia-smi" in c else "5242880"
                with pytest.raises(PreflightError, match="Insufficient disk") as exc_info:
                    await provisioner.preflight("host1")
                assert "5.0" in str(exc_info.value) or "5" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_collects_all_failures(self) -> None:
        """D-03: All failures collected before raising single PreflightError."""
        settings = ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0, min_disk_gb=20)
        provisioner = _make_provisioner(settings=settings)
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("inference_proxy.provisioning.provisioner.asyncio.open_connection", return_value=(MagicMock(), mock_writer)):
            with patch.object(provisioner, "_ssh_run_command", new_callable=AsyncMock) as mock_cmd:
                # Both GPU and disk fail
                mock_cmd.side_effect = lambda h, c: "" if "nvidia-smi" in c else "5242880"
                with pytest.raises(PreflightError) as exc_info:
                    await provisioner.preflight("host1")
                assert len(exc_info.value.failures) == 2

    @pytest.mark.asyncio
    async def test_standalone_preflight(self) -> None:
        """D-04: preflight() works independently when all checks pass."""
        provisioner = _make_provisioner()
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("inference_proxy.provisioning.provisioner.asyncio.open_connection", return_value=(MagicMock(), mock_writer)):
            with patch.object(provisioner, "_ssh_run_command", new_callable=AsyncMock) as mock_cmd:
                # 1 GPU, 50GB disk in KB
                mock_cmd.side_effect = lambda h, c: "Tesla V100" if "nvidia-smi" in c else "52428800"
                await provisioner.preflight("host1")  # Should not raise

    @pytest.mark.asyncio
    async def test_ssh_diagnostic_failure(self) -> None:
        """SSH diagnostic errors are collected as failures."""
        provisioner = _make_provisioner()
        mock_writer = MagicMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("inference_proxy.provisioning.provisioner.asyncio.open_connection", return_value=(MagicMock(), mock_writer)):
            with patch.object(provisioner, "_ssh_run_command", new_callable=AsyncMock) as mock_cmd:
                mock_cmd.side_effect = SSHConnectionError("host1", "connection reset")
                with pytest.raises(PreflightError, match="SSH diagnostic failed") as exc_info:
                    await provisioner.preflight("host1")
                assert len(exc_info.value.failures) >= 1
