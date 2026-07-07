# Phase 13: Teardown and Admin API - Research

**Researched:** 2026-07-07
**Domain:** FastAPI REST endpoints, async lifecycle management, SSH remote control, etcd state management
**Confidence:** HIGH

## Summary

Phase 13 extends the existing provisioning system with teardown capability and exposes setup/teardown via admin REST endpoints. All technology decisions are locked -- no new dependencies needed. The work is pure extension of existing patterns: add methods to `NodeProvisioner`, extend the `ProvisioningStep` enum, add endpoints to `admin_router`, and wire up DI.

The primary complexity is the drain-wait-stop sequence in `teardown()`, which requires `NodeRegistry` and `ConnectionTracker` access that `NodeProvisioner` currently lacks. The `EtcdClient` wrapper also needs a `delete()` method -- the underlying `etcd3gw.Etcd3Client` has one, but the project's wrapper does not expose it.

**Primary recommendation:** Extend `NodeProvisioner` constructor to accept `NodeRegistry` and `ConnectionTracker` for teardown drain-wait behavior. Add `EtcdClient.delete()`. All other work follows established codebase patterns exactly.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Teardown stops the remote container via SSH: `podman stop vllm-{model} && podman rm vllm-{model}`. Container name derived from `Node.model` field, matching Phase 10 D-03 naming convention.
- **D-02:** Leave container images on the remote host after teardown.
- **D-03:** Force teardown uses `podman rm --force vllm-{model}` -- single command, kills and removes immediately.
- **D-04:** Add `teardown()` method to `NodeProvisioner`. Same class owns both setup and teardown lifecycle.
- **D-05:** Reuse etcd `ProvisioningState` under `/provisioning/{hostname}` for task tracking. Task ID = hostname. Extend `ProvisioningStep` enum with teardown steps (DRAINING, STOPPING_CONTAINER, DEREGISTERING, TEARDOWN_COMPLETE). No separate task tracking layer.
- **D-06:** POST /admin/nodes/setup returns 202 with `{"task_id": hostname}`. GET /admin/provisioning/tasks reads all `/provisioning/*` keys from etcd.
- **D-07:** Completed/failed task state stays in etcd until the same host is provisioned or torn down again. Next operation overwrites. No TTL, no manual cleanup needed.
- **D-08:** Graceful teardown sets node to DRAINING, then waits up to 30 seconds (configurable via settings) for active connections to reach 0.
- **D-09:** When drain timeout expires and connections remain, proceed to force-stop. In-flight requests get connection errors. Clients can retry on another node.
- **D-10:** `drain_timeout` added to `ProvisioningSettings` with default 30 seconds.
- **D-11:** Teardown deletes the node key from etcd (`/nodes/{hostname}`) -- watcher propagates removal to NodeRegistry.
- **D-12:** Teardown overwrites `/provisioning/{hostname}` with TEARDOWN_COMPLETE terminal state.

### Claude's Discretion
- Admin API request/response Pydantic models (naming, fields beyond what requirements specify)
- Error response format for setup/teardown failures (follow existing OpenAI-compatible error pattern)
- Background task execution mechanism (asyncio.create_task or similar -- no Celery per CLAUDE.md)

