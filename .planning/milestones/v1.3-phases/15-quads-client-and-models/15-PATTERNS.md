# Phase 15: QUADS Client and Models - Pattern Map

**Mapped:** 2026-07-16
**Files analyzed:** 7 new + 2 modified = 9 total
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/quads/__init__.py` | config | -- | `inference_proxy/provisioning/__init__.py` | exact |
| `inference_proxy/quads/client.py` | service | request-response | `inference_proxy/proxy/client.py` | role-match |
| `inference_proxy/models/quads.py` | model | -- | `inference_proxy/models/node.py` | exact |
| `inference_proxy/config/settings.py` (MODIFY) | config | -- | self (add QUADSSettings like SSHSettings) | exact |
| `inference_proxy/config/dependencies.py` (MODIFY) | config | -- | self (add get_quads_client like get_provisioner) | exact |
| `inference_proxy/main.py` (MODIFY) | config | -- | self (lifespan block for provisioner) | exact |
| `tests/quads/__init__.py` | test | -- | `tests/provisioning/__init__.py` | exact |
| `tests/quads/test_client.py` | test | request-response | `tests/proxy/test_client.py` | exact |
| `tests/models/test_quads.py` | test | -- | `tests/models/test_node.py` | exact |

## Pattern Assignments

### `inference_proxy/quads/client.py` (service, request-response)

**Analog:** `inference_proxy/proxy/client.py`

**Imports pattern** (lines 1-18):
```python
from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()
```

**Constructor injection pattern** (lines 34-35):
```python
class ProxyClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
```

QUADSClient follows this same pattern but takes `base_url: str` as a second arg.

**Error handling pattern** -- QUADSClient introduces `QUADSConnectionError` (new typed exception per D-09). No analog for this exists in ProxyClient (which lets httpx exceptions propagate). Pattern from RESEARCH.md:
```python
class QUADSConnectionError(Exception):
    """Raised when the QUADS API is unreachable or returns an error."""

# In methods:
try:
    resp = await self._client.get(url)
    resp.raise_for_status()
except httpx.HTTPError as exc:
    raise QUADSConnectionError(str(exc)) from exc
```

Compare with `inference_proxy/provisioning/ssh_client.py` lines 26-27 for typed exception precedent:
```python
class SSHConnectionError(Exception): ...
class RemoteCommandError(Exception): ...
```

---

### `inference_proxy/models/quads.py` (model)

**Analog:** `inference_proxy/models/node.py`

**Imports pattern** (lines 1-8):
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
```

**Frozen model pattern** (lines 30-33, 39-56):
```python
class NodeCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_tokens: int = 4096
    gpu_memory: str = ""
```

QUADSHost follows identical structure: `ConfigDict(frozen=True)`, minimal fields per D-04.

---

### `inference_proxy/config/settings.py` (MODIFY -- add QUADSSettings)

**Analog:** Self -- follows `SSHSettings` / `ProvisioningSettings` pattern.

**Sub-model pattern** (lines 95-103):
```python
class SSHSettings(BaseModel):
    """SSH connection configuration (D-16)."""

    key_path: Path = Path("~/.ssh/id_rsa").expanduser()
    username: str = "root"
    connect_timeout: int = 10
```

**Root registration pattern** (lines 136-144):
```python
class Settings(BaseSettings):
    # ...
    ssh: SSHSettings = SSHSettings()
    provisioning: ProvisioningSettings = ProvisioningSettings()
```

Add `quads: QUADSSettings = QUADSSettings()` at the end of the root Settings fields.

---

### `inference_proxy/config/dependencies.py` (MODIFY -- add get_quads_client)

**Analog:** Self -- follows `get_provisioner()` pattern.

**DI provider pattern** (lines 86-88):
```python
def get_provisioner(request: Request) -> NodeProvisioner:
    """Return the node provisioner from the current application state."""
    return request.app.state.provisioner  # type: ignore[no-any-return]
```

Add `get_quads_client()` returning `QUADSClient | None` (None when QUADS not configured per D-10).

---

### `inference_proxy/main.py` (MODIFY -- lifespan QUADS client setup)

**Analog:** Self -- follows provisioner + httpx client creation block.

**httpx client creation pattern** (lines 168-182):
```python
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=resolved_settings.proxy.connect_timeout,
        read=resolved_settings.proxy.read_timeout,
        write=resolved_settings.proxy.write_timeout,
        pool=resolved_settings.proxy.pool_timeout,
    ),
    limits=httpx.Limits(
        max_connections=resolved_settings.proxy.max_connections,
        max_keepalive_connections=resolved_settings.proxy.max_keepalive_connections,
        keepalive_expiry=resolved_settings.proxy.keepalive_expiry,
    ),
)
proxy_client = ProxyClient(http_client)
app.state.proxy_client = proxy_client
```

**Shutdown cleanup pattern** (line 195):
```python
await http_client.aclose()
```

