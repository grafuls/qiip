# Phase 25: Core Models and Runner - Pattern Map

**Mapped:** 2026-07-24
**Files analyzed:** 9 (4 new, 1 modified, 4 test files)
**Analogs found:** 5 / 5 (all production files have exact or role-match analogs)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/models/llmfit.py` | model | transform | `inference_proxy/models/quads.py` | exact |
| `inference_proxy/llmfit/__init__.py` | config | -- | `inference_proxy/redfish/__init__.py` | exact |
| `inference_proxy/llmfit/errors.py` | model | -- | `inference_proxy/redfish/errors.py` | exact |
| `inference_proxy/llmfit/runner.py` | service | request-response | `inference_proxy/provisioning/ssh_client.py` | role-match |
| `inference_proxy/provisioning/ssh_client.py` | service | request-response | (self -- add `run()` mirroring `run_streaming()`) | exact |
| `tests/models/test_llmfit.py` | test | -- | `tests/models/test_quads.py` | exact |
| `tests/llmfit/__init__.py` | config | -- | `tests/provisioning/__init__.py` | exact |
| `tests/llmfit/test_runner.py` | test | -- | `tests/provisioning/test_ssh_client.py` | exact |
| `tests/provisioning/test_ssh_client.py` | test | -- | (self -- extend with `TestSSHClientRun`) | exact |

## Pattern Assignments

### `inference_proxy/models/llmfit.py` (model, transform)

**Analog:** `inference_proxy/models/quads.py`

**Imports pattern** (quads.py lines 1-10):
```python
"""QUADS host domain model.

Represents a GPU host from the QUADS inventory.  Only the fields
needed by the gateway are captured (D-04); extra fields from the
QUADS API response are silently ignored (Pydantic v2 default).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
```

**Core model pattern** (quads.py lines 13-21):
```python
class QUADSHost(BaseModel):
    """A GPU host from the QUADS inventory."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    gpu_vendor: str
    gpu_model: str
    gpu_count: int
```

**Key difference from analog:** llmfit models MUST use `ConfigDict(frozen=True, extra="ignore")` (not just `frozen=True`) because llmfit CLI output may add fields across versions. The `quads.py` model relies on Pydantic v2 default behavior for extras, but `extra="ignore"` makes this explicit for forward compatibility per research recommendation.

**Secondary analog for defaults pattern** (node.py lines 31-38):
```python
class NodeCapabilities(BaseModel):
    """Hardware and serving capabilities of a node."""

    model_config = ConfigDict(frozen=True)

    max_tokens: int = 4096
    gpu_memory: str = ""
```

Use this default-value pattern for `SystemInfo` and `ModelRecommendation` optional fields (e.g., `gpu_name: str = ""`, `score: float = 0.0`).

---

### `inference_proxy/llmfit/errors.py` (model, error hierarchy)

**Analog:** `inference_proxy/redfish/errors.py`

**Imports pattern** (redfish/errors.py lines 1-8):
```python
"""Redfish error types and human-readable error mapping (DIAG-03).
...
"""

from __future__ import annotations
```

**Base error pattern** (redfish/errors.py lines 13-17):
```python
class RedfishError(Exception):
    """Raised when a Redfish BMC operation fails."""

    def __init__(self, human_message: str) -> None:
        self.human_message = human_message
        super().__init__(human_message)
```

**Key adaptation:** `LLMFitError` is simpler (no `human_message` attribute needed). Subclasses `LLMFitTimeoutError` and `LLMFitParseError` store domain-specific context (`host`/`timeout` and `reason`/`raw_output` respectively). Follow the SSH error pattern (ssh_client.py lines 23-46) for storing structured attributes:

**Structured error attributes pattern** (ssh_client.py lines 23-46):
```python
class SSHConnectionError(Exception):
    """Raised when SSH connection to a host fails."""

    def __init__(self, host: str, reason: str) -> None:
        self.host = host
        self.reason = reason
        super().__init__(f"SSH connection to {host} failed: {reason}")


class RemoteCommandError(Exception):
    """Raised when a remote command exits with non-zero status."""

    def __init__(
        self, host: str, command: str, exit_status: int, stderr: str = ""
    ) -> None:
        self.host = host
        self.command = command
        self.exit_status = exit_status
        self.stderr = stderr
        tail = _stderr_tail(stderr) if stderr else ""
        msg = f"Command '{command}' on {host} exited with status {exit_status}"
        if tail:
            msg += f"\n--- stderr (last 50 lines) ---\n{tail}"
        super().__init__(msg)
```

---

### `inference_proxy/llmfit/runner.py` (service, request-response)

**Analog:** `inference_proxy/provisioning/ssh_client.py` (for SSHClient usage and DI pattern)

**Imports pattern** (ssh_client.py lines 1-20):
```python
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import asyncssh
import structlog

