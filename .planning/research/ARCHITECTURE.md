# Architecture: Redfish Power Management & Provisioning Diagnostics (v1.5)

**Domain:** BMC power management integration into existing provisioning pipeline
**Researched:** 2026-07-21
**Overall confidence:** HIGH

## Decision: Direct httpx Calls to Redfish REST API

The Redfish API is a simple REST protocol. Power state is a GET returning a JSON field. Power actions are a POST with a `ResetType` body. That is the entire surface area needed.

The project already has httpx. Adding `python-redfish-library` or importing `badfish` (which uses aiohttp) would add a dependency for what amounts to two HTTP calls. Use httpx directly with basic auth, same as the QUADS client pattern.

**Why not Badfish as a library?** Badfish is the QUADS ecosystem's Redfish tool (same GitHub org). It uses aiohttp internally -- adding aiohttp as a transitive dependency violates the "zero new deps when httpx can do it" constraint established in v1.3. Badfish is also focused on boot order management; its power operations are a subset of its CLI. The gateway needs two Redfish calls total. Direct httpx is less code than wiring Badfish's factory pattern.

**Why not python-redfish-library?** It is synchronous (uses requests internally). The gateway is async-first. Wrapping sync calls in `asyncio.to_thread()` is workable (the etcd3gw precedent) but unnecessary complexity when httpx.AsyncClient handles this natively.

## Architecture Overview

```
                     +---------------------------------------------+
                     |            FastAPI Gateway                   |
                     |                                              |
                     |  provisioning/             redfish/          |
                     |    provisioner.py             client.py      |
                     |    (orchestrator)             (thin httpx    |
                     |         |                      wrapper)      |
                     |         |                         ^          |
                     |         +--- power_on_if_needed --+          |
                     |         |                                    |
                     |         +--- preflight (SSH) ----> ssh_client|
                     |         +--- setup.sh -----------> ssh_client|
                     |         +--- start-vllm.sh ------> ssh_client|
                     |         +--- health poll --------> httpx     |
                     |         +--- register -----------> etcd      |
                     |                                              |
                     |  api/admin.py                                |
                     |    POST /admin/nodes/{id}/power              |
                     |    GET  /admin/nodes/{id}/power              |
                     |         |                                    |
                     |         +-----> redfish/client.py            |
                     |                     |                        |
                     +---------------------|------------------------+
                                           |
                                    HTTPS (basic auth)
                                           |
                                    +------v------+
                                    |  BMC/iDRAC  |
                                    |  Redfish    |
                                    |  endpoint   |
                                    | mgmt-<host> |
                                    +-------------+
```

## New Components

| Component | Responsibility | Lives In | Communicates With |
|-----------|---------------|----------|-------------------|
| **RedfishClient** | GET power state, POST reset action | `inference_proxy/redfish/client.py` | BMC via httpx over HTTPS |
| **RedfishSettings** | BMC credentials, hostname template, timeouts | `inference_proxy/config/settings.py` (new sub-model) | Consumed by RedfishClient constructor |
| **Power admin endpoints** | HTTP API for manual power operations | `inference_proxy/api/admin.py` (new routes) | RedfishClient |
| **Power actions in dashboard** | UI buttons for power on/off/restart | `inference_proxy/static/js/dashboard.js` (ACTION_CONFIG additions) | `/admin/nodes/{id}/power` |

### Modified Components

| Component | Change | Why |
|-----------|--------|-----|
| `provisioner.py` | Add `_power_on_if_needed()` before preflight | Auto-power-on before SSH provisioning |
| `state.py` | Add `POWERING_ON` to ProvisioningStep enum | Track power-on step in provisioning state |
| `settings.py` | Add `RedfishSettings` sub-model to root `Settings` | BMC credentials and hostname pattern |
| `dependencies.py` | Add `get_redfish_client()` dependency provider | Inject RedfishClient into admin routes |
| `main.py` | Create RedfishClient in lifespan, store in app.state | Same lifecycle pattern as QUADSClient |
| `admin.py` | Add power action and power status endpoints | Expose power management to dashboard |
| `models/admin.py` | Add `PowerActionRequest`, `PowerStatusResponse` models | Request/response types for power endpoints |
| `dashboard.js` | Add `power_on`, `power_off`, `power_restart` to ACTION_CONFIG | Dashboard power action buttons |
| `unified_nodes.py` | Add power actions to `_STATE_ACTIONS` for `available` state | Nodes that are off can be powered on |
| `node_detail.js` | Show error details inline (already partially implemented) | Better error visibility |
| `dashboard.js` | Show last error on main dashboard node row | Inline error display without navigating to detail |

