"""Unit tests for NodeProvisioner.

Tests mock SSHClient, EtcdClient, and httpx to verify the full
provisioning sequence: setup.sh -> start-vllm.sh -> health poll -> register.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import httpx
import pytest

from inference_proxy.config.settings import ProvisioningSettings
from inference_proxy.models.node import NodeStatus
from inference_proxy.provisioning.provisioner import (
    NodeProvisioner,
    PreflightError,
    ProvisioningError,
    _derive_container_name,
)
from inference_proxy.provisioning.ssh_client import (
    RemoteCommandError,
    SSHConnectionError,
)
from inference_proxy.provisioning.state import ProvisioningStep


def _make_provisioner(
    *,
    ssh_client: MagicMock | None = None,
    etcd_client: MagicMock | None = None,
    settings: ProvisioningSettings | None = None,
    registry: MagicMock | None = None,
    connection_tracker: MagicMock | None = None,
) -> NodeProvisioner:
    """Build a NodeProvisioner with mock dependencies."""
    return NodeProvisioner(
        ssh_client=ssh_client or MagicMock(),
        etcd_client=etcd_client or MagicMock(),
        settings=settings or ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0),
        registry=registry,
        connection_tracker=connection_tracker,
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

        with patch.object(provisioner, "preflight", new_callable=AsyncMock):
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
        etcd = MagicMock()
        etcd.prefix = "/nodes/"
        etcd.put = MagicMock(return_value=True)

        async def mock_streaming(host: str, command: str):
            yield ("stdout", "[STEP:nvidia_repo:START]")
            raise RemoteCommandError("host1", "bash setup.sh", 1)

        ssh.run_streaming = mock_streaming
        provisioner = _make_provisioner(ssh_client=ssh, etcd_client=etcd)

        with patch.object(provisioner, "preflight", new_callable=AsyncMock):
            with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = True
                with pytest.raises(ProvisioningError):
                    await provisioner.provision("host1")

    @pytest.mark.asyncio
    async def test_ssh_connection_error_wraps(self) -> None:
        ssh = MagicMock()
        etcd = MagicMock()
        etcd.prefix = "/nodes/"
        etcd.put = MagicMock(return_value=True)

        async def mock_streaming(host: str, command: str):
            raise SSHConnectionError("host1", "connection refused")
            # Make it an async generator
            yield  # pragma: no cover

        ssh.run_streaming = mock_streaming
        provisioner = _make_provisioner(ssh_client=ssh, etcd_client=etcd)

        with patch.object(provisioner, "preflight", new_callable=AsyncMock):
            with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = True
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


def _make_full_provisioner(etcd: MagicMock) -> tuple[NodeProvisioner, MagicMock]:
    """Build a provisioner with mocks suitable for full provision() tests."""
    ssh = MagicMock()

    async def mock_streaming(host: str, command: str):
        if "setup.sh" in command:
            for item in [("stdout", "[STEP:nvidia_repo:START]"), ("stdout", "[STEP:nvidia_repo:OK]")]:
                yield item
        elif "start-vllm.sh" in command:
            for item in [("stdout", "# Model:              Qwen/Qwen2.5-72B-Instruct")]:
                yield item

    ssh.run_streaming = mock_streaming
    etcd.prefix = "/nodes/"
    etcd.put = MagicMock(return_value=True)

    settings = ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0)
    provisioner = NodeProvisioner(ssh_client=ssh, etcd_client=etcd, settings=settings)
    return provisioner, ssh


class TestStateTracking:
    """D-05 through D-11: State machine tracking and PROVISIONING registration."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.provisioner.httpx.AsyncClient")
    async def test_full_success_transitions(self, mock_httpx_cls: MagicMock) -> None:
        """State writes go PENDING -> PREFLIGHT -> steps -> ... -> COMPLETE."""
        etcd = MagicMock()
        provisioner, _ = _make_full_provisioner(etcd)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        with patch.object(provisioner, "preflight", new_callable=AsyncMock):
            with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = True
                await provisioner.provision("host1")

        # Collect all etcd put calls -- both via to_thread and direct mock
        put_calls = mock_to_thread.call_args_list
        state_keys = []
        node_keys = []
        for c in put_calls:
            args = c[0]  # positional args: (etcd.put, key, value)
            if len(args) >= 3:
                key = args[1]
                if "/provisioning/" in key:
                    value = json.loads(args[2])
                    state_keys.append(value["current_step"])
                elif "/nodes/" in key:
                    node_keys.append(key)

        assert "pending" in state_keys
        assert "complete" in state_keys
        assert len(node_keys) >= 1  # PROVISIONING registration

    @pytest.mark.asyncio
    async def test_failed_state(self) -> None:
        """On failure, last state write has current_step=failed with details."""
        etcd = MagicMock()
        ssh = MagicMock()

        async def mock_streaming(host: str, command: str):
            if "setup.sh" in command:
                raise RemoteCommandError("host1", "bash setup.sh", 1)
                yield  # pragma: no cover

        ssh.run_streaming = mock_streaming
        etcd.prefix = "/nodes/"
        etcd.put = MagicMock(return_value=True)

        settings = ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0)
        provisioner = NodeProvisioner(ssh_client=ssh, etcd_client=etcd, settings=settings)

        with patch.object(provisioner, "preflight", new_callable=AsyncMock):
            with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = True
                with pytest.raises(ProvisioningError):
                    await provisioner.provision("host1")

        # Find the last /provisioning/ state write
        state_writes = []
        for c in mock_to_thread.call_args_list:
            args = c[0]
            if len(args) >= 3 and "/provisioning/" in str(args[1]):
                state_writes.append(json.loads(args[2]))

        assert len(state_writes) > 0
        last_state = state_writes[-1]
        assert last_state["current_step"] == "failed"
        assert last_state["failed_step"] is not None
        assert last_state["error"] is not None

    @pytest.mark.asyncio
    async def test_etcd_prefix(self) -> None:
        """State writes use /provisioning/{hostname}, not /nodes/ prefix (D-05)."""
        etcd = MagicMock()
        provisioner, _ = _make_full_provisioner(etcd)

        with patch.object(provisioner, "preflight", new_callable=AsyncMock):
            with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = True
                # provision() will fail at _poll_health without httpx mock, but
                # we only need to check early state writes
                with patch("inference_proxy.provisioning.provisioner.httpx.AsyncClient") as mock_httpx:
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_cl = AsyncMock()
                    mock_cl.get = AsyncMock(return_value=mock_resp)
                    mock_cl.__aenter__ = AsyncMock(return_value=mock_cl)
                    mock_cl.__aexit__ = AsyncMock(return_value=False)
                    mock_httpx.return_value = mock_cl
                    await provisioner.provision("host1")

        # All state writes should use /provisioning/ prefix
        for c in mock_to_thread.call_args_list:
            args = c[0]
            if len(args) >= 3:
                key = str(args[1])
                if "provisioning" in key.lower() and "nodes" not in key:
                    assert key.startswith("/provisioning/")

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.provisioner.httpx.AsyncClient")
    async def test_state_write_failure_continues(self, mock_httpx_cls: MagicMock) -> None:
        """State write exceptions are swallowed -- provisioning continues (Pitfall 3)."""
        etcd = MagicMock()
        provisioner, _ = _make_full_provisioner(etcd)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        call_count = 0

        async def flaky_to_thread(fn, *args):
            nonlocal call_count
            call_count += 1
            key = args[0] if args else ""
            # Fail all /provisioning/ writes, allow /nodes/ writes
            if isinstance(key, str) and "/provisioning/" in key:
                raise ConnectionError("etcd down")
            return True

        with patch.object(provisioner, "preflight", new_callable=AsyncMock):
            with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", side_effect=flaky_to_thread):
                # Should complete despite state write failures
                await provisioner.provision("host1")

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.provisioner.httpx.AsyncClient")
    async def test_registers_provisioning_before_setup(self, mock_httpx_cls: MagicMock) -> None:
        """D-09: First /nodes/ write creates node with status=provisioning."""
        etcd = MagicMock()
        provisioner, _ = _make_full_provisioner(etcd)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        with patch.object(provisioner, "preflight", new_callable=AsyncMock):
            with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = True
                with patch("inference_proxy.provisioning.provisioner.node_to_etcd") as mock_ser:
                    mock_ser.return_value = ("/nodes/host1", b'{"status":"provisioning"}')
                    await provisioner.provision("host1")

                    # Find the first call to node_to_etcd
                    first_call = mock_ser.call_args_list[0]
                    node = first_call[0][0]
                    assert node.status == NodeStatus.PROVISIONING

    @pytest.mark.asyncio
    async def test_preflight_called_before_setup(self) -> None:
        """Preflight failure prevents _run_setup from running."""
        etcd = MagicMock()
        etcd.prefix = "/nodes/"
        etcd.put = MagicMock(return_value=True)
        provisioner, ssh = _make_full_provisioner(etcd)

        setup_called = False
        original_run_setup = provisioner._run_setup

        async def tracking_setup(hostname: str) -> None:
            nonlocal setup_called
            setup_called = True
            await original_run_setup(hostname)

        provisioner._run_setup = tracking_setup

        with patch.object(provisioner, "preflight", new_callable=AsyncMock) as mock_pf:
            mock_pf.side_effect = PreflightError("host1", ["no gpus"])
            with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                mock_to_thread.return_value = True
                with pytest.raises(PreflightError):
                    await provisioner.provision("host1")

        assert not setup_called


