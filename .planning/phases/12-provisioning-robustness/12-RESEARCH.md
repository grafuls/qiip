# Phase 12: Provisioning Robustness - Research

**Researched:** 2026-07-02
**Domain:** Pre-flight validation, provisioning state machine, health checker coordination
**Confidence:** HIGH

## Summary

Phase 12 extends the existing `NodeProvisioner` (Phase 11) with three capabilities: pre-flight checks before setup, a fine-grained etcd-backed state machine for step tracking, and health checker coordination via a new `PROVISIONING` node status. All three are code-only changes to existing modules -- no new dependencies, no new infrastructure.

The codebase is well-structured for these additions. The provisioner already parses `[STEP:name:STATUS]` markers, the `EtcdClient` already supports `put()` via `asyncio.to_thread()`, and the health checker already filters by `NodeStatus` in its probe logic. The work is primarily: (1) add a `preflight()` method to `NodeProvisioner` that runs SSH diagnostic commands, (2) add a `ProvisioningState` Pydantic model and write state transitions to etcd, (3) add `PROVISIONING` to `NodeStatus` and guard the health checker against probing nodes in that state.

**Primary recommendation:** Extend existing code paths -- no new files beyond `provisioning/state.py` for the state model. The provisioner, health checker, and node model all get surgical edits.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Two-stage validation: TCP connect to SSH port first (fast network probe catches unreachable hosts without key exchange overhead), then SSH in to run diagnostic commands (nvidia-smi, df).
- **D-02:** Minimum 20 GB free disk space required before starting setup.
- **D-03:** Collect all pre-flight failures before aborting -- report everything wrong at once so operators fix all issues in one pass instead of fix-retry-fix-retry.
- **D-04:** Pre-flight is a separate public method `provisioner.preflight(hostname)` that operators can call independently for dry-run validation. `provision()` also calls it internally before setup.
- **D-05:** Provisioning state is etcd-backed. Written to a separate etcd key prefix (e.g., `/provisioning/`). Survives gateway restarts, queryable by admin API (Phase 13) and dashboard (Phase 14).
- **D-06:** Fine-grained states mapping 1:1 to step markers: PENDING -> PREFLIGHT -> each of 6 setup steps (nvidia_repo, system_update, nvidia_driver, nvidia_cdi, nfs_mount, firewall) -> STARTING_VLLM -> HEALTH_POLL -> REGISTERING -> COMPLETE/FAILED.
- **D-07:** Separate `ProvisioningState(BaseModel)` Pydantic model in the provisioning package. Not on the Node model -- Node is frozen and shared across routing/health/proxy. Separate etcd key prefix keeps concerns clean.
- **D-08:** FAILED state includes both `failed_step` (step name) and `error` (message string). Operators see what and why without checking logs.
- **D-09:** Add `NodeStatus.PROVISIONING` to the enum. Register node in etcd with PROVISIONING status before setup starts. Health checker skips nodes with this status.
- **D-10:** Node transitions from PROVISIONING to HEALTHY after `_poll_health` succeeds (200 OK from vLLM). Clean handoff -- health checker takes over from there.
- **D-11:** On provisioning failure, node stays in etcd with a FAILED-equivalent status (visible to dashboard). Not removed -- operators need to see what failed and re-trigger.

### Claude's Discretion
None -- all decisions made by user.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROV-05 | Pre-flight validation checks SSH reachable, GPU present, and disk space before setup | D-01 through D-04: TCP probe + SSH diagnostics via existing `SSHClient`, collect-all-errors pattern, standalone `preflight()` method |
| PROV-06 | Setup tracks per-step progress via a state machine (PENDING -> steps -> COMPLETE/FAILED) | D-05 through D-08: `ProvisioningState` model in `provisioning/state.py`, etcd `/provisioning/` prefix, state writes hook into existing `STEP_PATTERN` parsing in `_run_setup()` |
| PROV-07 | PROVISIONING node status prevents health checker from marking node unhealthy during setup | D-09 through D-11: Add `PROVISIONING` to `NodeStatus` enum, guard in `_probe_all_nodes()` to skip, register node with PROVISIONING status at start of `provision()` |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **SOLID principles required** -- all code must follow SRP, OCP, LSP, ISP, DIP
- **DIP enforced** -- SSHClient wraps asyncssh, EtcdClient wraps etcd3gw; provisioning state writes go through EtcdClient, never direct etcd3gw
- **Frozen Pydantic models** -- ProvisioningState must use `ConfigDict(frozen=True)` per existing pattern
- **Package-per-domain** -- state model goes in `provisioning/` package
- **No unnecessary abstractions** -- concrete class, no protocol/interface for single-implementation types (per Phase 11 D-15)
- **Tech stack** -- Python 3.12, FastAPI, httpx, asyncssh, etcd3gw, structlog, pydantic

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Pre-flight validation (SSH reachability, GPU, disk) | API / Backend | -- | SSH commands execute from gateway process, validate remote host state |
| Provisioning state machine | API / Backend | Database / Storage (etcd) | State transitions happen in gateway; persistence is etcd |
| Health checker coordination | API / Backend | -- | Health checker thread runs in gateway process, reads NodeStatus from registry |
| Node status enum | API / Backend | -- | Shared domain model consumed by routing, health, proxy, admin |