from inference_proxy.config.settings import SSHSettings

logger = structlog.get_logger()
```

Runner adaptation: imports `SSHClient` (not asyncssh directly -- DIP), `json` (stdlib), Pydantic `ValidationError`, and the llmfit models/errors.

**DI constructor pattern** (ssh_client.py lines 56-67):
```python
class SSHClient:
    def __init__(self, settings: SSHSettings) -> None:
        self._username = settings.username
        self._key_path = settings.key_path
        self._connect_timeout = settings.connect_timeout
```

Runner adaptation: `LLMFitRunner.__init__(self, ssh_client: SSHClient)` -- takes already-constructed SSHClient, stores as `self._ssh`.

**Error handling pattern -- SSH errors bubble unchanged** (ssh_client.py lines 107-116):
```python
except asyncssh.PermissionDenied as exc:
    raise SSHConnectionError(
        host, f"authentication failed: {exc}"
    ) from exc
except asyncssh.DisconnectError as exc:
    raise SSHConnectionError(
        host, f"disconnected: {exc.reason}"
    ) from exc
except OSError as exc:
    raise SSHConnectionError(host, str(exc)) from exc
```

Runner does NOT catch `SSHConnectionError` or `RemoteCommandError` -- per D-03 they bubble through unchanged. Runner only catches `asyncio.TimeoutError` (converts to `LLMFitTimeoutError`) and JSON/Pydantic parse failures (converts to `LLMFitParseError`).

---

### `inference_proxy/provisioning/ssh_client.py` MODIFIED (add `run()` method)

**Analog:** `run_streaming()` in the same file (lines 69-116)

**Connection block to replicate** (ssh_client.py lines 83-90):
```python
async with asyncssh.connect(
    host,
    username=self._username,
    client_keys=[str(self._key_path)],
    known_hosts=None,  # D-03: lab servers reimaged frequently
    connect_timeout=self._connect_timeout,
) as conn:
```

**Error handling block to replicate exactly** (ssh_client.py lines 107-116):
```python
except asyncssh.PermissionDenied as exc:
    raise SSHConnectionError(
        host, f"authentication failed: {exc}"
    ) from exc
except asyncssh.DisconnectError as exc:
    raise SSHConnectionError(
        host, f"disconnected: {exc.reason}"
    ) from exc
except OSError as exc:
    raise SSHConnectionError(host, str(exc)) from exc
```

**Non-zero exit check to replicate** (ssh_client.py lines 102-106):
```python
if process.exit_status is not None and process.exit_status != 0:
    raise RemoteCommandError(
        host, command, process.exit_status,
        stderr=stderr_output or "",
    )
```

**Key difference from `run_streaming()`:** Uses `conn.run(command)` instead of `conn.create_process(command)`. Wraps in `asyncio.wait_for(conn.run(command), timeout=timeout)` per D-02. Returns `tuple[str, str, int]` not `AsyncIterator`. Does NOT catch `asyncio.TimeoutError` -- it bubbles to the caller per D-03/research.

---

### `tests/models/test_llmfit.py` (test)

**Analog:** `tests/models/test_quads.py`

**Test class structure** (test_quads.py lines 1-47):
```python
"""Unit tests for the QUADSHost domain model."""

from __future__ import annotations

import pytest

from inference_proxy.models.quads import QUADSHost


class TestQUADSHostCreation:
    def test_all_fields_set_correctly(self) -> None:
        host = QUADSHost(
            hostname="gpu-host01",
            gpu_vendor="NVIDIA",
            gpu_model="A100",
            gpu_count=4,
        )
        assert host.hostname == "gpu-host01"


class TestQUADSHostFrozen:
    def test_assignment_raises_type_error(self) -> None:
        host = QUADSHost(...)
        with pytest.raises(Exception):
            host.hostname = "other"  # type: ignore[misc]


class TestQUADSHostExtraFieldsIgnored:
    def test_extra_kwarg_does_not_raise(self) -> None:
        host = QUADSHost(
            hostname="gpu-host01",
            gpu_vendor="NVIDIA",
            gpu_model="A100",
            gpu_count=4,
            interfaces=["eth0", "eth1"],  # type: ignore[call-arg]
        )
        assert host.hostname == "gpu-host01"
        assert not hasattr(host, "interfaces")
```

Pattern: one test class per behavior (`Creation`, `Frozen`, `ExtraFieldsIgnored`). Sync tests (no `@pytest.mark.asyncio`). Use `pytest.raises(Exception)` for frozen mutation.

---

### `tests/llmfit/test_runner.py` (test)

**Analog:** `tests/provisioning/test_ssh_client.py`

**Mock setup pattern** (test_ssh_client.py lines 23-55):
```python
def _make_settings(**overrides: object) -> SSHSettings:
    defaults: dict[str, object] = {
        "key_path": Path("/tmp/test_key"),
        "username": "testuser",
        "connect_timeout": 5,
    }
    defaults.update(overrides)
    return SSHSettings(**defaults)


