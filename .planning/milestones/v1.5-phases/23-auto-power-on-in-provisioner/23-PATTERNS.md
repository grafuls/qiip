# Phase 23: Auto-Power-On in Provisioner - Pattern Map

**Mapped:** 2026-07-22
**Files analyzed:** 5 (all modifications, no new files)
**Analogs found:** 5 / 5

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `inference_proxy/provisioning/provisioner.py` | service | request-response | self (existing methods) | exact |
| `inference_proxy/provisioning/state.py` | model | N/A | self (existing enum) | exact |
| `inference_proxy/config/settings.py` | config | N/A | self (`ProvisioningSettings`) | exact |
| `inference_proxy/main.py` | config | N/A | self (provisioner construction block) | exact |
| `tests/provisioning/test_provisioner.py` | test | N/A | self (existing test classes) | exact |

## Pattern Assignments

### `inference_proxy/provisioning/provisioner.py` (service, request-response)

**Analog:** Self -- all patterns already exist in this file.

**Constructor injection pattern** (lines 69-83) -- add `redfish_client` as optional kwarg:
```python
def __init__(
    self,
    ssh_client: SSHClient,
    etcd_client: EtcdClient,
    settings: ProvisioningSettings,
    registry: NodeRegistry | None = None,
    connection_tracker: ConnectionTracker | None = None,
    # NEW: same None-default pattern as registry/connection_tracker
) -> None:
```

**Import to add:**
```python
from inference_proxy.redfish.client import RedfishClient
from inference_proxy.redfish.errors import RedfishError
```

**Best-effort catch-and-continue pattern** (lines 111-114) -- `_update_state()` is the analog:
```python
try:
    await asyncio.to_thread(self._etcd_client.put, key, value)
except Exception:
    logger.warning("state_write_failed", hostname=hostname, step=step)
```

**TCP probe pattern** (lines 136-144) -- `preflight()` Stage 1 is the analog for `_wait_for_ssh()`:
```python
_reader, writer = await asyncio.wait_for(
    asyncio.open_connection(hostname, 22), timeout=10
)
writer.close()
await writer.wait_closed()
```

**Deadline-based retry loop pattern** (lines 282-302) -- `_poll_health()` is the analog:
```python
deadline = asyncio.get_running_loop().time() + self._settings.health_poll_timeout
# ...
while True:
    # ... try operation ...
    if asyncio.get_running_loop().time() >= deadline:
        raise ProvisioningError(...)
    await asyncio.sleep(self._settings.health_poll_interval)
```

**Provision insertion point** (lines 188-189) -- insert `_power_on_if_needed()` call between PENDING and PREFLIGHT:
```python
await self._update_state(hostname, ProvisioningStep.PENDING)
# INSERT HERE: await self._power_on_if_needed(hostname)
await self._update_state(hostname, ProvisioningStep.PREFLIGHT)
```

**Optional-None skip pattern** (lines 328-330) -- `_drain_wait()` is the analog:
```python
if self._tracker is None:
    logger.warning("drain_skip_no_tracker", hostname=hostname)
    return
```

---

### `inference_proxy/provisioning/state.py` (model, enum)

**Analog:** Self -- `ProvisioningStep` enum (lines 19-39).

**Enum member ordering** -- add `POWERING_ON` between PENDING and PREFLIGHT:
```python
class ProvisioningStep(StrEnum):
    PENDING = "pending"
    POWERING_ON = "powering_on"  # NEW
    PREFLIGHT = "preflight"
    # ... rest unchanged ...
```

---

### `inference_proxy/config/settings.py` (config)

**Analog:** Self -- `ProvisioningSettings` class (lines 106-118).

**Settings field pattern** -- existing fields use plain `int` with inline defaults:
```python
class ProvisioningSettings(BaseModel):
    health_poll_timeout: int = 600
    health_poll_interval: int = 10
    vllm_port: int = 8000
    min_disk_gb: int = 20
    drain_timeout: int = 30
    scripts_dir: Path = Path("auto-vllm-container")
    # NEW: boot_wait_timeout: int = 300
    # NEW: boot_wait_interval: int = 10
```

---

### `inference_proxy/main.py` (config, lifespan wiring)