## Standard Stack

No new dependencies. This phase uses only what is already installed:

### Core (already installed)
| Library | Version | Purpose | Phase 12 Use |
|---------|---------|---------|--------------|
| asyncssh | >=2.20 | SSH client | Pre-flight: TCP probe via `asyncio.open_connection()`, SSH diagnostic commands via `SSHClient.run_streaming()` |
| pydantic | >=2.10 | Data validation | `ProvisioningState` model with frozen config |
| etcd3gw | >=2.5.0 | etcd client | Write provisioning state to `/provisioning/` prefix |
| structlog | >=26.1.0 | Structured logging | Log pre-flight results, state transitions |
| httpx | >=0.28 | HTTP client | Already used in `_poll_health()` -- no change |

No new packages to install. No `Package Legitimacy Audit` section needed.

## Architecture Patterns

### System Architecture Diagram

```
                    provision(hostname)
                          |
                    +-----v------+
                    | preflight  |   TCP connect -> SSH diagnostics
                    | (collect   |   nvidia-smi, df, gpu count
                    |  errors)   |   ALL failures collected before abort
                    +-----+------+
                          | pass
              +-----------v-----------+
              | Register node in etcd |   status=PROVISIONING
              | Write initial state   |   /provisioning/{hostname}
              +-----------+-----------+
                          |
               +----------v-----------+
               | _run_setup()         |   Parses [STEP:name:STATUS]
               | State updates:       |   Each marker -> etcd write
               | nvidia_repo -> ...   |   /provisioning/{hostname}
               | -> firewall          |
               +----------+-----------+
                          |
               +----------v-----------+
               | _run_start_vllm()    |   State: STARTING_VLLM
               +----------+-----------+
                          |
               +----------v-----------+
               | _poll_health()       |   State: HEALTH_POLL
               +----------+-----------+        |
                          |                    |
                          | 200 OK             | timeout
                          v                    v
              +----------+------+    +---------+------+
              | _register_node()|    | State: FAILED  |
              | status=HEALTHY  |    | failed_step +  |
              | State: COMPLETE |    | error message  |
              +--------+--------+    +----------------+
                       |
            Health checker takes over

    Health Checker Thread (parallel):
    +-----------------------------------------+
    | for node in registry.get_all():         |
    |   if node.status == PROVISIONING: skip  |  <-- D-09
    |   else: probe /health                   |
    +-----------------------------------------+
```

### Recommended Project Structure

```
inference_proxy/
├── provisioning/
│   ├── __init__.py          # existing
│   ├── provisioner.py       # MODIFIED: add preflight(), state tracking, PROVISIONING registration
│   ├── ssh_client.py        # existing, unchanged
│   └── state.py             # NEW: ProvisioningState model, ProvisioningStep enum
├── models/
│   └── node.py              # MODIFIED: add PROVISIONING to NodeStatus
├── config/
│   └── settings.py          # MODIFIED: add min_disk_gb to ProvisioningSettings
├── discovery/
│   └── etcd_client.py       # existing, unchanged (already has put())
└── resilience/
    └── health_checker.py    # MODIFIED: skip PROVISIONING nodes in _probe_all_nodes()
```

### Pattern 1: Pre-flight with Collected Errors (D-03)

**What:** Run all pre-flight checks, collect every failure, then raise a single error with all problems listed.
**When to use:** When an operator needs to fix multiple issues in one pass.