## RedfishClient Design

Follows the exact pattern of `QUADSClient`: thin httpx wrapper, constructor-injected AsyncClient, typed errors.

```python
class RedfishError(Exception):
    """Raised when Redfish API call fails."""

class RedfishClient:
    """Thin async wrapper around httpx for Redfish power operations.

    Constructor-injected httpx.AsyncClient (DIP). All BMCs share
    credentials (lab environment, same as SSH pattern).
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        settings: RedfishSettings,
    ) -> None:
        self._client = http_client
        self._username = settings.username
        self._password = settings.password
        self._bmc_template = settings.bmc_hostname_template
        self._system_id = settings.system_id

    def _bmc_url(self, hostname: str, path: str) -> str:
        bmc_host = self._bmc_template.format(hostname=hostname)
        return f"https://{bmc_host}/redfish/v1/Systems/{self._system_id}{path}"

    async def get_power_state(self, hostname: str) -> str:
        """Return PowerState (On, Off, PoweringOn, PoweringOff)."""
        url = self._bmc_url(hostname, "")
        resp = await self._client.get(
            url, auth=(self._username, self._password)
        )
        resp.raise_for_status()
        return resp.json()["PowerState"]

    async def reset(self, hostname: str, reset_type: str) -> None:
        """POST ComputerSystem.Reset action."""
        url = self._bmc_url(hostname, "/Actions/ComputerSystem.Reset")
        resp = await self._client.post(
            url,
            json={"ResetType": reset_type},
            auth=(self._username, self._password),
        )
        resp.raise_for_status()
```

**BMC hostname derivation:** QUADS uses `mgmt-<hostname>` convention. Configurable via `bmc_hostname_template` setting with `{hostname}` placeholder, default `"mgmt-{hostname}"`. This handles the common case and lets operators override for non-standard environments.

**System ID:** Most vendors use `/redfish/v1/Systems/1` but Dell uses `System.Embedded.1` and others vary. Configurable via `system_id` setting, default `"1"`. All lab servers are typically the same vendor, so one setting covers the fleet.

**SSL verification:** BMCs use self-signed certs. The httpx.AsyncClient is created with `verify=False` (same as typical Redfish tooling). Scoped to the Redfish client's httpx instance -- the proxy client and QUADS client keep their own SSL settings.

## RedfishSettings Design

```python
class RedfishSettings(BaseModel):
    """Redfish BMC configuration.

    When ``username`` is ``None`` (the default), Redfish features are
    disabled. Setting it via ``INFERENCE_PROXY_REDFISH__USERNAME``
    activates the integration. Same opt-in pattern as QUADSSettings.
    """

    username: str | None = None
    password: str | None = None
    bmc_hostname_template: str = "mgmt-{hostname}"
    system_id: str = "1"
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    power_on_wait: int = 120  # seconds to wait for power on before preflight
    power_on_poll_interval: int = 5  # seconds between power state polls
```

**Opt-in pattern:** When `username` is None, Redfish is disabled. The provisioner skips the power-on step. The admin power endpoints return 503 ("Redfish not configured"). Matches the QUADS opt-in pattern (`base_url: str | None = None`).

**Credentials via env vars:** `INFERENCE_PROXY_REDFISH__USERNAME` and `INFERENCE_PROXY_REDFISH__PASSWORD`. Environment variables, not config files -- the existing pydantic-settings pattern handles this. Operators already set `INFERENCE_PROXY_QUADS__BASE_URL` the same way.

## Provisioner Integration: Auto-Power-On

The provisioning sequence gains one new step at the front:

```
PENDING -> POWERING_ON (new) -> PREFLIGHT -> UPLOADING_SCRIPTS -> ... -> COMPLETE
```

