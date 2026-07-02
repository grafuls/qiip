# Phase 12: Provisioning Robustness - Pattern Map

**Mapped:** 2026-07-02
**Files analyzed:** 5 (1 new, 4 modified)
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/provisioning/state.py` | model | transform | `inference_proxy/models/node.py` | exact |
| `inference_proxy/provisioning/provisioner.py` | service | request-response | itself (extend) | exact |
| `inference_proxy/models/node.py` | model | n/a | itself (extend) | exact |
| `inference_proxy/resilience/health_checker.py` | service | event-driven | itself (extend) | exact |
| `inference_proxy/config/settings.py` | config | n/a | itself (extend) | exact |

## Pattern Assignments

### `inference_proxy/provisioning/state.py` (NEW -- model, transform)

**Analog:** `inference_proxy/models/node.py`

**Imports pattern** (lines 1-6):
```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
```

**StrEnum pattern** (lines 20-27):
```python
class NodeStatus(StrEnum):
    """Status of a vLLM inference node."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    UNKNOWN = "unknown"
```

**Frozen Pydantic model pattern** (lines 38-63):
```python
class Node(BaseModel):
    """A vLLM inference node registered in etcd.

    Instances are immutable (``frozen=True``) to prevent external
    mutation of registry entries without acquiring the registry lock.
    Use ``model_copy(update={...})`` to create modified copies.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str
    endpoint: str
    status: NodeStatus = NodeStatus.UNKNOWN
    model: str = ""
    last_heartbeat: datetime | None = None
```

Apply: `ProvisioningStep(StrEnum)` follows `NodeStatus` pattern. `ProvisioningState(BaseModel)` follows `Node` pattern with `ConfigDict(frozen=True)`.

---

### `inference_proxy/provisioning/provisioner.py` (MODIFIED -- service, request-response)

**Analog:** itself

**Imports pattern** (lines 1-28):
```python
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import httpx
import structlog

from inference_proxy.config.settings import ProvisioningSettings
from inference_proxy.discovery.etcd_client import EtcdClient
from inference_proxy.discovery.serializer import node_to_etcd
from inference_proxy.models.node import Node, NodeStatus
from inference_proxy.provisioning.ssh_client import (
    RemoteCommandError,
    SSHClient,
    SSHConnectionError,
)

logger = structlog.get_logger()
```

**Exception pattern** (lines 34-36):
```python
class ProvisioningError(Exception):
    """Raised when any stage of provisioning fails."""
```

New `PreflightError` follows this pattern but adds structured fields per D-03:
```python
class PreflightError(Exception):
    def __init__(self, hostname: str, failures: list[str]) -> None:
        self.hostname = hostname
        self.failures = failures
```

**DI constructor pattern** (lines 45-53):
```python
def __init__(
    self,
    ssh_client: SSHClient,
    etcd_client: EtcdClient,
    settings: ProvisioningSettings,
) -> None:
    self._ssh_client = ssh_client
    self._etcd_client = etcd_client
    self._settings = settings
```

**etcd write via asyncio.to_thread pattern** (lines 139-141):
```python
await asyncio.to_thread(self._etcd_client.put, key, value)
logger.info("node_registered", hostname=hostname, model=model, key=key)
```

State writes to `/provisioning/{hostname}` reuse this exact pattern.

**SSH streaming consumption pattern** (lines 73-87, used by _run_setup):
```python
async for stream, line in self._ssh_client.run_streaming(
    hostname, "bash auto-vllm-container/setup.sh"
):
    if stream == "stdout":
        match = STEP_PATTERN.search(line)
        if match:
            step_name, status = match.group(1), match.group(2)
```

State machine updates plug into the existing `STEP_PATTERN` match block -- when a `START` marker arrives, write the corresponding `ProvisioningStep` to etcd.

**Node registration pattern** (lines 129-141):
```python
async def _register_node(self, hostname: str, model: str) -> None:
    node = Node(
        node_id=hostname,
        endpoint=f"{hostname}:{self._settings.vllm_port}",
        status=NodeStatus.HEALTHY,
        model=model,
        last_heartbeat=datetime.now(timezone.utc),
    )
    key, value = node_to_etcd(node, self._etcd_client.prefix)
    await asyncio.to_thread(self._etcd_client.put, key, value)
