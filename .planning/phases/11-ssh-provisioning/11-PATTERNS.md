# Phase 11: SSH Provisioning - Pattern Map

**Mapped:** 2026-07-01
**Files analyzed:** 7 new/modified files
**Analogs found:** 5 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/provisioning/__init__.py` | config | -- | `inference_proxy/discovery/__init__.py` | exact |
| `inference_proxy/provisioning/ssh_client.py` | service | streaming | `inference_proxy/discovery/etcd_client.py` | role-match |
| `inference_proxy/provisioning/provisioner.py` | service | request-response | `inference_proxy/resilience/health_checker.py` | partial |
| `inference_proxy/config/settings.py` (modify) | config | -- | self (existing sub-models) | exact |
| `inference_proxy/discovery/etcd_client.py` (modify) | service | CRUD | self (existing methods) | exact |
| `tests/provisioning/test_ssh_client.py` | test | -- | `tests/discovery/test_etcd_client.py` | exact |
| `tests/provisioning/test_provisioner.py` | test | -- | `tests/discovery/test_etcd_client.py` | role-match |

## Pattern Assignments

### `inference_proxy/provisioning/__init__.py` (package marker)

**Analog:** `inference_proxy/discovery/__init__.py`

Empty file. All `__init__.py` files in this codebase are empty.

---

### `inference_proxy/provisioning/ssh_client.py` (service, streaming)

**Analog:** `inference_proxy/discovery/etcd_client.py`

**Module docstring pattern** (lines 1-10):
```python
"""Thin wrapper around etcd3gw providing typed node operations.

This module is the **sole consumer** of ``etcd3gw`` in the codebase,
following the Dependency Inversion Principle (DIP): all other modules
depend on this wrapper rather than importing ``etcd3gw`` directly.

Per D-13: Encapsulates connection configuration and provides typed
methods for node operations.
Per D-14: Created from ``EtcdSettings`` (endpoints, node_prefix).
"""
```
SSHClient docstring should mirror this: state it is the sole consumer of asyncssh, reference relevant D-numbers.

**Imports pattern** (lines 12-19):
```python
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import structlog
from etcd3gw.client import Etcd3Client

from inference_proxy.config.settings import EtcdSettings
```
Convention: `from __future__ import annotations` first, stdlib, third-party, then project imports. Module-level `logger = structlog.get_logger()`.

**Constructor pattern** (lines 36-56):
```python
class EtcdClient:
    def __init__(self, settings: EtcdSettings) -> None:
        # Validate/parse settings
        endpoint = settings.endpoints[0]
        parsed = urlparse(endpoint)
        if not parsed.scheme or not parsed.hostname:
            raise ValueError(...)
        self._client = Etcd3Client(
            host=parsed.hostname,
            port=parsed.port or 2379,
            protocol=parsed.scheme,
            timeout=5,
        )
        self._prefix = settings.node_prefix
```
Key pattern: accept Settings sub-model, store private fields extracted from it, instantiate the wrapped library client. SSHClient should accept `SSHSettings`, store `_username`, `_key_path`, `_connect_timeout` -- do NOT store the settings object itself (extract values in constructor).

**Method delegation pattern** (lines 63-80):
```python
def get_prefix(self) -> list[tuple[bytes, dict[str, Any]]]:
    return self._client.get_prefix(self._prefix)

def watch_prefix(self) -> tuple[Any, Any]:
    return self._client.watch_prefix(self._prefix)
```
Thin delegation: each method maps 1:1 to the underlying library call. SSHClient.run_streaming() wraps asyncssh.connect() + create_process().

---

### `inference_proxy/provisioning/provisioner.py` (service, request-response)

**Analog:** `inference_proxy/resilience/health_checker.py` (partial -- health poll logic)

**Health probe pattern** (lines 141-172):
```python
try:
    url = f"http://{endpoint}/health"
    response = client.get(url)
    if response.status_code == 200:
        _handle_probe_success(...)
    else:
        _handle_probe_failure(...)
except Exception:
    _handle_probe_failure(...)
    logger.debug(
        "health probe failed with exception",
        node_id=node_id,
        exc_info=True,
    )
```
Provisioner's health poll adapts this to async httpx with a deadline loop. Key: catch broad Exception for connection errors, log at debug not warning (Pitfall 4: early polls will fail).

**Structlog usage pattern** (throughout health_checker.py):
```python
logger.info("node recovered to healthy", node_id=node_id, previous_status=str(current_status))
logger.debug("health probe succeeded", node_id=node_id)
logger.debug("health probe failed", node_id=node_id, consecutive_failures=count, reason=reason)
logger.info("node marked unhealthy", node_id=node_id, consecutive_failures=count, threshold=failure_threshold)
```
Convention: `info` for state transitions, `debug` for routine events. Use keyword args for structured context.

**Also references:** `inference_proxy/discovery/serializer.py` for registration.

**Node construction + serialization pattern** (serializer.py lines 50-66):
```python
def node_to_etcd(node: Node, prefix: str) -> tuple[str, bytes]:
    key = prefix + node.node_id
    data = node.model_dump(exclude={"node_id"}, mode="json")
    value_bytes = json.dumps(data).encode("utf-8")
    return key, value_bytes