Implementation in `provisioner.py`:

```python
async def _power_on_if_needed(
    self, hostname: str, redfish: RedfishClient | None
) -> None:
    """Check power state; if off, power on and wait."""
    if redfish is None:
        return  # Redfish not configured, skip

    try:
        state = await redfish.get_power_state(hostname)
    except Exception:
        logger.warning("redfish_power_check_failed", hostname=hostname)
        return  # Best-effort: proceed to SSH preflight, which will fail
                # if the machine is actually off

    if state == "On":
        return  # Already on

    await self._update_state(hostname, ProvisioningStep.POWERING_ON)
    await redfish.reset(hostname, "On")

    # Poll until On or timeout
    deadline = asyncio.get_running_loop().time() + self._settings.power_on_wait
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(self._settings.power_on_poll_interval)
        try:
            state = await redfish.get_power_state(hostname)
            if state == "On":
                return
        except Exception:
            pass  # BMC may be temporarily unresponsive during power-on
    raise ProvisioningError(
        f"Timed out waiting for {hostname} to power on"
    )
```

**Best-effort semantics:** If Redfish is not configured or the BMC is unreachable, provisioning proceeds to SSH preflight. The preflight TCP probe (port 22) will fail if the machine is actually off, giving a clear error. This avoids making Redfish a hard dependency of provisioning.

**Constructor change:** `NodeProvisioner.__init__` gains an optional `redfish_client: RedfishClient | None = None` parameter. Injected in `main.py` lifespan, same as all other dependencies.

## Admin API: Power Endpoints

Two new routes in `admin.py`:

```
GET  /admin/nodes/{node_id}/power   -> PowerStatusResponse
POST /admin/nodes/{node_id}/power   -> PowerActionResponse (202)
```

### GET Power Status

Returns the current Redfish power state for any known host. Does not require the node to be registered in etcd (useful for checking if an available QUADS host is powered on before setup).

```python
class PowerStatusResponse(BaseModel):
    hostname: str
    power_state: str  # On, Off, PoweringOn, PoweringOff
```

### POST Power Action

Triggers a Redfish reset action. Accepts a `ResetType` from the supported set.

```python
class PowerActionRequest(BaseModel):
    reset_type: str  # On, ForceOff, GracefulRestart, ForceRestart

class PowerActionResponse(BaseModel):
    hostname: str
    reset_type: str
    status: str  # "accepted"
```

**Validation:** The endpoint validates `reset_type` against `{"On", "ForceOff", "GracefulRestart", "ForceRestart"}`. The Redfish spec defines more reset types but these four cover the use cases in PROJECT.md.

**Not async background:** Unlike provisioning, power actions are fire-and-forget POST to the BMC. The Redfish POST returns quickly (the BMC handles the actual power sequence). No need for `fire_background()`.

## Provisioning Error Capture Enhancement

### Current State

The existing `ProvisioningState` model already has `failed_step: str | None` and `error: str | None`. The provisioner populates these when exceptions occur. The node_detail.js already renders error text.

### Gap

The error messages are exception `str()` representations, which are sometimes terse (e.g., `"Command 'bash auto-vllm-container/setup.sh' on host1 exited with status 1"`). No stderr capture, no structured detail.

### Enhancement: Capture stderr in error field

When `RemoteCommandError` is raised during `_run_setup()`, the error message does not include stderr (stderr is logged but not stored). The fix is to capture the last N lines of stderr output during step execution and include them in the error field written to etcd.

```python
# In provisioner.py _run_setup method:
stderr_lines: list[str] = []
async for stream, line in self._ssh_client.run_streaming(
    hostname, "bash auto-vllm-container/setup.sh"
):
    if stream == "stdout":
        # ... existing step marker parsing ...
    else:
        stderr_lines.append(line)
        logger.warning("setup_stderr", line=line, hostname=hostname)

# On exception, include stderr context:
# error = f"{exc}\nstderr: {chr(10).join(stderr_lines[-10:])}"
```

**Bounded:** Only last 10 stderr lines stored to keep etcd values reasonable. This is diagnostic context, not a full log.

### Enhancement: Failed step name precision