```python
# [ASSUMED] -- pattern derived from D-01 through D-04
class PreflightError(Exception):
    """One or more pre-flight checks failed."""
    def __init__(self, hostname: str, failures: list[str]) -> None:
        self.hostname = hostname
        self.failures = failures
        summary = "; ".join(failures)
        super().__init__(f"Pre-flight failed for {hostname}: {summary}")

async def preflight(self, hostname: str) -> None:
    """Validate host readiness. Collects all failures before raising."""
    failures: list[str] = []

    # Stage 1: TCP probe (D-01 -- fast, no key exchange)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(hostname, 22),
            timeout=self._settings.ssh.connect_timeout,
        )
        writer.close()
        await writer.wait_closed()
    except (OSError, asyncio.TimeoutError) as exc:
        failures.append(f"SSH port 22 unreachable: {exc}")
        # Cannot proceed to stage 2 without SSH
        raise PreflightError(hostname, failures) from exc

    # Stage 2: SSH diagnostics (D-01)
    try:
        # GPU check
        gpu_output = await self._ssh_run_command(hostname, "nvidia-smi --query-gpu=name --format=csv,noheader")
        gpu_count = len([line for line in gpu_output.splitlines() if line.strip()])
        if gpu_count == 0:
            failures.append("No GPUs detected (nvidia-smi returned no devices)")

        # Disk space check (D-02)
        df_output = await self._ssh_run_command(hostname, "df --output=avail / | tail -1")
        avail_kb = int(df_output.strip())
        avail_gb = avail_kb / (1024 * 1024)
        if avail_gb < self._settings.min_disk_gb:
            failures.append(f"Insufficient disk: {avail_gb:.1f}GB free, need {self._settings.min_disk_gb}GB")
    except (SSHConnectionError, RemoteCommandError) as exc:
        failures.append(f"SSH diagnostic failed: {exc}")

    if failures:
        raise PreflightError(hostname, failures)
```

### Pattern 2: State Machine with etcd Writes (D-05, D-06)

**What:** A Pydantic model representing provisioning progress, serialized to etcd on every transition.
**When to use:** Every time the provisioner moves to a new step.

```python
# [ASSUMED] -- derived from D-05 through D-08
from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ProvisioningStep(StrEnum):
    """Fine-grained provisioning steps (D-06)."""
    PENDING = "pending"
    PREFLIGHT = "preflight"
    NVIDIA_REPO = "nvidia_repo"
    SYSTEM_UPDATE = "system_update"
    NVIDIA_DRIVER = "nvidia_driver"
    NVIDIA_CDI = "nvidia_cdi"
    NFS_MOUNT = "nfs_mount"
    FIREWALL = "firewall"
    STARTING_VLLM = "starting_vllm"
    HEALTH_POLL = "health_poll"
    REGISTERING = "registering"
    COMPLETE = "complete"
    FAILED = "failed"

class ProvisioningState(BaseModel):
    """Provisioning progress for a single host (D-07)."""
    model_config = ConfigDict(frozen=True)

    hostname: str
    current_step: ProvisioningStep
    started_at: datetime
    updated_at: datetime
    failed_step: str | None = None  # D-08
    error: str | None = None        # D-08
```

### Pattern 3: Health Checker Guard (D-09)

**What:** Skip PROVISIONING nodes in the health checker probe loop.
**When to use:** Prevents spurious probes and premature status changes.

```python
# [ASSUMED] -- derived from D-09, applied to existing _probe_all_nodes()
def _probe_all_nodes(...) -> None:
    nodes = registry.get_all()
    for node in nodes:
        if node.status == NodeStatus.PROVISIONING:
            continue  # D-09: skip nodes being provisioned
        _probe_node(...)
```

### Anti-Patterns to Avoid

- **Putting provisioning state on the Node model:** Node is frozen, shared across routing/health/proxy. Provisioning state is a separate concern with its own lifecycle and etcd prefix. Mixing them violates SRP and creates coupling.
- **Failing fast on first pre-flight error:** D-03 explicitly requires collecting ALL failures. An operator re-imaging a machine may have 3 problems -- report all, not just the first.
- **Probing PROVISIONING nodes:** The health checker would send HTTP requests to a host that may not have vLLM running, generating spurious failure logs. Worse, `_handle_probe_success()` checks `if current_status != NodeStatus.HEALTHY` and would mark a PROVISIONING node HEALTHY prematurely if vLLM happened to respond during setup.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TCP port probe | Raw socket code | `asyncio.open_connection()` + `wait_for()` | stdlib handles timeout, cleanup, error reporting |
| SSH command execution | Direct asyncssh calls | Existing `SSHClient` wrapper | DIP -- SSHClient is the sole asyncssh consumer |
| etcd state persistence | Direct etcd3gw calls | Existing `EtcdClient.put()` via `asyncio.to_thread()` | DIP -- EtcdClient is the sole etcd3gw consumer |
| JSON serialization | Manual dict construction | `model.model_dump(mode="json")` + `json.dumps()` | Pydantic handles datetime serialization, validation |