class TestContainerNameDerivation:
    """Container name derived from model name per start-vllm.sh convention."""

    def test_model_with_org(self) -> None:
        assert _derive_container_name("Qwen/Qwen2.5-72B-Instruct") == "vllm-qwen2.5-72b-instruct"

    def test_model_without_org(self) -> None:
        assert _derive_container_name("some-model") == "vllm-some-model"

    def test_model_multiple_slashes(self) -> None:
        assert _derive_container_name("org/sub/Model-Name") == "vllm-model-name"


def _make_teardown_provisioner(
    *,
    model: str = "Qwen/Qwen2.5-72B-Instruct",
    tracker_get_returns: int | list[int] = 0,
    force: bool = False,
) -> tuple[NodeProvisioner, MagicMock, MagicMock, MagicMock, list[str]]:
    """Build a provisioner wired for teardown testing.

    Returns (provisioner, ssh_mock, etcd_mock, registry_mock, state_steps).
    state_steps is populated during the test via side_effect on to_thread.
    """
    from inference_proxy.models.node import Node, NodeStatus

    ssh = MagicMock()
    etcd = MagicMock()
    etcd.prefix = "/nodes/"
    etcd.put = MagicMock(return_value=True)
    etcd.delete = MagicMock(return_value=True)

    registry = MagicMock()
    node = Node(
        node_id="host1",
        endpoint="host1:8000",
        status=NodeStatus.HEALTHY,
        model=model,
        last_heartbeat=datetime.now(timezone.utc),
    )
    registry.get.return_value = node
    registry.drain.return_value = True

    tracker = MagicMock()
    if isinstance(tracker_get_returns, list):
        tracker.get.side_effect = tracker_get_returns
    else:
        tracker.get.return_value = tracker_get_returns

    async def mock_streaming(host: str, command: str):
        for item in [("stdout", "container stopped")]:
            yield item

    ssh.run_streaming = mock_streaming

    provisioner = _make_provisioner(
        ssh_client=ssh,
        etcd_client=etcd,
        registry=registry,
        connection_tracker=tracker,
        settings=ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0, drain_timeout=2),
    )
    return provisioner, ssh, etcd, registry, tracker