QUADS client follows same structure but simpler timeout (single `httpx.Timeout(resolved_settings.quads.timeout)`), gated by `if resolved_settings.quads.base_url is not None`.

---

### `tests/quads/test_client.py` (test, request-response)

**Analog:** `tests/proxy/test_client.py`

**Test structure pattern** (full file):
```python
from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from inference_proxy.proxy.client import ProxyClient


class TestProxyClientForward:
    """forward() delegates requests to the underlying httpx.AsyncClient."""

    async def test_forward_sends_json_body(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url="http://node1:8000/v1/chat/completions",
            json={"id": "cmpl-1", "choices": []},
        )
        async with httpx.AsyncClient() as http_client:
            proxy = ProxyClient(http_client)
            await proxy.forward(...)

        request = httpx_mock.get_request()
        assert request is not None
```

Key conventions: class-per-behavior grouping, `async def test_*`, `HTTPXMock` fixture via pytest-httpx, `async with httpx.AsyncClient()` for client lifecycle in tests.

**Error test pattern** (lines 60-73):
```python
    async def test_forward_propagates_timeout(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_exception(
            httpx.ReadTimeout("read timed out"),
            url="http://node1:8000/v1/chat/completions",
        )
        async with httpx.AsyncClient() as http_client:
            proxy = ProxyClient(http_client)
            with pytest.raises(httpx.TimeoutException):
                await proxy.forward(...)
```

Use `httpx_mock.add_exception()` for connection error tests (QUADSConnectionError wrapping).

---

### `tests/models/test_quads.py` (test)

**Analog:** `tests/models/test_node.py`

**Model test pattern** (lines 1-40):
```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from inference_proxy.models.node import Node, NodeCapabilities, NodeStatus


class TestNodeMinimalCreation:
    def test_node_minimal_creation(self) -> None:
        node = Node(node_id="node-1", endpoint="http://10.0.1.100:8000")
        assert node.node_id == "node-1"
        assert node.status == NodeStatus.UNKNOWN
```

Key conventions: class-per-behavior, sync test functions for model tests (no async needed), assert each field default.

---

### `tests/config/test_settings.py` (MODIFY -- extend with QUADSSettings tests)

**Analog:** Self -- follows existing settings test pattern.

**Defaults test pattern** (lines 99-114):
```python
class TestDefaultSSHSettings:
    """D-01, D-02, D-04: SSHSettings defaults."""

    def test_default_key_path(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.ssh.key_path == Path("~/.ssh/id_rsa").expanduser()

    def test_default_username(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.ssh.username == "root"
```

**Env var override test pattern** (lines 133-137):
```python
class TestEnvVarOverrideSSHUsername:
    def test_env_var_override_ssh_username(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_SSH__USERNAME", "deploy")
        settings = Settings(_env_file=None)
        assert settings.ssh.username == "deploy"
```

**BaseModel assertion pattern** (lines 149-153):
```python
class TestSSHAndProvisioningAreNotBaseSettings:
    def test_ssh_settings_is_base_model_not_base_settings(self) -> None:
        assert not issubclass(SSHSettings, BaseSettings)
        assert issubclass(SSHSettings, BaseModel)
```

Use `Settings(_env_file=None)` to avoid loading `.env` in tests. Use `monkeypatch.setenv()` for env overrides.

---

## Shared Patterns

### Structured Logging
**Source:** All service files (e.g., `inference_proxy/proxy/client.py` line 19)
**Apply to:** `quads/client.py`
```python
import structlog
logger = structlog.get_logger()
```

### Constructor Injection
**Source:** `inference_proxy/proxy/client.py` lines 34-35
**Apply to:** `quads/client.py`
```python
def __init__(self, client: httpx.AsyncClient) -> None:
    self._client = client
```

### Frozen Pydantic Models
**Source:** `inference_proxy/models/node.py` lines 30-33
**Apply to:** `models/quads.py`
```python
class SomeModel(BaseModel):
    model_config = ConfigDict(frozen=True)
```

### Empty __init__.py
**Source:** `inference_proxy/provisioning/__init__.py`, `inference_proxy/models/__init__.py`
**Apply to:** `inference_proxy/quads/__init__.py`, `tests/quads/__init__.py`

Empty files -- no barrel exports in this codebase.

### Typed Custom Exceptions
**Source:** `inference_proxy/provisioning/ssh_client.py` lines 26-27
**Apply to:** `quads/client.py`
```python
class SSHConnectionError(Exception): ...
class RemoteCommandError(Exception): ...
```

### pytest-httpx Mocking
**Source:** `tests/proxy/test_client.py` lines 19-38
**Apply to:** `tests/quads/test_client.py`
```python
async def test_something(self, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="...", json={...})
    async with httpx.AsyncClient() as http_client:
        # construct service with injected client
        # call method
    request = httpx_mock.get_request()
    assert request is not None
```

## No Analog Found

None -- all files have strong analogs in the existing codebase.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 9 analog files read
**Pattern extraction date:** 2026-07-16