def _setup_mock_asyncssh(
    mock_asyncssh: MagicMock,
    stdout_lines: list[str] | None = None,
    stderr_text: str = "",
    exit_status: int = 0,
) -> None:
    """Wire up mock_asyncssh with real exception classes and a mock process."""
    mock_asyncssh.PermissionDenied = type("PermissionDenied", (Exception,), {})
    mock_asyncssh.DisconnectError = type(
        "DisconnectError", (Exception,), {"reason": ""}
    )
    # ... mock process setup ...
```

**Test class pattern** (test_ssh_client.py lines 58-75):
```python
class TestSSHClientConnectParams:
    """D-03, D-04: asyncssh.connect called with correct parameters."""

    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.ssh_client.asyncssh")
    async def test_connect_params(self, mock_asyncssh: MagicMock) -> None:
        _setup_mock_asyncssh(mock_asyncssh)
        client = SSHClient(_make_settings())
        # ... assertions ...
```

**Error assertion pattern** (test_ssh_client.py lines 110-125):
```python
class TestSSHClientNonZeroExit:
    @pytest.mark.asyncio
    @patch("inference_proxy.provisioning.ssh_client.asyncssh")
    async def test_raises_remote_command_error(self, mock_asyncssh: MagicMock) -> None:
        _setup_mock_asyncssh(mock_asyncssh, exit_status=1)
        client = SSHClient(_make_settings())

        with pytest.raises(RemoteCommandError) as exc_info:
            async for _ in client.run_streaming("host1", "fail"):
                pass

        assert exc_info.value.host == "host1"
        assert exc_info.value.exit_status == 1
```

**Test helper classes** (test_ssh_client.py lines 188-225):
```python
class _async_cm:
    """Minimal async context manager wrapping a return value."""
    def __init__(self, value: object) -> None:
        self._value = value
    async def __aenter__(self):
        return self._value
    async def __aexit__(self, *args: object) -> None:
        pass


class _async_cm_raises:
    """Async context manager that raises on __aenter__."""
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
    async def __aenter__(self):
        raise self._exc
    async def __aexit__(self, *args: object) -> None:
        pass
```

Runner test adaptation: mock `SSHClient` (not asyncssh) using `MagicMock(spec=SSHClient)` with `client.run = AsyncMock()`. Simpler than SSH client tests because the runner just calls `self._ssh.run()`.

---

### `tests/provisioning/test_ssh_client.py` MODIFIED (extend with `TestSSHClientRun`)

**Analog:** `TestSSHClientStdoutStreaming` and `TestSSHClientNonZeroExit` in the same file.

New `TestSSHClientRun` class follows the same `@patch` + `_setup_mock_asyncssh` pattern. Key difference: mock uses `conn.run` (returns `SSHCompletedProcess`-like mock) instead of `conn.create_process`. Needs a new helper or adaptation of `_setup_mock_asyncssh` to wire `conn.run = AsyncMock(return_value=mock_result)`.

---

## Shared Patterns

### Imports: `from __future__ import annotations`
**Source:** Every file in `inference_proxy/` (e.g., ssh_client.py line 10, quads.py line 8, node.py line 13)
**Apply to:** All new files

### Pydantic ConfigDict: `frozen=True`
**Source:** `inference_proxy/models/node.py` line 34, `inference_proxy/models/quads.py` line 16, `inference_proxy/models/admin.py` line 26
**Apply to:** `inference_proxy/models/llmfit.py`
```python
model_config = ConfigDict(frozen=True, extra="ignore")
```

### Logging: structlog
**Source:** `inference_proxy/provisioning/ssh_client.py` line 20
**Apply to:** `inference_proxy/llmfit/runner.py`
```python
import structlog

logger = structlog.get_logger()
```

### Error class attributes
**Source:** `inference_proxy/provisioning/ssh_client.py` lines 23-46
**Apply to:** `inference_proxy/llmfit/errors.py`
Store structured context (host, timeout, raw_output) as instance attributes, format a human-readable `super().__init__(msg)`.

### Test markers and mocking
**Source:** `tests/provisioning/test_ssh_client.py` lines 58-75
**Apply to:** All async test files
```python
@pytest.mark.asyncio
@patch("inference_proxy.provisioning.ssh_client.asyncssh")
async def test_something(self, mock_asyncssh: MagicMock) -> None:
```

## No Analog Found

None -- all files have close analogs in the existing codebase.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 5 analogs read (ssh_client.py, quads.py, node.py, admin.py, redfish/errors.py) + 2 test files (test_quads.py, test_ssh_client.py)
**Pattern extraction date:** 2026-07-24