class TestTeardownGraceful:
    """D-01, D-08, D-11, D-12: Graceful teardown drains, stops, deregisters."""

    @pytest.mark.asyncio
    async def test_graceful_teardown_sequence(self) -> None:
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner()
        state_steps: list[str] = []

        async def capture_to_thread(fn, *args):
            # Capture state writes to track step progression
            if fn == etcd.put and len(args) >= 2:
                key = args[0]
                if "/provisioning/" in str(key):
                    data = json.loads(args[1])
                    state_steps.append(data["current_step"])
            return True

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", side_effect=capture_to_thread):
            await provisioner.teardown("host1")

        # Verify drain was called
        registry.drain.assert_called_once_with("host1")
        # Verify state progression: DRAINING -> STOPPING_CONTAINER -> DEREGISTERING -> TEARDOWN_COMPLETE
        assert "draining" in state_steps
        assert "stopping_container" in state_steps
        assert "deregistering" in state_steps
        assert "teardown_complete" in state_steps

    @pytest.mark.asyncio
    async def test_graceful_teardown_ssh_command(self) -> None:
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner()
        commands: list[str] = []

        async def mock_streaming(host: str, command: str):
            commands.append(command)
            for item in [("stdout", "ok")]:
                yield item

        ssh.run_streaming = mock_streaming

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_tt:
            mock_tt.return_value = True
            await provisioner.teardown("host1")

        # Should use podman stop + podman rm (graceful)
        assert any("podman stop" in c for c in commands)
        assert any("podman rm" in c for c in commands) or any("podman stop" in c and "podman rm" in c for c in commands)

    @pytest.mark.asyncio
    async def test_etcd_node_key_deleted(self) -> None:
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner()
        deleted_keys: list[str] = []

        async def capture_to_thread(fn, *args):
            if fn == etcd.delete:
                deleted_keys.append(args[0])
            return True

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", side_effect=capture_to_thread):
            await provisioner.teardown("host1")

        # D-11: should delete /nodes/host1
        assert "/nodes/host1" in deleted_keys