**Analog:** Self -- provisioner construction block (lines 164-171).

**Constructor call pattern** -- add `redfish_client` kwarg:
```python
provisioner = NodeProvisioner(
    ssh_client=ssh_client,
    etcd_client=etcd_client,
    settings=resolved_settings.provisioning,
    registry=registry,
    connection_tracker=connection_tracker,
    # NEW: redfish_client=app.state.redfish_client,
)
```

Note: `app.state.redfish_client` is already set at line 224 (or `None` at line 227), before provisioner construction at line 164. The redfish block (lines 203-229) runs **before** the provisioner block (lines 163-171), so `app.state.redfish_client` is available.

---

### `tests/provisioning/test_provisioner.py` (test)

**Analog:** Self -- existing test structure.

**Test helper pattern** (lines 32-47) -- `_make_provisioner()` factory:
```python
def _make_provisioner(
    *,
    ssh_client: MagicMock | None = None,
    etcd_client: MagicMock | None = None,
    settings: ProvisioningSettings | None = None,
    registry: MagicMock | None = None,
    connection_tracker: MagicMock | None = None,
    # NEW: redfish_client: MagicMock | None = None,
) -> NodeProvisioner:
    return NodeProvisioner(
        ssh_client=ssh_client or MagicMock(),
        etcd_client=etcd_client or MagicMock(),
        settings=settings or ProvisioningSettings(health_poll_timeout=2, health_poll_interval=0),
        registry=registry,
        connection_tracker=connection_tracker,
        # NEW: redfish_client=redfish_client,
    )
```

**Test class pattern** -- each behavior gets its own class (e.g., `TestHealthPoll`, `TestPreflight`):
```python
class TestHealthPoll:
    """D-10, D-09: Health polling via httpx."""

    @pytest.mark.asyncio
    async def test_success_on_200(self, ...) -> None:
        ...
```

**Async mock pattern** -- `patch` + `AsyncMock`:
```python
with patch("inference_proxy.provisioning.provisioner.asyncio.open_connection",
           side_effect=OSError("Connection refused")):
    ...
```

**State capture pattern** (lines 720-741) -- intercept `asyncio.to_thread` to capture state writes:
```python
state_steps: list[str] = []

async def capture_to_thread(fn, *args):
    if fn == etcd.put and len(args) >= 2 and "/provisioning/" in str(args[0]):
        data = json.loads(args[1])
        state_steps.append(data["current_step"])
    return True

with patch("inference_proxy.provisioning.provisioner.asyncio.to_thread",
           side_effect=capture_to_thread):
    await provisioner.teardown("host1")

assert "draining" in state_steps
```

## Shared Patterns

### Structured Logging
**Source:** Throughout `provisioner.py`
**Apply to:** All new methods in provisioner
```python
logger = structlog.get_logger()
logger.info("event_name", hostname=hostname, key=value)
logger.warning("event_name", hostname=hostname, error=str(exc))
```

### Best-Effort with Catch-and-Continue
**Source:** `provisioner.py` lines 111-114 (`_update_state`)
**Apply to:** `_power_on_if_needed()` -- catch `RedfishError`, log warning, continue
```python
try:
    await self._redfish_client.power_action(hostname, "On")
except RedfishError as exc:
    logger.warning("power_on_failed", hostname=hostname, error=str(exc))
```

### Deadline-Based Retry
**Source:** `provisioner.py` lines 285-302 (`_poll_health`), lines 331-338 (`_drain_wait`)
**Apply to:** `_wait_for_ssh()` -- same `loop.time() + timeout` deadline pattern
```python
deadline = asyncio.get_running_loop().time() + self._settings.boot_wait_timeout
while asyncio.get_running_loop().time() < deadline:
    # try TCP probe
    await asyncio.sleep(self._settings.boot_wait_interval)
logger.warning("ssh_wait_timeout", hostname=hostname)
```

## No Analog Found

No files without analogs. Every change modifies existing files, and every pattern needed already exists in the codebase.

## Metadata

**Analog search scope:** `inference_proxy/provisioning/`, `inference_proxy/config/`, `inference_proxy/redfish/`, `inference_proxy/main.py`, `tests/provisioning/`
**Files scanned:** 6
**Pattern extraction date:** 2026-07-22