## Common Pitfalls

### Pitfall 1: TCP Probe Succeeds but SSH Auth Fails
**What goes wrong:** TCP connect to port 22 succeeds (host is reachable, sshd is running), but SSH key auth fails. Pre-flight reports "SSH reachable" but then diagnostic commands fail.
**Why it happens:** TCP probe only checks network + port, not authentication.
**How to avoid:** The two-stage design (D-01) handles this correctly. Stage 1 (TCP) catches unreachable hosts fast. Stage 2 (SSH commands) catches auth failures. Both failure types are collected.
**Warning signs:** TCP probe passes but all SSH diagnostic commands fail with `SSHConnectionError`.

### Pitfall 2: Race Between Provisioner and Health Checker on Node Registration
**What goes wrong:** Provisioner registers node with `PROVISIONING` status. Health checker probe cycle is already running, picks up the node before the status guard executes.
**Why it happens:** Health checker runs in a separate thread with its own probe cycle timing.
**How to avoid:** The guard in `_probe_all_nodes()` checks status at probe time, not at cycle start. Even if the node appears mid-cycle, the guard catches it. The existing code iterates `registry.get_all()` and probes each node individually, so the status check is per-node, not per-cycle.
**Warning signs:** Spurious "health probe failed" log entries for nodes that are being provisioned.

### Pitfall 3: State Write Failures Silent During Provisioning
**What goes wrong:** etcd is temporarily unreachable during provisioning. State writes via `asyncio.to_thread()` fail. Provisioning continues but state is stale in etcd.
**Why it happens:** State writes are informational -- the provisioner shouldn't abort setup because a state update failed.
**How to avoid:** Wrap state writes in try/except, log the failure, continue provisioning. The state is best-effort observability, not a control mechanism.
**Warning signs:** State stuck on an old step in etcd while provisioning has progressed.

### Pitfall 4: `asyncio.open_connection()` Needs Explicit Cleanup
**What goes wrong:** TCP probe opens a connection, gets the reader/writer, but doesn't close the writer. Leaves dangling sockets.
**Why it happens:** `asyncio.open_connection()` doesn't use context manager pattern.
**How to avoid:** Always call `writer.close()` and `await writer.wait_closed()` after probe succeeds. On failure (exception), the connection was never established, so no cleanup needed.
**Warning signs:** Resource warnings about unclosed transports in test output.

### Pitfall 5: Adding PROVISIONING to NodeStatus Breaks Test Assertions
**What goes wrong:** `tests/models/test_node.py::TestNodeStatusEnumValues` asserts `len(NodeStatus) == 4`. Adding PROVISIONING makes it 5.
**Why it happens:** Test is explicit about enum member count.
**How to avoid:** Update the test to assert `len(NodeStatus) == 5` and add `assert NodeStatus.PROVISIONING == "provisioning"`.
**Warning signs:** Test failure immediately after adding the enum variant.

### Pitfall 6: EtcdClient Needs a Provisioning Prefix
**What goes wrong:** Provisioning state is written to `/nodes/` prefix, colliding with node registration data.
**Why it happens:** `EtcdClient` is constructed with `EtcdSettings.node_prefix` which is `/nodes/`.
**How to avoid:** D-05 specifies a separate `/provisioning/` prefix. Either (a) add a `provisioning_prefix` to `EtcdSettings`, or (b) have the provisioner construct the key directly as `/provisioning/{hostname}` and pass it to `etcd_client.put()`. Option (b) is simpler -- `put()` takes a full key, not a prefix-relative key.
**Warning signs:** Provisioning state appears in the admin node list or corrupts node data.

## Code Examples

### SSH Diagnostic Command (non-streaming)

The existing `SSHClient.run_streaming()` yields line-by-line. For pre-flight diagnostics, we need the full output as a string. Two approaches:

**Option A: Add a `run()` method to SSHClient** [ASSUMED]
```python
async def run(self, host: str, command: str) -> str:
    """Run command, return stdout as string. Raises on non-zero exit."""
    lines = []
    async for stream, line in self.run_streaming(host, command):
        if stream == "stdout":
            lines.append(line)
    return "\n".join(lines)
```