### Deferred Ideas (OUT OF SCOPE)
None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEAR-01 | Operator can teardown a node: drain connections, SSH stop container, deregister from etcd | D-01, D-04, D-08, D-09, D-11; NodeProvisioner.teardown() method with drain-wait loop, SSH podman stop, etcd delete |
| TEAR-02 | Force teardown option skips connection drain and immediately stops/deregisters | D-03; `force` parameter on teardown() skips drain, uses `podman rm --force` |
| API-01 | POST /admin/nodes/setup accepts hostname, returns 202 with task ID | D-06; admin_router endpoint, asyncio.create_task for background provisioning |
| API-02 | GET /admin/provisioning/tasks returns status of all setup/teardown operations | D-05, D-06; reads all `/provisioning/*` keys from etcd via get_prefix-style call |
| API-03 | DELETE /admin/nodes/{id} triggers graceful or forced teardown | D-01, D-03, D-08; query param `?force=true` for force mode |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Teardown orchestration | API / Backend | -- | NodeProvisioner owns lifecycle, runs in gateway process |
| Drain wait loop | API / Backend | -- | Checks ConnectionTracker (in-memory), asyncio sleep loop |
| Container stop (SSH) | API / Backend | Remote Host | Gateway sends SSH commands to remote host |
| etcd node deregistration | API / Backend | Database / Storage | Delete key from etcd, watcher propagates |
| Admin REST endpoints | API / Backend | -- | FastAPI routes under /admin |
| Task status tracking | Database / Storage | API / Backend | ProvisioningState stored in etcd, served via API |
| Background task execution | API / Backend | -- | asyncio.create_task, no external task queue |

## Standard Stack

No new packages. Phase uses the existing installed stack exclusively. [VERIFIED: pyproject.toml inspection]

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.135 | Admin API endpoints | Already the framework |
| Pydantic | >=2.10 | Request/response models | Already used for all models |
| asyncssh | >=2.20 | SSH commands (via SSHClient wrapper) | Already installed |
| etcd3gw | >=2.5.0 | State tracking (via EtcdClient wrapper) | Already installed |
| structlog | >=26.1.0 | Logging | Already used everywhere |

## Architecture Patterns

### Teardown Sequence Diagram

```
DELETE /admin/nodes/{id}
  |
  v
admin_router handler
  |
  +--> Validate node exists in registry
  |
  +--> asyncio.create_task(provisioner.teardown(hostname, force=...))
  |
  +--> Return 202 {"task_id": hostname}

Background: provisioner.teardown()
  |
  +--> _update_state(DRAINING)           [etcd /provisioning/{hostname}]
  |
  +--> if not force:
  |      registry.drain(hostname)         [mark DRAINING in registry]
  |      wait loop: check tracker.get(hostname) == 0
  |      timeout after drain_timeout -> proceed anyway
  |
  +--> _update_state(STOPPING_CONTAINER)
  |
  +--> SSH: podman stop + rm (graceful)   [or podman rm --force (force)]
  |
  +--> _update_state(DEREGISTERING)
  |
  +--> etcd_client.delete(/nodes/{hostname})  [watcher sees DELETE event]
  |
  +--> _update_state(TEARDOWN_COMPLETE)   [terminal state in /provisioning/]
```

### Recommended Project Structure Changes

```
inference_proxy/
├── provisioning/
│   ├── provisioner.py       # ADD teardown() method
│   └── state.py             # EXTEND ProvisioningStep enum
├── api/
│   └── admin.py             # ADD setup/teardown/tasks endpoints
├── models/
│   └── admin.py             # ADD setup/teardown request/response models
├── config/
│   ├── settings.py          # ADD drain_timeout to ProvisioningSettings
│   └── dependencies.py      # ADD get_provisioner()
├── discovery/
│   └── etcd_client.py       # ADD delete() method
└── main.py                  # CREATE provisioner in lifespan, store in app.state
```

### Pattern 1: Background Task with asyncio.create_task

**What:** Fire-and-forget background work from a request handler. [VERIFIED: codebase pattern in existing provisioning design]
**When to use:** POST /admin/nodes/setup and DELETE /admin/nodes/{id} return 202 immediately while work runs in background.
**Example:**
```python
# Source: existing codebase pattern
@admin_router.post("/admin/nodes/setup", status_code=202)
async def setup_node(
    request: SetupRequest,
    provisioner: NodeProvisioner = Depends(get_provisioner),
) -> SetupResponse:
    asyncio.create_task(provisioner.provision(request.hostname))
    return SetupResponse(task_id=request.hostname)
```

### Pattern 2: Drain Wait Loop