```
Provisioner must construct a `Node` with all required fields, then call `node_to_etcd()` to get key/value, then `etcd_client.put(key, value)`.

**Node model fields** (node.py lines 57-63):
```python
node_id: str
endpoint: str
status: NodeStatus = NodeStatus.UNKNOWN
model: str = ""
last_heartbeat: datetime | None = None
capabilities: NodeCapabilities = Field(default_factory=NodeCapabilities)
active_connections: int = 0
```

---

### `inference_proxy/config/settings.py` (modify -- add SSHSettings, ProvisioningSettings)

**Analog:** Self -- existing sub-model pattern.

**Sub-model definition pattern** (lines 12-16, 20-33, etc.):
```python
class GatewaySettings(BaseModel):
    """Gateway server configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    graceful_shutdown_timeout: int = 30


class EtcdSettings(BaseModel):
    """etcd service discovery configuration."""
    endpoints: list[str] = ["http://localhost:2379"]
    node_prefix: str = "/nodes/"

    @field_validator("endpoints")
    @classmethod
    def endpoints_must_be_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one etcd endpoint must be configured")
        return v
```
Convention: `BaseModel` (not `BaseSettings`), docstring, typed fields with defaults, optional `field_validator`.

**Root Settings registration pattern** (lines 93-116):
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INFERENCE_PROXY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    gateway: GatewaySettings = GatewaySettings()
    etcd: EtcdSettings = EtcdSettings()
    routing: RoutingSettings = RoutingSettings()
    proxy: ProxySettings = ProxySettings()
    resilience: ResilienceSettings = ResilienceSettings()
    logging: LoggingSettings = LoggingSettings()
    dashboard: DashboardSettings = DashboardSettings()
```
Add `ssh: SSHSettings = SSHSettings()` and `provisioning: ProvisioningSettings = ProvisioningSettings()` following this pattern.

---

### `inference_proxy/discovery/etcd_client.py` (modify -- add put method)

**Analog:** Self -- existing delegation methods.

**Method to add follows this pattern** (lines 63-70):
```python
def get_prefix(self) -> list[tuple[bytes, dict[str, Any]]]:
    """Fetch all key-value pairs under the configured node prefix."""
    return self._client.get_prefix(self._prefix)
```
New `put()` method: same thin delegation to `self._client.put(key, value)`.

---

### `tests/provisioning/test_ssh_client.py` (test)

**Analog:** `tests/discovery/test_etcd_client.py`

**Test file structure** (lines 1-36):
```python
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
```
Convention: one class per behavior group, descriptive class docstring, `@patch` the third-party library at its import location, construct settings explicitly, assert delegation.

**Mock pattern for delegation tests** (lines 42-57):
```python
@patch("inference_proxy.discovery.etcd_client.Etcd3Client")
def test_delegates_get_prefix(self, mock_etcd3_cls: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_instance.get_prefix.return_value = [...]
    mock_etcd3_cls.return_value = mock_instance

    settings = EtcdSettings(...)
    client = EtcdClient(settings)
    result = client.get_prefix()

    mock_instance.get_prefix.assert_called_once_with("/test-nodes/")
```
SSHClient tests should `@patch("inference_proxy.provisioning.ssh_client.asyncssh")` and verify `connect()` is called with correct params.

---

### `tests/provisioning/test_provisioner.py` (test)

**Analog:** `tests/discovery/test_etcd_client.py` (mock pattern), `tests/config/test_settings.py` (settings test pattern)

**Settings default test pattern** (test_settings.py lines 18-22):
```python
class TestDefaultGatewaySettings:
    def test_default_gateway_settings(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.gateway.host == "0.0.0.0"
        assert settings.gateway.port == 8080
```

**Env var override test pattern** (test_settings.py lines 41-44):
```python
class TestEnvVarOverrideGatewayPort:
    def test_env_var_override_gateway_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_GATEWAY__PORT", "9090")
        settings = Settings(_env_file=None)
        assert settings.gateway.port == 9090
```
Provisioner tests mock SSHClient (dependency injection), httpx (for health poll), and EtcdClient (for registration). No `@patch` needed if provisioner accepts dependencies via constructor.

---

## Shared Patterns

### Structlog Logger
**Source:** All modules
**Apply to:** `ssh_client.py`, `provisioner.py`
```python
import structlog

logger = structlog.get_logger()
```
Module-level logger. Use `logger.info()` for state transitions, `logger.debug()` for routine operations, `logger.warning()` for stderr output (D-07).

### `from __future__ import annotations`
**Source:** All modules
**Apply to:** All new files
First import in every module.

### Frozen Pydantic Models
**Source:** `inference_proxy/models/node.py`
**Apply to:** Node construction in provisioner
```python
model_config = ConfigDict(frozen=True)
```
Node is frozen -- provisioner constructs new instances, never mutates.

### DIP Wrapper Pattern
**Source:** `inference_proxy/discovery/etcd_client.py`
**Apply to:** `inference_proxy/provisioning/ssh_client.py`
Only `ssh_client.py` imports `asyncssh`. Only `etcd_client.py` imports `etcd3gw`. All other modules depend on the wrapper.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `inference_proxy/provisioning/provisioner.py` | service | orchestration | No async orchestration service exists yet. Closest partial match is `health_checker.py` (sync, thread-based). Use RESEARCH.md patterns for the async orchestration flow (SSH -> health poll -> register). |

The provisioner is unique in this codebase: it chains multiple async operations (SSH streaming, health polling, etcd registration) into a single workflow. The individual pieces (health check, etcd write, structlog) all have analogs, but the orchestration flow is new.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 8 analog files read
**Pattern extraction date:** 2026-07-01