```

PROVISIONING registration at start of `provision()` follows the same pattern but with `status=NodeStatus.PROVISIONING`.

---

### `inference_proxy/models/node.py` (MODIFIED -- model)

**Analog:** itself

**Enum extension point** (lines 20-27):
```python
class NodeStatus(StrEnum):
    """Status of a vLLM inference node."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    UNKNOWN = "unknown"
```

Add `PROVISIONING = "provisioning"` to this enum. Test at `tests/models/test_node.py` line 19 asserts `len(NodeStatus) == 4` -- update to 5.

---

### `inference_proxy/resilience/health_checker.py` (MODIFIED -- service, event-driven)

**Analog:** itself

**Probe loop with per-node iteration** (lines 101-113):
```python
nodes = registry.get_all()
for node in nodes:
    _probe_node(
        node_id=node.node_id,
        endpoint=node.endpoint,
        current_status=node.status,
        ...
    )
```

Guard insertion point: add `if node.status == NodeStatus.PROVISIONING: continue` before the `_probe_node` call inside this loop.

---

### `inference_proxy/config/settings.py` (MODIFIED -- config)

**Analog:** itself

**Settings sub-model pattern** (lines 106-114):
```python
class ProvisioningSettings(BaseModel):
    """Node provisioning configuration (D-17)."""

    health_poll_timeout: int = 600
    health_poll_interval: int = 10
    vllm_port: int = 8000
```

Add `min_disk_gb: int = 20` per D-02.

---

## Shared Patterns

### Structured Logging
**Source:** All modules use `structlog.get_logger()` at module level
**Apply to:** All new/modified files
```python
import structlog
logger = structlog.get_logger()

# Usage: keyword args, snake_case event names
logger.info("provisioning_start", hostname=hostname)
logger.warning("state_write_failed", hostname=hostname, step=step)
```

### asyncio.to_thread for Sync etcd Calls
**Source:** `inference_proxy/provisioning/provisioner.py` line 140
**Apply to:** All new etcd state writes in provisioner
```python
await asyncio.to_thread(self._etcd_client.put, key, value)
```

### Pydantic JSON Serialization
**Source:** `inference_proxy/discovery/serializer.py` lines 63-65
**Apply to:** ProvisioningState serialization to etcd
```python
data = node.model_dump(exclude={"node_id"}, mode="json")
value_bytes = json.dumps(data).encode("utf-8")
```

### Test Fixture Pattern (provisioner tests)
**Source:** `tests/provisioning/test_provisioner.py` lines 26-36
**Apply to:** New TestPreflight and TestStateTracking test classes
```python
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
```

### Test Fixture Pattern (health checker tests)
**Source:** `tests/resilience/test_health_checker.py` lines 24-31
**Apply to:** New TestProvisioningNodeSkipped test class
```python
def _make_node(
    node_id: str = "node-1",
    endpoint: str = "10.0.1.100:8000",
    status: NodeStatus = NodeStatus.HEALTHY,
) -> Node:
    return Node(node_id=node_id, endpoint=endpoint, status=status)
```

### Async Generator Mock Pattern
**Source:** `tests/provisioning/test_provisioner.py` lines 58-68
**Apply to:** Tests for preflight SSH command mocking
```python
async def mock_streaming(host: str, command: str):
    if "setup.sh" in command:
        for item in [("stdout", "[STEP:nvidia_repo:START]")]:
            yield item
    elif "start-vllm.sh" in command:
        for item in [("stdout", "# Model:  Qwen/Qwen2.5-72B-Instruct")]:
            yield item
```

### Health Checker Stop-After-N Pattern
**Source:** `tests/resilience/test_health_checker.py` lines 54-60
**Apply to:** TestProvisioningNodeSkipped
```python
iteration_count = 0
def stop_after_one_iteration(timeout: float | None = None) -> bool:
    nonlocal iteration_count
    iteration_count += 1
    if iteration_count >= 1:
        stop_event.set()
        return True
    return original_wait(timeout)
```

## No Analog Found

None -- all files have exact analogs in the existing codebase.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 12
**Pattern extraction date:** 2026-07-02