**What:** Poll ConnectionTracker until active connections reach 0 or timeout expires. [ASSUMED]
**When to use:** Graceful teardown before stopping container.
**Example:**
```python
async def _drain_wait(self, hostname: str) -> None:
    deadline = asyncio.get_running_loop().time() + self._settings.drain_timeout
    while asyncio.get_running_loop().time() < deadline:
        if self._tracker.get(hostname) == 0:
            return
        await asyncio.sleep(1)
    logger.warning("drain_timeout_expired", hostname=hostname)
```

### Pattern 3: EtcdClient.delete (new method)

**What:** Wrap `etcd3gw.Etcd3Client.delete()` in the EtcdClient wrapper. [VERIFIED: etcd3gw has `delete(key) -> bool`]
**When to use:** Removing node key from etcd during teardown.
**Example:**
```python
def delete(self, key: str) -> bool:
    return self._client.delete(key)
```

### Pattern 4: etcd Prefix Read for Task Listing

**What:** Read all keys under `/provisioning/` prefix for task status listing. [ASSUMED]
**When to use:** GET /admin/provisioning/tasks.
**Example:**
```python
# EtcdClient needs get_prefix with custom prefix (not just node_prefix)
# Option: add a raw get_prefix(prefix) method, or use _client directly
# Simplest: add get_raw_prefix(prefix) that takes arbitrary prefix
```

**Important note:** The current `EtcdClient.get_prefix()` is hardcoded to `self._prefix` (the node prefix `/nodes/`). For reading `/provisioning/*` keys, we need either:
1. A parameterized `get_prefix(prefix)` method, or
2. A separate method like `get_provisioning_states()` on EtcdClient

Option 1 is cleaner -- rename existing `get_prefix()` to accept an optional prefix parameter (defaulting to `self._prefix`). [VERIFIED: codebase inspection]

### Anti-Patterns to Avoid
- **Direct registry mutation from teardown:** Per established pattern, write to etcd and let watcher propagate. However, for drain (setting DRAINING status), the registry has a `drain()` method that should be called directly since we need immediate effect before waiting. The etcd delete at the end is what triggers watcher cleanup.
- **Blocking the event loop during drain wait:** Use `asyncio.sleep()`, never `time.sleep()`.
- **Fire-and-forget without error handling:** `asyncio.create_task()` tasks that raise unhandled exceptions log to stderr and are lost. Wrap teardown/provision in try/except that updates state to FAILED.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Background tasks | Task queue, worker pool | `asyncio.create_task()` | Per CLAUDE.md, no Celery. Gateway is single-process. |
| Connection counting | Custom drain tracker | `ConnectionTracker.get()` | Already exists and is thread-safe |
| Node status transition | Manual status field updates | `NodeRegistry.drain()` | Already exists, handles locking |
| SSH command execution | Raw asyncssh calls | `SSHClient.run_streaming()` or `_ssh_run_command()` | Already wraps asyncssh with error handling |
| State machine | Custom state tracker | `ProvisioningState` + `_update_state()` | Already exists in provisioner |

## Common Pitfalls

### Pitfall 1: Container Name Derivation
**What goes wrong:** Container name must match Phase 10 D-03 naming: `vllm-{model}`. The model name may contain slashes (e.g., `Qwen/Qwen2.5-72B-Instruct`). Podman container names cannot contain slashes.
**Why it happens:** Model names from HuggingFace use `org/model` format.
**How to avoid:** Check how `start-vllm.sh` derives the container name. The model field on the Node object stores the full model name. The container name derivation must match exactly what provisioning used.
**Warning signs:** `podman stop` returns "no such container" during teardown.

### Pitfall 2: Race Between Drain Mark and Connection Accept
**What goes wrong:** A new request arrives and gets routed to the node between when teardown marks it DRAINING and when the drain wait starts.
**Why it happens:** `registry.drain()` and route handler selection are not atomic.
**How to avoid:** This is acceptable per existing design -- the DRAINING node is excluded from selection by `NodeSelector.select()`, and any in-flight request that started before the drain mark will complete and decrement the tracker naturally.
**Warning signs:** Drain wait never reaches 0 connections (but the timeout handles this).