Currently `failed_step` is set to the exception class name (`"RemoteCommandError"`, `"SSHConnectionError"`). Change to the actual provisioning step name that was active when the failure occurred (`"uploading_scripts"`, `"nvidia_driver"`, etc.). This is more useful for operators.

The provisioner already tracks which step it is in via `_update_state()`. Capture the last step name and use it as `failed_step` instead of the exception class name.

### Dashboard: Inline error on main node list

The main dashboard (`dashboard.js`) does not show errors -- operators must click through to node_detail to see failure details. Add a column or tooltip showing the last error for nodes in `failed` state.

Implementation: The `/admin/provisioning/tasks` endpoint already returns error data. The dashboard refresh can fetch tasks alongside nodes and merge the last error for each hostname into the node row display.

Alternatively, add `last_error: str | None` to `AdminNodeResponse` and populate it in `UnifiedNodeService` by checking provisioning tasks in etcd. This keeps the dashboard fetch simple (one endpoint).

**Recommendation:** Add `last_error` to `AdminNodeResponse`. The unified node service already merges data from multiple sources. Adding provisioning task error lookup is a natural extension. The dashboard just renders it.

## Data Flow: Power On + Provision

```
Operator clicks "Setup" on dashboard
         |
         v
POST /admin/nodes/setup  {hostname: "host1.lab.example.com"}
         |
         v
provisioner.provision("host1.lab.example.com")
         |
         +-- _power_on_if_needed(hostname, redfish_client)
         |       |
         |       +-- GET https://mgmt-host1.lab.example.com/redfish/v1/Systems/1
         |       |   -> PowerState: "Off"
         |       |
         |       +-- POST https://mgmt-host1.lab.example.com/redfish/v1/Systems/1/Actions/ComputerSystem.Reset
         |       |   body: {"ResetType": "On"}
         |       |
         |       +-- Poll GET .../Systems/1  every 5s for up to 120s
         |       |   -> PowerState: "On"
         |       |
         +-- preflight(hostname)
         |       |
         |       +-- TCP probe port 22 (SSH reachability)
         |       +-- SSH: nvidia-smi (GPU check)
         |       +-- SSH: df (disk check)
         |
         +-- [... existing provisioning steps ...]
```

## Data Flow: Manual Power Action from Dashboard

```
Operator clicks "Power Off" on a healthy node
         |
         v
POST /admin/nodes/host1.lab.example.com/power  {reset_type: "ForceOff"}
         |
         v
admin.py route handler
         |
         +-- redfish_client.reset("host1.lab.example.com", "ForceOff")
         |       |
         |       +-- POST https://mgmt-host1.lab.example.com/.../ComputerSystem.Reset
         |       |   body: {"ResetType": "ForceOff"}
         |       |   <- 200/204 OK
         |       |
         +-- return PowerActionResponse(status="accepted")
```

## Data Flow: Error Display

```
Provisioning fails at nvidia_driver step
         |
         v
provisioner._run_setup() catches RemoteCommandError
         |
         +-- _update_state(hostname, FAILED,
         |       failed_step="nvidia_driver",
         |       error="Command exited with status 1\nstderr: E: nvidia-driver not found...")
         |
         +-- etcd key /provisioning/host1 updated
         |
Dashboard polls /admin/nodes (includes last_error from provisioning tasks)
         |
         v
Node row shows:  [host1] [NVIDIA] [A100] [—] [failed] [nvidia_driver: nvidia-driver not found...]
                                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                                        inline error text, truncated with tooltip
```

## Component Boundaries

### redfish/client.py

Single responsibility: translate hostname + action into Redfish HTTP calls. Does not know about provisioning, etcd, or dashboard. Injected into provisioner and admin routes independently.

- Depends on: httpx, RedfishSettings
- Depended on by: NodeProvisioner, admin power endpoints
- Does NOT depend on: NodeRegistry, etcd, SSHClient, ProvisioningState

### provisioner.py (modified)

Gains `redfish_client` as an optional constructor parameter. The `provision()` method calls `_power_on_if_needed()` as the first step. If Redfish is None, the step is skipped.

- New dependency: RedfishClient (optional, via constructor)
- No change to: SSHClient, EtcdClient, ProvisioningSettings dependencies