**Option B: Consume `run_streaming()` in preflight** [ASSUMED]
```python
async def _ssh_run_command(self, hostname: str, command: str) -> str:
    lines = []
    async for stream, line in self._ssh_client.run_streaming(hostname, command):
        if stream == "stdout":
            lines.append(line)
    return "\n".join(lines)
```

Option A is cleaner (reusable) but adds to SSHClient's API surface. Option B is private to the provisioner. Both work. The planner should decide based on whether Phase 13 (Admin API) will also need non-streaming SSH commands.

### State Transition Write to etcd

```python
# [ASSUMED] -- pattern for etcd state writes
import json
from datetime import datetime, timezone

async def _update_state(
    self,
    hostname: str,
    step: ProvisioningStep,
    *,
    failed_step: str | None = None,
    error: str | None = None,
) -> None:
    """Write provisioning state to etcd. Best-effort -- does not abort on failure."""
    state = ProvisioningState(
        hostname=hostname,
        current_step=step,
        started_at=self._provision_started_at,
        updated_at=datetime.now(timezone.utc),
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

### Registering Node with PROVISIONING Status (D-09)

```python
# [ASSUMED] -- at start of provision(), before setup
async def provision(self, hostname: str) -> None:
    await self.preflight(hostname)
    # Register with PROVISIONING status so health checker skips it
    node = Node(
        node_id=hostname,
        endpoint=f"{hostname}:{self._settings.vllm_port}",
        status=NodeStatus.PROVISIONING,
        last_heartbeat=datetime.now(timezone.utc),
    )
    key, value = node_to_etcd(node, self._etcd_client.prefix)
    await asyncio.to_thread(self._etcd_client.put, key, value)
    # ... rest of provisioning
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fire-and-forget provisioning (Phase 11) | Step-tracked state machine with pre-flight (Phase 12) | This phase | Operators can observe provisioning progress and diagnose failures without reading logs |
| Health checker probes all nodes | Health checker skips PROVISIONING nodes | This phase | No spurious failure logs or premature HEALTHY transitions during setup |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `asyncio.open_connection(host, 22)` is sufficient for TCP probe of SSH port | Code Examples | Low -- stdlib, well-documented. Alternative is raw socket. |
| A2 | `nvidia-smi --query-gpu=name --format=csv,noheader` returns one line per GPU | Code Examples | Low -- standard nvidia-smi usage. If format differs, parsing logic adjusts. |
| A3 | `df --output=avail / | tail -1` returns available KB on the root filesystem | Code Examples | Low -- standard coreutils. RHEL/Fedora targets guaranteed to have GNU df. |
| A4 | `EtcdClient.put()` accepts arbitrary full keys (not just prefix-scoped) | Architecture Patterns | Medium -- verified by reading `put()` source: it passes key directly to `etcd3gw.put()`. No prefix enforcement. |
| A5 | Option A (add `run()` to SSHClient) vs Option B (private helper) -- planner decides | Code Examples | Low -- both work, stylistic choice |

## Open Questions

1. **Should `preflight()` take `SSHSettings` connect_timeout or a separate pre-flight timeout?**
   - What we know: D-01 says TCP probe is "fast". `SSHSettings.connect_timeout` is 10s.
   - What's unclear: Whether 10s is appropriate for the TCP probe (it's generous for a LAN).
   - Recommendation: Reuse `SSHSettings.connect_timeout` for TCP probe. Add `preflight_timeout` to `ProvisioningSettings` only if needed.

2. **Should `ProvisioningState` include a `gpu_count` field from pre-flight?**
   - What we know: Pre-flight detects GPU count. Dashboard (Phase 14) might want to show it.
   - What's unclear: Whether this data belongs on ProvisioningState or is just logged.
   - Recommendation: Keep it out of ProvisioningState for now. Log it. Phase 14 can add it if needed. YAGNI.

3. **What happens if `provision()` is called for a hostname that already has a ProvisioningState in etcd?**
   - What we know: `etcd_client.put()` overwrites. No conflict detection.
   - What's unclear: Whether we should check for existing state and warn/abort.
   - Recommendation: Overwrite silently. Re-provisioning is a valid operation. The new state replaces the old.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 (auto mode) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/provisioning/ tests/resilience/test_health_checker.py tests/models/test_node.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROV-05a | TCP probe detects unreachable host | unit | `pytest tests/provisioning/test_provisioner.py::TestPreflight::test_tcp_unreachable -x` | Wave 0 |