class TestTeardownForce:
    """D-03: Force teardown skips drain, uses podman rm --force."""

    @pytest.mark.asyncio
    async def test_force_skips_drain(self) -> None:
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner()
        state_steps: list[str] = []

        async def capture_to_thread(fn, *args):
            if fn == etcd.put and len(args) >= 2 and "/provisioning/" in str(args[0]):
                data = json.loads(args[1])
                state_steps.append(data["current_step"])
            return True

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", side_effect=capture_to_thread):
            await provisioner.teardown("host1", force=True)

        # Force mode should NOT have DRAINING step
        assert "draining" not in state_steps
        # But should still have the rest
        assert "stopping_container" in state_steps
        assert "deregistering" in state_steps
        assert "teardown_complete" in state_steps
        # registry.drain should NOT be called
        registry.drain.assert_not_called()

    @pytest.mark.asyncio
    async def test_force_uses_podman_rm_force(self) -> None:
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner()
        commands: list[str] = []

        async def mock_streaming(host: str, command: str):
            commands.append(command)
            for item in [("stdout", "ok")]:
                yield item

        ssh.run_streaming = mock_streaming

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_tt:
            mock_tt.return_value = True
            await provisioner.teardown("host1", force=True)

        assert any("podman rm --force" in c for c in commands)


class TestDrainTimeout:
    """D-09: Drain timeout expiry proceeds to container stop."""

    @pytest.mark.asyncio
    async def test_timeout_proceeds_to_stop(self) -> None:
        """Connections never reach 0 but teardown still completes after timeout."""
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner(
            tracker_get_returns=5,  # always 5 connections
        )
        state_steps: list[str] = []

        async def capture_to_thread(fn, *args):
            if fn == etcd.put and len(args) >= 2 and "/provisioning/" in str(args[0]):
                data = json.loads(args[1])
                state_steps.append(data["current_step"])
            return True

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", side_effect=capture_to_thread):
            await provisioner.teardown("host1")

        # Should still complete despite never draining
        assert "stopping_container" in state_steps
        assert "teardown_complete" in state_steps


class TestTeardownStateProgression:
    """D-05: State tracked step-by-step in etcd."""

    @pytest.mark.asyncio
    async def test_graceful_state_order(self) -> None:
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner()
        state_steps: list[str] = []

        async def capture_to_thread(fn, *args):
            if fn == etcd.put and len(args) >= 2 and "/provisioning/" in str(args[0]):
                data = json.loads(args[1])
                state_steps.append(data["current_step"])
            return True

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", side_effect=capture_to_thread):
            await provisioner.teardown("host1")

        expected_order = ["draining", "stopping_container", "deregistering", "teardown_complete"]
        assert state_steps == expected_order

    @pytest.mark.asyncio
    async def test_force_state_order(self) -> None:
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner()
        state_steps: list[str] = []

        async def capture_to_thread(fn, *args):
            if fn == etcd.put and len(args) >= 2 and "/provisioning/" in str(args[0]):
                data = json.loads(args[1])
                state_steps.append(data["current_step"])
            return True

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", side_effect=capture_to_thread):
            await provisioner.teardown("host1", force=True)

        expected_order = ["stopping_container", "deregistering", "teardown_complete"]
        assert state_steps == expected_order


class TestTeardownSSHFailure:
    """Teardown with SSH failure updates state to FAILED."""

    @pytest.mark.asyncio
    async def test_ssh_failure_sets_failed_state(self) -> None:
        provisioner, ssh, etcd, registry, tracker = _make_teardown_provisioner()
        state_steps: list[str] = []

        async def failing_streaming(host: str, command: str):
            raise SSHConnectionError("host1", "connection refused")
            yield  # pragma: no cover

        ssh.run_streaming = failing_streaming

        async def capture_to_thread(fn, *args):
            if fn == etcd.put and len(args) >= 2 and "/provisioning/" in str(args[0]):
                data = json.loads(args[1])
                state_steps.append(data["current_step"])
            return True

        with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", side_effect=capture_to_thread):
            with pytest.raises(ProvisioningError):
                await provisioner.teardown("host1", force=True)

        assert "failed" in state_steps
