"""Unit tests for the SSHClient wrapper.

All tests mock asyncssh to avoid requiring real SSH connections.
Tests verify connection parameters, stdout/stderr streaming,
error handling, and DIP compliance.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from inference_proxy.config.settings import SSHSettings
from inference_proxy.provisioning.ssh_client import (
    RemoteCommandError,
    SSHClient,
    SSHConnectionError,
)


def _make_settings(**overrides: object) -> SSHSettings:
    defaults = {
        "key_path": Path("/tmp/test_key"),
        "username": "testuser",
        "connect_timeout": 5,
    }
    defaults.update(overrides)
    return SSHSettings(**defaults)


class TestSSHClientConnectParams:
    """D-03, D-04: asyncssh.connect called with correct parameters."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.ssh_client.asyncssh")
    async def test_connect_params(self, mock_asyncssh: MagicMock) -> None:
        settings = _make_settings()
        client = SSHClient(settings)

        # Set up the mock chain: connect -> conn -> create_process -> process
        mock_process = AsyncMock()
        mock_process.stdout.__aiter__ = AsyncMock(return_value=aiter([]))
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value="")
        mock_process.exit_status = 0

        mock_conn = AsyncMock()
        mock_conn.create_process = MagicMock(return_value=_async_cm(mock_process))

        mock_asyncssh.connect = MagicMock(return_value=_async_cm(mock_conn))

        lines = [line async for line in client.run_streaming("host1", "echo hi")]

        mock_asyncssh.connect.assert_called_once_with(
            "host1",
            username="testuser",
            client_keys=["/tmp/test_key"],
            known_hosts=None,
            connect_timeout=5,
        )


class TestSSHClientStdoutStreaming:
    """D-05: run_streaming yields (stdout, line) tuples."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.ssh_client.asyncssh")
    async def test_yields_stdout_lines(self, mock_asyncssh: MagicMock) -> None:
        settings = _make_settings()
        client = SSHClient(settings)

        mock_process = AsyncMock()
        mock_process.stdout.__aiter__ = AsyncMock(
            return_value=aiter(["line1\n", "line2\n"])
        )
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value="")
        mock_process.exit_status = 0

        mock_conn = AsyncMock()
        mock_conn.create_process = MagicMock(return_value=_async_cm(mock_process))
        mock_asyncssh.connect = MagicMock(return_value=_async_cm(mock_conn))

        lines = [line async for line in client.run_streaming("host1", "ls")]

        assert lines == [("stdout", "line1"), ("stdout", "line2")]


class TestSSHClientStderrStreaming:
    """D-07: stderr lines yielded separately after stdout."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.ssh_client.asyncssh")
    async def test_yields_stderr_lines(self, mock_asyncssh: MagicMock) -> None:
        settings = _make_settings()
        client = SSHClient(settings)

        mock_process = AsyncMock()
        mock_process.stdout.__aiter__ = AsyncMock(
            return_value=aiter(["out\n"])
        )
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value="warn1\nwarn2\n")
        mock_process.exit_status = 0

        mock_conn = AsyncMock()
        mock_conn.create_process = MagicMock(return_value=_async_cm(mock_process))
        mock_asyncssh.connect = MagicMock(return_value=_async_cm(mock_conn))

        lines = [line async for line in client.run_streaming("host1", "cmd")]

        assert ("stdout", "out") in lines
        assert ("stderr", "warn1") in lines
        assert ("stderr", "warn2") in lines


class TestSSHClientNonZeroExit:
    """RemoteCommandError raised on non-zero exit status."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.ssh_client.asyncssh")
    async def test_raises_remote_command_error(self, mock_asyncssh: MagicMock) -> None:
        settings = _make_settings()
        client = SSHClient(settings)

        mock_process = AsyncMock()
        mock_process.stdout.__aiter__ = AsyncMock(return_value=aiter([]))
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value="")
        mock_process.exit_status = 1

        mock_conn = AsyncMock()
        mock_conn.create_process = MagicMock(return_value=_async_cm(mock_process))
        mock_asyncssh.connect = MagicMock(return_value=_async_cm(mock_conn))

        with pytest.raises(RemoteCommandError) as exc_info:
            async for _ in client.run_streaming("host1", "fail"):
                pass

        assert exc_info.value.host == "host1"
        assert exc_info.value.command == "fail"
        assert exc_info.value.exit_status == 1


class TestSSHClientConnectionError:
    """SSHConnectionError wraps asyncssh auth/disconnect/OS errors."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.ssh_client.asyncssh")
    async def test_wraps_permission_denied(self, mock_asyncssh: MagicMock) -> None:
        settings = _make_settings()
        client = SSHClient(settings)

        # Make asyncssh.PermissionDenied available as the actual exception class
        mock_asyncssh.PermissionDenied = type("PermissionDenied", (Exception,), {})
        mock_asyncssh.DisconnectError = type(
            "DisconnectError", (Exception,), {"reason": "test"}
        )

        mock_asyncssh.connect = MagicMock(
            return_value=_async_cm_raises(mock_asyncssh.PermissionDenied("denied"))
        )

        with pytest.raises(SSHConnectionError) as exc_info:
            async for _ in client.run_streaming("host1", "cmd"):
                pass

        assert exc_info.value.host == "host1"
        assert "authentication failed" in exc_info.value.reason

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.ssh_client.asyncssh")
    async def test_wraps_os_error(self, mock_asyncssh: MagicMock) -> None:
        settings = _make_settings()
        client = SSHClient(settings)

        mock_asyncssh.PermissionDenied = type("PermissionDenied", (Exception,), {})
        mock_asyncssh.DisconnectError = type(
            "DisconnectError", (Exception,), {"reason": "test"}
        )

        mock_asyncssh.connect = MagicMock(
            return_value=_async_cm_raises(OSError("Connection refused"))
        )

        with pytest.raises(SSHConnectionError) as exc_info:
            async for _ in client.run_streaming("host1", "cmd"):
                pass

        assert exc_info.value.host == "host1"
        assert "Connection refused" in exc_info.value.reason


# -- Helpers --


async def aiter(items: list[str]):  # noqa: ANN201
    """Create an async iterator from a list."""
    for item in items:
        yield item


class _async_cm:
    """Minimal async context manager wrapping a return value."""

    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self):  # noqa: ANN204
        return self._value

    async def __aexit__(self, *args: object) -> None:
        pass


class _async_cm_raises:
    """Async context manager that raises on __aenter__."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self):  # noqa: ANN204
        raise self._exc

    async def __aexit__(self, *args: object) -> None:
        pass