### admin.py (modified)

Gains two new routes for power management. The routes use `get_redfish_client()` dependency injection, returning 503 if Redfish is not configured.

### unified_nodes.py (modified)

`_STATE_ACTIONS` extended: nodes in `available` state gain a `power_on` action. Nodes in `healthy`/`unhealthy` state gain `power_off` and `power_restart` actions alongside existing teardown/retry. The `failed` state shows the error.

## ProvisioningStep Enum Update

```python
class ProvisioningStep(StrEnum):
    PENDING = "pending"
    POWERING_ON = "powering_on"    # NEW
    PREFLIGHT = "preflight"
    UPLOADING_SCRIPTS = "uploading_scripts"
    # ... rest unchanged ...
```

One new member. No existing members removed or renamed. Backward compatible with existing etcd data.

## File Layout

```
inference_proxy/
    redfish/
        __init__.py              # NEW
        client.py                # NEW: RedfishClient (thin httpx wrapper)
    config/
        settings.py              # MODIFY: add RedfishSettings sub-model
        dependencies.py          # MODIFY: add get_redfish_client()
    provisioning/
        provisioner.py           # MODIFY: add _power_on_if_needed(), improve error capture
        state.py                 # MODIFY: add POWERING_ON step
    api/
        admin.py                 # MODIFY: add power action/status endpoints
    models/
        admin.py                 # MODIFY: add PowerActionRequest, PowerStatusResponse, PowerActionResponse
    services/
        unified_nodes.py         # MODIFY: add power actions, last_error field
    static/
        js/
            dashboard.js         # MODIFY: add power actions to ACTION_CONFIG, inline error display
            node_detail.js       # MODIFY: (minor) error display improvements
    templates/
        dashboard.html           # MODIFY: (minor) add error column to node table
tests/
    redfish/
        __init__.py              # NEW
        test_client.py           # NEW
    provisioning/
        test_provisioner.py      # MODIFY: test power-on-if-needed flow
        test_state.py            # MODIFY: test POWERING_ON member
    api/
        test_admin.py            # MODIFY: test power endpoints
    services/
        test_unified_nodes.py    # MODIFY: test power actions in state map
```

New files: 3 production (`redfish/__init__.py`, `redfish/client.py`) + 2 test.
Modified files: 10 production + 4 test.

## Build Order (Suggested Phase Structure)

Based on dependency analysis, bottom-up:

### Phase 1: RedfishClient + Settings + Tests

- `RedfishSettings` sub-model in `settings.py`
- `redfish/client.py` with `get_power_state()` and `reset()`
- `tests/redfish/test_client.py` (mock httpx responses with pytest-httpx)
- Wire into `main.py` lifespan (create client if configured, store in app.state)
- `dependencies.py`: add `get_redfish_client()`

**Deliverable:** RedfishClient exists, is tested, is injected. Nothing uses it yet.
**Why first:** Zero dependencies on other v1.5 work. Foundation for everything else.

### Phase 2: Admin Power Endpoints

- `PowerActionRequest`, `PowerStatusResponse`, `PowerActionResponse` in `models/admin.py`
- `GET /admin/nodes/{id}/power` and `POST /admin/nodes/{id}/power` in `admin.py`
- Tests for power endpoints
- Dashboard ACTION_CONFIG additions for power actions
- `_STATE_ACTIONS` updates in `unified_nodes.py`

**Deliverable:** Operators can check power state and trigger power on/off/restart from dashboard.
**Why second:** Depends on RedfishClient from Phase 1. Independent of provisioning changes.

### Phase 3: Auto-Power-On in Provisioner

- Add `POWERING_ON` to `ProvisioningStep`
- Add `redfish_client` parameter to `NodeProvisioner.__init__`
- Implement `_power_on_if_needed()` in provisioner
- Call it as first step in `provision()`
- Update `main.py` to pass redfish_client to provisioner
- Tests

**Deliverable:** Setup button auto-powers-on machines before SSH provisioning.
**Why third:** Depends on RedfishClient (Phase 1). Modifies provisioner behavior.

### Phase 4: Provisioning Error Diagnostics