### Pitfall 3: asyncio.create_task Reference Lost
**What goes wrong:** If the task reference from `asyncio.create_task()` is not stored, the task can be garbage collected before completion.
**Why it happens:** Python GC does not keep strong references to tasks.
**How to avoid:** Store the task in a set or dict. Use `task.add_done_callback(tasks.discard)` to auto-cleanup.
**Warning signs:** Teardown silently stops mid-sequence.

### Pitfall 4: EtcdClient.delete Not Wrapped in asyncio.to_thread
**What goes wrong:** Calling `etcd3gw` delete synchronously blocks the event loop.
**Why it happens:** etcd3gw is synchronous.
**How to avoid:** Wrap in `asyncio.to_thread()` like all other etcd calls in the codebase.
**Warning signs:** Event loop stalls during teardown.

### Pitfall 5: GET /admin/provisioning/tasks Reads Node Prefix Instead of Provisioning Prefix
**What goes wrong:** The endpoint returns node data instead of provisioning task data.
**Why it happens:** `EtcdClient.get_prefix()` currently only supports the node prefix.
**How to avoid:** Add parameterized prefix support to `get_prefix()` or add a dedicated method.
**Warning signs:** Task listing returns node JSON instead of ProvisioningState JSON.

### Pitfall 6: NodeProvisioner Constructor Change Breaks Existing Tests
**What goes wrong:** Adding `registry` and `connection_tracker` parameters to `NodeProvisioner.__init__` breaks all existing tests that construct it with 3 args.
**Why it happens:** Constructor signature change.
**How to avoid:** Make the new parameters optional (default `None`). Teardown raises if they are missing. Provisioning does not need them. Existing tests remain unchanged.
**Warning signs:** Massive test failures on `TypeError: __init__() missing required positional argument`.

## Code Examples

### Extending ProvisioningStep Enum
```python
# Source: inference_proxy/provisioning/state.py (extend existing)
class ProvisioningStep(StrEnum):
    # ... existing steps ...
    DRAINING = "draining"
    STOPPING_CONTAINER = "stopping_container"
    DEREGISTERING = "deregistering"
    TEARDOWN_COMPLETE = "teardown_complete"
```

### EtcdClient.delete Method
```python
# Source: inference_proxy/discovery/etcd_client.py (add to existing class)
def delete(self, key: str) -> bool:
    """Delete a key from etcd."""
    return self._client.delete(key)
```

### EtcdClient.get_prefix with Custom Prefix
```python
# Source: inference_proxy/discovery/etcd_client.py (modify existing method)
def get_prefix(self, prefix: str | None = None) -> list[tuple[bytes, dict[str, Any]]]:
    """Fetch all key-value pairs under a prefix.
    
    Defaults to the configured node prefix if none specified.
    """
    return self._client.get_prefix(prefix or self._prefix)
```

### ProvisioningSettings Extension
```python
# Source: inference_proxy/config/settings.py (extend existing)
class ProvisioningSettings(BaseModel):
    # ... existing fields ...
    drain_timeout: int = 30  # D-10: seconds to wait for connections to drain
```

### Admin Pydantic Models
```python
# Source: inference_proxy/models/admin.py (add to existing file)
class SetupRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    hostname: str

class SetupResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    task_id: str

class TaskStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    hostname: str
    current_step: str
    started_at: datetime
    updated_at: datetime
    failed_step: str | None = None
    error: str | None = None

class TeardownResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    task_id: str
```

### DI Provider for Provisioner
```python
# Source: inference_proxy/config/dependencies.py (add)
def get_provisioner(request: Request) -> NodeProvisioner:
    return request.app.state.provisioner
```

