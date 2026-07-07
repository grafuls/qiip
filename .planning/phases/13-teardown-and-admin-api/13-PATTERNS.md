# Phase 13: Teardown and Admin API - Pattern Map

**Mapped:** 2026-07-07
**Files analyzed:** 10 (all modifications, no new files)
**Analogs found:** 10 / 10

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `inference_proxy/provisioning/provisioner.py` | service | request-response | self (provision() method) | exact |
| `inference_proxy/provisioning/state.py` | model | N/A | self (ProvisioningStep enum) | exact |
| `inference_proxy/api/admin.py` | controller | request-response | self (list_nodes endpoint) | exact |
| `inference_proxy/models/admin.py` | model | N/A | self (AdminNodeResponse) | exact |
| `inference_proxy/config/settings.py` | config | N/A | self (ProvisioningSettings) | exact |
| `inference_proxy/config/dependencies.py` | provider | N/A | self (get_registry pattern) | exact |
| `inference_proxy/discovery/etcd_client.py` | service | CRUD | self (put() method) | exact |
| `inference_proxy/main.py` | config | N/A | self (lifespan wiring) | exact |
| `tests/provisioning/test_provisioner.py` | test | N/A | self (TestProvisionSequence) | exact |
| `tests/api/test_admin.py` | test | N/A | self (TestAdminNodesPopulated) | exact |

All files are self-analogs (extending existing code). Every pattern comes from the file being modified.

## Pattern Assignments

### `inference_proxy/provisioning/provisioner.py` (service, request-response)

**Analog:** self -- add `teardown()` mirroring `provision()` at line 158.

**Constructor pattern** (lines 60-69) -- extend with optional `registry` and `connection_tracker`:
```python
class NodeProvisioner:
    def __init__(
        self,
        ssh_client: SSHClient,
        etcd_client: EtcdClient,
        settings: ProvisioningSettings,
    ) -> None:
        self._ssh_client = ssh_client
        self._etcd_client = etcd_client
        self._settings = settings
        self._provision_started_at: datetime | None = None
```
New params must be optional (default `None`) per Research Pitfall 6 to avoid breaking existing tests.

**State update pattern** (lines 71-94) -- reuse `_update_state()` for teardown steps:
```python
async def _update_state(
    self,
    hostname: str,
    step: ProvisioningStep,
    *,
    failed_step: str | None = None,
    error: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    state = ProvisioningState(
        hostname=hostname,
        current_step=step,
        started_at=self._provision_started_at or now,
        updated_at=now,
        failed_step=failed_step,
        error=error,
    )
    key = f"/provisioning/{hostname}"
    value = json.dumps(state.model_dump(mode="json")).encode("utf-8")
    try:
        await asyncio.to_thread(self._etcd_client.put, key, value)
    except Exception:
        logger.warning("state_write_failed", hostname=hostname, step=step)
```

**SSH command pattern** (lines 96-102) -- reuse `_ssh_run_command()` for podman stop/rm:
```python
async def _ssh_run_command(self, hostname: str, command: str) -> str:
    lines: list[str] = []
    async for stream, line in self._ssh_client.run_streaming(hostname, command):
        if stream == "stdout":
            lines.append(line)
    return "\n".join(lines)
```

**Health poll loop pattern** (lines 255-275) -- copy for drain wait loop:
```python
async def _poll_health(self, hostname: str) -> None:
    url = f"http://{hostname}:{self._settings.vllm_port}/health"
    deadline = asyncio.get_running_loop().time() + self._settings.health_poll_timeout

    async with httpx.AsyncClient() as client:
        while True:
            # ... check condition ...
            if asyncio.get_running_loop().time() >= deadline:
                raise ProvisioningError(...)
            await asyncio.sleep(self._settings.health_poll_interval)
```
Drain wait uses the same deadline pattern but checks `self._tracker.get(hostname) == 0` instead of HTTP health.

**Error handling pattern** (lines 204-209) -- wrap teardown body in same try/except:
```python
except (RemoteCommandError, SSHConnectionError, ProvisioningError) as exc:
    await self._update_state(
        hostname, ProvisioningStep.FAILED,
        failed_step=type(exc).__name__, error=str(exc),
    )
    raise ProvisioningError(str(exc)) from exc
```