- Improve error capture in provisioner (stderr context, precise step names)
- Add `last_error` field to `AdminNodeResponse`
- Populate `last_error` in `UnifiedNodeService`
- Dashboard inline error display for failed nodes
- Tests

**Deliverable:** Operators see failure details directly on dashboard without clicking through.
**Why last:** Independent of Redfish (could be reordered), but grouping with v1.5 makes sense. Benefits from the POWERING_ON step existing (tests can verify error display for power failures too).

## Patterns to Follow

### Pattern: Thin Client Wrapper (QUADSClient precedent)

`RedfishClient` follows the exact shape of `QUADSClient`: constructor takes an httpx.AsyncClient and settings, methods do one HTTP call each, all errors wrapped in `RedfishError`. No business logic in the client -- the provisioner and admin routes own the orchestration.

### Pattern: Optional Feature via None Settings (QUADSSettings precedent)

`RedfishSettings.username is None` means Redfish is disabled. The lifespan creates `app.state.redfish_client = None`. The provisioner skips power-on. The admin endpoint returns 503. No feature flags, no booleans -- the None pattern already works for QUADS.

### Pattern: Same httpx Instance Lifecycle (QUADS httpx precedent)

A dedicated `httpx.AsyncClient` for Redfish, created in lifespan, closed on shutdown. Separate from the proxy client and QUADS client. Each has its own timeout and SSL settings.

## Anti-Patterns to Avoid

### Anti-Pattern: Importing Badfish

**What:** `from badfish.main import badfish_factory` to reuse QUADS ecosystem tooling.
**Why bad:** Adds aiohttp as a transitive dependency. Badfish is CLI-oriented with a heavy factory pattern. The gateway needs two HTTP calls. The coupling to Badfish's release cycle is not worth it.
**Instead:** Direct httpx calls. Two methods, ~30 lines total.

### Anti-Pattern: Session-Based Redfish Auth

**What:** Create a Redfish session (POST to SessionService), cache X-Auth-Token, manage session lifecycle.
**Why bad:** BMCs have low session limits (often 4-8). Session management adds cleanup complexity. The gateway makes infrequent power calls -- not a high-throughput scenario.
**Instead:** Basic auth per request. Simple, stateless, no session leak risk. BMCs handle basic auth without session count pressure.

### Anti-Pattern: Polling BMC Power State Continuously

**What:** Background thread polling every BMC for power state, like the health checker polls vLLM /health.
**Why bad:** BMCs are slow. N hosts * frequent polls = timeout cascade on the management network. Power state changes are rare and operator-initiated.
**Instead:** Query power state on demand (when dashboard loads, when provisioning starts). No background polling.

### Anti-Pattern: Storing BMC Credentials in etcd

**What:** Per-host BMC credentials in etcd alongside node registration.
**Why bad:** etcd is not a secrets store. Credentials would be visible via etcd API. Lab servers share credentials anyway.
**Instead:** Environment variables via pydantic-settings. Same as SSH key path.

## Sources

- [DMTF Redfish python-redfish-library](https://github.com/DMTF/python-redfish-library) - HIGH confidence
- [DMTF Redfish Tacklebox (power reset types)](https://github.com/DMTF/Redfish-Tacklebox/blob/main/docs/rf_power_reset.md) - HIGH confidence
- [OpenBMC Redfish Cheatsheet](https://github.com/openbmc/docs/blob/master/REDFISH-cheatsheet.md) - HIGH confidence
- [QUADS Badfish (quadsproject Redfish tool)](https://github.com/quadsproject/badfish) - HIGH confidence
- [Advantech Redfish Power Operations](https://advantech-ncg.zendesk.com/hc/en-us/articles/44142031579417) - MEDIUM confidence
- [Dell iDRAC Redfish API Guide](https://www.dell.com/support/manuals/en-us/idrac7-8-lifecycle-controller-v2.40.40.40/redfish%202.40.40.40/power) - MEDIUM confidence
- [HPE Redfish Authentication](https://servermanagementportal.ext.hpe.com/docs/concepts/redfishauthentication) - MEDIUM confidence
- Existing codebase: `inference_proxy/` source files - HIGH confidence