### Provisioner Creation in Lifespan
```python
# Source: inference_proxy/main.py (add to lifespan)
from inference_proxy.provisioning.provisioner import NodeProvisioner
from inference_proxy.provisioning.ssh_client import SSHClient

ssh_client = SSHClient(resolved_settings.ssh)
provisioner = NodeProvisioner(
    ssh_client=ssh_client,
    etcd_client=etcd_client,
    settings=resolved_settings.provisioning,
    registry=registry,
    connection_tracker=connection_tracker,
)
app.state.provisioner = provisioner
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastAPI BackgroundTasks | asyncio.create_task | N/A | FastAPI's BackgroundTasks runs AFTER response is sent but is sequential. asyncio.create_task runs truly concurrently. For long-running provisioning/teardown, create_task is correct. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Container name format is `vllm-{model}` with slashes replaced or removed per start-vllm.sh | Pitfall 1 | Teardown fails to find container -- need to check actual naming in start-vllm.sh |
| A2 | Drain wait loop polling at 1-second intervals is sufficient | Pattern 2 | Low risk -- configurable timeout handles edge cases |

## Open Questions

1. **Container name derivation from model name**
   - What we know: D-01 says container name is `vllm-{model}`, Phase 10 D-03 naming convention
   - What's unclear: How are slashes in model names (e.g., `Qwen/Qwen2.5-72B-Instruct`) handled in container naming? Does start-vllm.sh replace them?
   - Recommendation: Check `auto-vllm-container/start-vllm.sh` during implementation to match exact naming

2. **Should GET /admin/provisioning/tasks filter by operation type?**
   - What we know: D-06 says it reads all `/provisioning/*` keys
   - What's unclear: Whether to distinguish setup vs teardown tasks in the response
   - Recommendation: Return all tasks with their current_step indicating what kind of operation (setup steps vs teardown steps). The step enum values are self-documenting.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 1.4+ |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/provisioning/ tests/api/test_admin.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEAR-01 | teardown() drains, SSH stops, deregisters | unit | `uv run pytest tests/provisioning/test_provisioner.py -x -k teardown` | Exists (extend) |
| TEAR-02 | Force teardown skips drain, uses podman rm --force | unit | `uv run pytest tests/provisioning/test_provisioner.py -x -k force` | Exists (extend) |
| API-01 | POST /admin/nodes/setup returns 202 + task_id | integration | `uv run pytest tests/api/test_admin.py -x -k setup` | Exists (extend) |
| API-02 | GET /admin/provisioning/tasks returns all task states | integration | `uv run pytest tests/api/test_admin.py -x -k tasks` | Exists (extend) |
| API-03 | DELETE /admin/nodes/{id} triggers teardown (graceful + force) | integration | `uv run pytest tests/api/test_admin.py -x -k "delete or teardown"` | Exists (extend) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/provisioning/test_provisioner.py tests/api/test_admin.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
None -- existing test infrastructure (`conftest.py`, test files for provisioner and admin) covers all phase requirements. New tests are extensions of existing test files. The `conftest.py` needs a `provisioner` fixture added (with mock SSHClient and EtcdClient), but that follows the established pattern.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Internal network only (CLAUDE.md constraint) |
| V3 Session Management | No | Stateless API |
| V4 Access Control | No | No auth in v1 (internal network) |
| V5 Input Validation | Yes | Pydantic models validate hostname format |
| V6 Cryptography | No | SSH keys handled by asyncssh |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via hostname | Tampering | Pydantic hostname validation; SSHClient only passes hostname as connection target, not as shell argument |
| Unauthorized teardown | Elevation of Privilege | Out of scope for v1 (internal network); future: add admin auth |

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `provisioner.py`, `state.py`, `admin.py`, `dependencies.py`, `etcd_client.py`, `settings.py`, `main.py`, `registry.py`, `connection_tracker.py`, `routes.py`, `conftest.py`
- etcd3gw `Etcd3Client.delete()` signature verified via runtime inspection: `delete(key, *, range_end=None, prev_kv=None) -> bool`

### Secondary (MEDIUM confidence)
- None

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new packages, all existing
- Architecture: HIGH - extends established patterns with locked decisions from CONTEXT.md
- Pitfalls: HIGH - identified from codebase inspection (missing delete method, constructor change, prefix hardcoding)

**Research date:** 2026-07-07
**Valid until:** 2026-08-07 (stable -- internal project, no external API changes)