| PROV-05b | SSH diagnostics detect missing GPU | unit | `pytest tests/provisioning/test_provisioner.py::TestPreflight::test_no_gpu -x` | Wave 0 |
| PROV-05c | SSH diagnostics detect insufficient disk | unit | `pytest tests/provisioning/test_provisioner.py::TestPreflight::test_insufficient_disk -x` | Wave 0 |
| PROV-05d | All failures collected before raising | unit | `pytest tests/provisioning/test_provisioner.py::TestPreflight::test_collects_all_failures -x` | Wave 0 |
| PROV-05e | preflight() callable independently | unit | `pytest tests/provisioning/test_provisioner.py::TestPreflight::test_standalone_preflight -x` | Wave 0 |
| PROV-06a | State transitions through all steps on success | unit | `pytest tests/provisioning/test_provisioner.py::TestStateTracking::test_full_success_transitions -x` | Wave 0 |
| PROV-06b | FAILED state includes failed_step and error | unit | `pytest tests/provisioning/test_provisioner.py::TestStateTracking::test_failed_state -x` | Wave 0 |
| PROV-06c | State written to etcd /provisioning/ prefix | unit | `pytest tests/provisioning/test_provisioner.py::TestStateTracking::test_etcd_prefix -x` | Wave 0 |
| PROV-07a | PROVISIONING added to NodeStatus enum | unit | `pytest tests/models/test_node.py::TestNodeStatusEnumValues -x` | Exists (update) |
| PROV-07b | Health checker skips PROVISIONING nodes | unit | `pytest tests/resilience/test_health_checker.py::TestProvisioningNodeSkipped -x` | Wave 0 |
| PROV-07c | Node registered with PROVISIONING before setup | unit | `pytest tests/provisioning/test_provisioner.py::TestProvisionSequence::test_registers_provisioning_before_setup -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/provisioning/ tests/resilience/test_health_checker.py tests/models/test_node.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/provisioning/test_provisioner.py` -- add `TestPreflight` and `TestStateTracking` classes
- [ ] `tests/resilience/test_health_checker.py` -- add `TestProvisioningNodeSkipped` class
- [ ] `tests/models/test_node.py` -- update `TestNodeStatusEnumValues` for 5 members
- [ ] `tests/provisioning/test_state.py` -- ProvisioningState model validation tests (optional, low complexity)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | SSH key auth handled by asyncssh (Phase 11) |
| V3 Session Management | No | No sessions in provisioning flow |
| V4 Access Control | No | Internal network only, no auth in v1 |
| V5 Input Validation | Yes | Pydantic validates ProvisioningState, hostname validated by SSH connection attempt |
| V6 Cryptography | No | SSH transport layer handles crypto |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via hostname | Tampering | hostname passed to `asyncio.open_connection()` and `asyncssh.connect()` which validate format; not interpolated into shell commands |
| State tampering in etcd | Tampering | Internal network, etcd access is trusted; no auth on etcd in v1 per project constraints |

## Sources

### Primary (HIGH confidence)
- `inference_proxy/provisioning/provisioner.py` -- existing provisioner code, line-by-line analysis
- `inference_proxy/resilience/health_checker.py` -- health checker probe logic, status guards
- `inference_proxy/models/node.py` -- NodeStatus enum, Node model (frozen)
- `inference_proxy/config/settings.py` -- ProvisioningSettings, SSHSettings
- `inference_proxy/discovery/etcd_client.py` -- EtcdClient.put() accepts full keys
- `auto-vllm-container/setup.sh` -- 6 step names confirmed: nvidia_repo, system_update, nvidia_driver, nvidia_cdi, nfs_mount, firewall
- `tests/provisioning/test_provisioner.py` -- existing test patterns and mock strategies
- `tests/resilience/test_health_checker.py` -- health checker test patterns
- `tests/models/test_node.py` -- enum count assertion at line 19

### Secondary (MEDIUM confidence)
- Python stdlib `asyncio.open_connection()` -- [CITED: docs.python.org/3/library/asyncio-stream.html]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing code verified by reading source
- Architecture: HIGH -- all integration points traced through source code, patterns match existing codebase conventions
- Pitfalls: HIGH -- derived from actual code analysis (e.g., health checker race condition, enum count assertion, etcd prefix collision)

**Research date:** 2026-07-02
**Valid until:** 2026-08-02 (stable -- internal codebase, no external dependency changes)