**etcd registration pattern** (lines 277-289) -- mirror for etcd deletion in teardown:
```python
async def _register_node(self, hostname: str, model: str) -> None:
    node = Node(...)
    key, value = node_to_etcd(node, self._etcd_client.prefix)
    await asyncio.to_thread(self._etcd_client.put, key, value)
```
Teardown calls `await asyncio.to_thread(self._etcd_client.delete, ...)` instead.

---

### `inference_proxy/provisioning/state.py` (model, enum extension)

**Analog:** self -- extend `ProvisioningStep` enum at lines 19-34.

**Enum pattern** (lines 19-34):
```python
class ProvisioningStep(StrEnum):
    """Steps in the node provisioning sequence (D-06)."""

    PENDING = "pending"
    PREFLIGHT = "preflight"
    # ... existing members ...
    COMPLETE = "complete"
    FAILED = "failed"
```
Add four new members before COMPLETE/FAILED: `DRAINING`, `STOPPING_CONTAINER`, `DEREGISTERING`, `TEARDOWN_COMPLETE`.

---

### `inference_proxy/api/admin.py` (controller, request-response)

**Analog:** self -- add endpoints mirroring `list_nodes` at line 28.

**Endpoint pattern** (lines 28-51):
```python
@admin_router.get("/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
    node_selector: NodeSelector = Depends(get_node_selector),
    cb_registry: CircuitBreakerRegistry = Depends(get_circuit_breaker_registry),
) -> list[AdminNodeResponse]:
    nodes = registry.get_all()
    tracker = node_selector.tracker
    return [
        AdminNodeResponse(...)
        for n in nodes
    ]
```
New endpoints follow the same `Depends()` injection, return Pydantic models pattern. POST/DELETE return 202 with `status_code=202` on the decorator.

**Import pattern** (lines 1-24):
```python
from fastapi import APIRouter, Depends
from inference_proxy.config.dependencies import (
    get_circuit_breaker_registry,
    get_node_selector,
    get_registry,
    get_request_metrics,
)
```
Add `get_provisioner` to this import block.

---

### `inference_proxy/models/admin.py` (model, Pydantic)

**Analog:** self -- add models mirroring `AdminNodeResponse` at line 12.

**Frozen model pattern** (lines 12-28):
```python
class AdminNodeResponse(BaseModel):
    """Docstring."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    endpoint: str
    model: str
    status: str
    active_connections: int
    circuit_breaker_state: str
```
New models (`SetupRequest`, `SetupResponse`, `TeardownResponse`, `TaskStatusResponse`) follow identical `ConfigDict(frozen=True)` pattern.

---

### `inference_proxy/config/settings.py` (config, field addition)

**Analog:** self -- extend `ProvisioningSettings` at line 106.

**Settings field pattern** (lines 106-115):
```python
class ProvisioningSettings(BaseModel):
    """Node provisioning configuration (D-17)."""

    health_poll_timeout: int = 600
    health_poll_interval: int = 10
    vllm_port: int = 8000
    min_disk_gb: int = 20
```
Add `drain_timeout: int = 30` following the same typed-field-with-default style.

---

### `inference_proxy/config/dependencies.py` (provider, DI)

**Analog:** self -- add `get_provisioner` mirroring `get_registry` at line 34.

**DI provider pattern** (lines 34-41):
```python
def get_registry(request: Request) -> NodeRegistry:
    """Return the node registry from the current application state."""
    return request.app.state.registry  # type: ignore[no-any-return]
```
`get_provisioner` follows identical structure: `return request.app.state.provisioner`.

---

### `inference_proxy/discovery/etcd_client.py` (service, CRUD)

**Analog:** self -- add `delete()` mirroring `put()` at line 72.

**Method pattern** (lines 72-82):
```python
def put(self, key: str, value: str | bytes) -> bool:
    """Put a key-value pair into etcd."""
    return self._client.put(key, value)  # type: ignore[no-any-return]
```
`delete()` is identical shape: `return self._client.delete(key)`.

