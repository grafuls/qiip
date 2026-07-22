# Phase 23: Auto-Power-On in Provisioner - Research

**Researched:** 2026-07-22
**Domain:** Provisioning orchestration / Redfish BMC integration
**Confidence:** HIGH

## Summary

This phase inserts an automatic Redfish power-on step into the existing provisioning sequence so offline servers are powered up before SSH provisioning begins. All building blocks already exist in the codebase: `RedfishClient.get_power_state()` and `RedfishClient.power_action("On")` (Phase 21), `NodeProvisioner` with constructor injection and step-based state tracking, and `ProvisioningStep` StrEnum that the dashboard renders dynamically.

The work is a pure internal integration -- no new packages, no new external dependencies, no API surface changes. The provisioner gains an optional `RedfishClient` parameter (matching the existing `QUADSClient | None` pattern), a new `POWERING_ON` enum member, a private `_power_on_if_needed()` method, and a TCP-based SSH wait loop before preflight.

**Primary recommendation:** Follow existing constructor-injection and optional-None patterns exactly. Keep all new logic inside `provisioner.py` as private methods. The SSH wait loop reuses `asyncio.open_connection` (already used in preflight's TCP probe).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** When RedfishClient is None (not configured), skip the power-on step entirely and proceed directly to preflight -- backward-compatible with existing deployments
- **D-02:** Log skip at INFO level: "redfish_not_configured, skipping power check"
- **D-03:** Add a dedicated SSH wait loop (TCP probe retries) before preflight, separate from the existing single-probe preflight check -- clean separation of concerns (SRP)
- **D-04:** Single `POWERING_ON` dashboard step covers the entire boot sequence (Redfish power action + SSH wait loop) -- operators see "powering on" until SSH is ready
- **D-05:** Default boot wait timeout: 300 seconds (5 minutes), configurable via ProvisioningSettings -- covers most cold boots with margin
- **D-06:** Best-effort power-on: if Redfish power action fails (BMC unreachable, timeout, bad credentials), log warning and continue to preflight -- server might already be on
- **D-07:** Still show POWERING_ON step in dashboard before transitioning to PREFLIGHT on failure -- operator sees the attempt was made

### Claude's Discretion
- SSH wait loop probe interval (e.g., 5-10s between TCP probes)
- Whether to add `boot_wait_timeout` and `boot_wait_interval` as new ProvisioningSettings fields or reuse existing patterns
- Whether `_power_on_if_needed()` is a private method on NodeProvisioner or a standalone helper
- Test structure for the new power-on logic

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PWR-05 | Provisioning automatically powers on a node before SSH setup if the node is off | RedfishClient.power_action("On") already implements check-before-act + poll; NodeProvisioner.provision() has clear insertion point between PENDING and PREFLIGHT |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Power-on decision | API / Backend (NodeProvisioner) | -- | Provisioner owns the setup sequence; power check is a pre-step |
| BMC communication | API / Backend (RedfishClient) | -- | Already exists; provisioner delegates to it |
| SSH readiness probe | API / Backend (NodeProvisioner) | -- | TCP probe is server-side; same tier as existing preflight |
| Dashboard step display | Browser / Client | API / Backend (etcd state) | Dashboard reads steps from etcd; provisioner writes POWERING_ON state |
| Boot timeout config | API / Backend (ProvisioningSettings) | -- | pydantic-settings with env var override |

## Standard Stack

No new packages. This phase uses only what is already installed:

| Library | Version | Purpose | Already Installed |
|---------|---------|---------|-------------------|
| asyncio (stdlib) | 3.12 | `open_connection` TCP probe, `sleep`, `get_running_loop().time()` deadline | Yes (stdlib) |
| structlog | >=26.1.0 | Structured logging for power-on and SSH wait events | Yes |
| RedfishClient | internal | `get_power_state()`, `power_action("On")` | Yes (Phase 21) |

**Installation:** None required. Zero new dependencies (per project decision: "Zero new dependencies for v1.5").

## Architecture Patterns

### System Architecture Diagram

```
provision("hostname") called
         |
         v
  [PENDING state write]
         |
         v
  +-- RedfishClient is None? --+
  |  YES                       |  NO
  |  log skip, continue        |  _power_on_if_needed(hostname)
  |                            |    |
  |                            |    v
  |                            |  [POWERING_ON state write]
  |                            |    |
  |                            |    v
  |                            |  power_action("On")  <-- best-effort
  |                            |  (catch RedfishError, log warning)
  |                            |    |
  |                            |    v
  |                            |  _wait_for_ssh(hostname)
  |                            |  (TCP probe loop, port 22)
  |                            |  timeout: boot_wait_timeout (300s)
  |                            |    |
  +<---------------------------+    |
  |                                 |
  v                                 v
  [PREFLIGHT state write]
  |
  v
  preflight(hostname)  <-- existing, unchanged
  |
  v
  ... rest of provision sequence unchanged ...
```

### Recommended Changes (by file)

```
inference_proxy/
  provisioning/
    provisioner.py   # Add _power_on_if_needed(), _wait_for_ssh(), modify __init__ + provision()
    state.py         # Add POWERING_ON to ProvisioningStep enum
  config/
    settings.py      # Add boot_wait_timeout + boot_wait_interval to ProvisioningSettings
  main.py            # Pass redfish_client to NodeProvisioner constructor
tests/
  provisioning/
    test_provisioner.py  # Add TestPowerOnIfNeeded, TestWaitForSsh classes
```

### Pattern 1: Optional Dependency Injection (Constructor)

**What:** Add `redfish_client: RedfishClient | None = None` to `NodeProvisioner.__init__()`.
**When to use:** When a feature is conditionally available (Redfish may not be configured).
**Example:**
```python
# Source: inference_proxy/provisioning/provisioner.py lines 69-83 (existing pattern)
def __init__(
    self,
    ssh_client: SSHClient,
    etcd_client: EtcdClient,
    settings: ProvisioningSettings,
    registry: NodeRegistry | None = None,
    connection_tracker: ConnectionTracker | None = None,
    redfish_client: RedfishClient | None = None,  # NEW
) -> None:
    # ... existing assignments ...
    self._redfish_client = redfish_client
```

### Pattern 2: Best-Effort with Catch-and-Continue

**What:** Try a Redfish action, catch `RedfishError`, log warning, continue.
**When to use:** When failure of the action should not block the overall operation (D-06).
**Example:**
```python
# Source: Mirrors existing best-effort etcd writes in _update_state() lines 98-114
async def _power_on_if_needed(self, hostname: str) -> None:
    if self._redfish_client is None:
        logger.info("redfish_not_configured", msg="skipping power check")
        return
    await self._update_state(hostname, ProvisioningStep.POWERING_ON)
    try:
        state = await self._redfish_client.power_action(hostname, "On")
        logger.info("power_on_result", hostname=hostname, state=state)
    except RedfishError as exc:
        logger.warning("power_on_failed", hostname=hostname, error=str(exc))
    # Always proceed to SSH wait regardless of power action result
    await self._wait_for_ssh(hostname)
```

### Pattern 3: TCP Probe Retry Loop with Deadline

**What:** Poll TCP port 22 until connection succeeds or timeout expires.
**When to use:** Waiting for a cold-booting server to become SSH-reachable.
**Example:**
```python
# Source: Mirrors _poll_health() lines 282-302 (deadline pattern) and
#         preflight() lines 137-145 (open_connection pattern)
async def _wait_for_ssh(self, hostname: str) -> None:
    deadline = asyncio.get_running_loop().time() + self._settings.boot_wait_timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(hostname, 22), timeout=10
            )
            writer.close()
            await writer.wait_closed()
            logger.info("ssh_ready", hostname=hostname)
            return
        except (OSError, TimeoutError, asyncio.TimeoutError):
            pass
        await asyncio.sleep(self._settings.boot_wait_interval)
    logger.warning("ssh_wait_timeout", hostname=hostname,
                   timeout=self._settings.boot_wait_timeout)
```

### Pattern 4: ProvisioningStep Enum Member Ordering

**What:** Add `POWERING_ON` member to ProvisioningStep before PREFLIGHT.
**When to use:** When adding a new step to the provisioning sequence.
**Example:**
```python
# Source: inference_proxy/provisioning/state.py lines 19-39
class ProvisioningStep(StrEnum):
    PENDING = "pending"
    POWERING_ON = "powering_on"  # NEW -- before PREFLIGHT
    PREFLIGHT = "preflight"
    # ... rest unchanged ...
```

### Anti-Patterns to Avoid
- **Modifying preflight() to include power logic:** Violates SRP (D-03). Power-on and SSH wait are separate from validation.
- **Raising on Redfish failure:** D-06 explicitly requires best-effort. The server might already be on.
- **Coupling SSH wait timeout to health_poll_timeout:** These are different operations with different timing characteristics. Boot wait (300s) vs health poll (600s for model loading).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TCP port probe | Custom socket code | `asyncio.open_connection(host, 22)` | Already used in preflight; handles IPv4/IPv6, async, proper cleanup |
| Redfish power-on with idempotency | Direct POST to BMC | `RedfishClient.power_action("On")` | Already implements check-before-act + poll (D-03, D-04 of Phase 21) |
| Deadline-based retry loop | Custom timer class | `asyncio.get_running_loop().time()` + deadline float | Already used in `_poll_health()` and `_drain_wait()` |

**Key insight:** Every primitive needed for this phase already exists in the codebase. The work is composition, not creation.

## Common Pitfalls

### Pitfall 1: Breaking Existing Tests
**What goes wrong:** Adding `redfish_client` parameter to `NodeProvisioner.__init__()` breaks existing test helper `_make_provisioner()` and all callers.
**Why it happens:** Constructor signature change.
**How to avoid:** Use `redfish_client: RedfishClient | None = None` as a keyword-only default. The existing `_make_provisioner()` helper does not pass `redfish_client`, so `None` default preserves backward compatibility.
**Warning signs:** Test failures in `test_provisioner.py` after modifying `__init__`.

### Pitfall 2: SSH Wait Loop Never Terminates
**What goes wrong:** If `boot_wait_timeout` is set too high or the server never comes up, the provisioning call blocks indefinitely.
**Why it happens:** No deadline enforcement.
**How to avoid:** Use the same deadline pattern as `_poll_health()`: `loop.time() + timeout` comparison. After timeout, log warning and proceed to preflight (which will fail fast on TCP probe if SSH is truly unreachable).
**Warning signs:** Provisioning tasks stuck in POWERING_ON state.

### Pitfall 3: Enum Ordering Affects Dashboard
**What goes wrong:** Adding `POWERING_ON` after `PREFLIGHT` in the enum makes the dashboard show incorrect step progression.
**Why it happens:** Dashboard may render steps in enum declaration order.
**How to avoid:** Add `POWERING_ON` between `PENDING` and `PREFLIGHT` in the StrEnum definition.
**Warning signs:** Dashboard shows steps in wrong order.

### Pitfall 4: Double State Write on Redfish Skip
**What goes wrong:** Writing POWERING_ON state even when Redfish is None, then immediately writing PREFLIGHT -- dashboard flashes POWERING_ON briefly.
**Why it happens:** State write before the None check.
**How to avoid:** Check `self._redfish_client is None` before writing POWERING_ON state. When skipped, go directly PENDING -> PREFLIGHT.
**Warning signs:** Dashboard briefly shows POWERING_ON for non-Redfish deployments.

## Code Examples

### Provisioning Settings Extension

```python
# Source: inference_proxy/config/settings.py -- extend ProvisioningSettings
class ProvisioningSettings(BaseModel):
    # ... existing fields ...
    boot_wait_timeout: int = 300   # D-05: 5 minutes for cold boot
    boot_wait_interval: int = 10   # ponytail: 10s between probes, adjustable
```

### Main.py Wiring

```python
# Source: inference_proxy/main.py -- modify provisioner construction (lines 164-170)
provisioner = NodeProvisioner(
    ssh_client=ssh_client,
    etcd_client=etcd_client,
    settings=resolved_settings.provisioning,
    registry=registry,
    connection_tracker=connection_tracker,
    redfish_client=app.state.redfish_client,  # NEW -- may be None
)
```

### Provision Method Insertion Point

```python
# Source: inference_proxy/provisioning/provisioner.py lines 178-199
async def provision(self, hostname: str, *, managed: bool = True) -> None:
    self._provision_started_at = datetime.now(timezone.utc)
    logger.info("provisioning_start", hostname=hostname)

    await self._update_state(hostname, ProvisioningStep.PENDING)

    # NEW: power-on before preflight
    await self._power_on_if_needed(hostname)

    await self._update_state(hostname, ProvisioningStep.PREFLIGHT)
    # ... rest unchanged ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual server power-on before provisioning | Auto power-on via Redfish in provisioning flow | Phase 23 (this phase) | Eliminates manual step; provisioning works on powered-off servers |

## Assumptions Log

> All claims verified against codebase. No assumptions.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| -- | (none) | -- | -- |

**If this table is empty:** All claims in this research were verified or cited -- no user confirmation needed.

## Open Questions

None. All integration points are well-defined in the existing codebase, and all decisions are locked in CONTEXT.md.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio (auto mode) |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/provisioning/test_provisioner.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PWR-05a | Power-on called when Redfish configured and server is off | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestPowerOnIfNeeded -x` | Wave 0 |
| PWR-05b | Power-on skipped when Redfish is None | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestPowerOnIfNeeded -x` | Wave 0 |
| PWR-05c | SSH wait loop retries until port 22 reachable | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestWaitForSsh -x` | Wave 0 |
| PWR-05d | SSH wait loop times out and proceeds | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestWaitForSsh -x` | Wave 0 |
| PWR-05e | POWERING_ON state written to etcd for dashboard | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestPowerOnIfNeeded -x` | Wave 0 |
| PWR-05f | Redfish error caught, logged, and provisioning continues | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestPowerOnIfNeeded -x` | Wave 0 |
| PWR-05g | Full provision() sequence includes power-on step | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestProvisionSequence -x` | Modify existing |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/provisioning/test_provisioner.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/provisioning/test_provisioner.py::TestPowerOnIfNeeded` -- new test class for power-on logic
- [ ] `tests/provisioning/test_provisioner.py::TestWaitForSsh` -- new test class for SSH wait loop

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | BMC auth already handled by RedfishClient (Phase 21) |
| V3 Session Management | No | N/A |
| V4 Access Control | No | Admin endpoints already gated (existing) |
| V5 Input Validation | No | No new user input; hostname comes from existing provision() call |
| V6 Cryptography | No | N/A |

### Known Threat Patterns

No new threat surface. This phase adds internal logic between existing components. The BMC credentials and TLS verification are already configured in Phase 21's `RedfishSettings`.

## Sources

### Primary (HIGH confidence)
- `inference_proxy/provisioning/provisioner.py` -- current provision() sequence, constructor pattern, _update_state(), _poll_health() deadline pattern
- `inference_proxy/provisioning/state.py` -- ProvisioningStep enum definition
- `inference_proxy/redfish/client.py` -- RedfishClient.power_action() API, check-before-act + poll
- `inference_proxy/redfish/errors.py` -- RedfishError exception type
- `inference_proxy/config/settings.py` -- ProvisioningSettings, RedfishSettings patterns
- `inference_proxy/config/dependencies.py` -- get_redfish_client provider
- `inference_proxy/main.py` -- lifespan wiring, provisioner construction
- `tests/provisioning/test_provisioner.py` -- existing test patterns, `_make_provisioner()` helper
- `tests/conftest.py` -- DI override patterns, mock provisioner setup

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new packages, all internal
- Architecture: HIGH -- insertion point is obvious, all patterns verified in codebase
- Pitfalls: HIGH -- derived directly from codebase analysis

**Research date:** 2026-07-22
**Valid until:** 2026-08-22 (stable internal integration, no external dependency drift)