**get_prefix pattern** (lines 63-70) -- modify to accept optional prefix parameter:
```python
def get_prefix(self) -> list[tuple[bytes, dict[str, Any]]]:
    """Fetch all key-value pairs under the configured node prefix."""
    return self._client.get_prefix(self._prefix)  # type: ignore[no-any-return]
```
Add `prefix: str | None = None` parameter, use `prefix or self._prefix`.

---

### `inference_proxy/main.py` (config, lifespan wiring)

**Analog:** self -- extend lifespan at line 96.

**Service creation pattern** (lines 148-151) -- how services are wired:
```python
connection_tracker = ConnectionTracker()
node_selector = NodeSelector(registry, connection_tracker)
app.state.node_selector = node_selector
```
Provisioner follows same pattern: create instance, assign to `app.state.provisioner`.

**Import pattern** (lines 28-45) -- add provisioner imports to existing block.

---

### `tests/provisioning/test_provisioner.py` (test, unit)

**Analog:** self -- add teardown tests mirroring `TestProvisionSequence` at line 50.

**Factory function pattern** (lines 30-41):
```python
def _make_provisioner(
    *,
    ssh_client: MagicMock | None = None,
    etcd_client: MagicMock | None = None,
    settings: ProvisioningSettings | None = None,
) -> NodeProvisioner:
    return NodeProvisioner(
        ssh_client=ssh_client or MagicMock(),
        etcd_client=etcd_client or MagicMock(),
        settings=settings or ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0),
    )
```
Extend with optional `registry` and `connection_tracker` params.

**Mock SSH streaming pattern** (lines 63-72):
```python
async def mock_streaming(host: str, command: str):
    if "setup.sh" in command:
        call_order.append("setup")
        for item in [("stdout", "[STEP:nvidia_repo:START]")]:
            yield item
```

**asyncio.to_thread mock pattern** (lines 86-88):
```python
with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
    mock_to_thread.return_value = True
    await provisioner.provision("host1")
```

---

### `tests/api/test_admin.py` (test, integration)

**Analog:** self -- add setup/teardown endpoint tests mirroring `TestAdminNodesPopulated` at line 40.

**Test fixture pattern** (uses `client` and `test_registry` from conftest.py):
```python
class TestAdminNodesPopulated:
    def test_returns_200_with_two_nodes(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        test_registry.add(_make_node(...))
        response = client.get("/admin/nodes")
        assert response.status_code == 200
```

**conftest.py app fixture pattern** (lines 92-119 of conftest.py) -- extend with provisioner mock:
```python
@pytest.fixture
def app(
    test_settings: Settings,
    test_registry: NodeRegistry,
    ...
) -> Generator[FastAPI, None, None]:
    application = create_app(settings=test_settings)
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.state.registry = test_registry
    # Add: application.state.provisioner = mock_provisioner
    # Add: application.dependency_overrides[get_provisioner] = lambda: mock_provisioner
    yield application
    application.dependency_overrides.clear()
```

---

## Shared Patterns

### asyncio.to_thread for etcd calls
**Source:** `inference_proxy/provisioning/provisioner.py` line 92
**Apply to:** All new etcd interactions (delete, get_prefix with custom prefix)
```python
await asyncio.to_thread(self._etcd_client.put, key, value)
```

### structlog logger
**Source:** `inference_proxy/provisioning/provisioner.py` line 30
**Apply to:** All modified files that add logging
```python
import structlog
logger = structlog.get_logger()
```

### Frozen Pydantic models
**Source:** `inference_proxy/models/admin.py` line 19
**Apply to:** All new Pydantic models
```python
model_config = ConfigDict(frozen=True)
```

### DI via Depends + app.state
**Source:** `inference_proxy/config/dependencies.py` lines 34-41
**Apply to:** New `get_provisioner` provider and admin route handlers
```python
def get_registry(request: Request) -> NodeRegistry:
    return request.app.state.registry  # type: ignore[no-any-return]
```

### Test mock pattern with dependency_overrides
**Source:** `tests/conftest.py` lines 102-108
**Apply to:** Test fixtures needing provisioner injection
```python
application.dependency_overrides[get_some_dep] = lambda: mock_instance
application.state.some_service = mock_instance
```

## No Analog Found

No files without analogs. Every file is a modification of an existing file with established patterns to follow.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 10
**Pattern extraction date:** 2026-07-07
