# Feature Landscape

**Domain:** Redfish power management and provisioning failure diagnostics for an LLM inference proxy
**Researched:** 2026-07-21

## Existing Infrastructure (Already Built)

The provisioning system has the foundation these features plug into:

| Component | What It Does | New Features Build On |
|-----------|-------------|----------------------|
| `NodeProvisioner` | 16-step state machine (PENDING through COMPLETE/FAILED) with SSH orchestration | Auto-power-on inserts before PREFLIGHT; error capture enriches FAILED state |
| `ProvisioningState` | Frozen Pydantic model with `current_step`, `failed_step`, `error` fields stored in etcd | Step-level error capture extends the `error` field with structured detail |
| `ProvisioningStep` enum | StrEnum covering setup + teardown lifecycle | New `POWER_ON` step added before `PREFLIGHT` |
| Admin API (`/admin/nodes/setup`) | Triggers background provisioning, dedup guard, QUADS validation | Power actions get new endpoints; setup gains auto-power-on |
| Node detail page | Shows provisioning tasks table with step badge, status, error column | Error display shows richer failure detail |
| Dashboard main page | Node fleet table with state badges and action buttons | Inline error indicator for failed nodes; power actions in action buttons |
| `QUADSClient` | httpx-based async REST client pattern (injected `AsyncClient`, `base_url`) | Redfish client follows identical pattern |
| `Settings` / pydantic-settings | Nested config with `INFERENCE_PROXY_` env prefix | `RedfishSettings` sub-model for BMC credentials and defaults |

## Table Stakes

Features operators expect from power management on bare metal servers. Missing any of these makes Redfish integration feel incomplete.

| Feature | Why Expected | Complexity | Depends On |
|---------|-------------|------------|------------|
| Power on via Redfish | Cannot SSH into a powered-off server; must power on first | Medium | Redfish client, BMC credentials config |
| Power off via Redfish (ForceOff) | Operators need to shut down nodes cleanly or force-stop when SSH is unavailable | Low | Redfish client |
| Power restart via Redfish (GracefulRestart, ForceRestart) | Common ops action for hung servers; two modes match operator expectations | Low | Redfish client |
| Power status query | Know if server is On/Off/PoweringOn/PoweringOff before attempting operations | Low | Redfish client |
| Auto-power-on before provisioning | If server is off when setup is triggered, power it on automatically and wait for SSH | Medium | Power status query, power on, SSH readiness poll |
| Step-level error capture | Current `error` field is a single string; operators need to know exactly which step failed and why | Low | Existing `ProvisioningState` model extension |
| Dashboard error display for failed nodes | Main fleet table shows "failed" badge but no error detail; operators must click through to node detail | Low | `AdminNodeResponse` model extension, dashboard JS |

## Differentiators

Features that add operational polish. Not expected from a v1.5 internal tool, but valuable if cheap.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Power status in fleet table | See On/Off/PoweringOn per node without clicking through | Low | New column in dashboard table, one Redfish GET per node (or cached from last poll) |
| Power action buttons in dashboard | Power on/off/restart from the fleet table directly | Low | Extend `ACTION_CONFIG` and `_STATE_ACTIONS` with power actions |
| BMC reachability check | Verify BMC responds before attempting power operations; better error messages | Low | Single GET to `/redfish/v1/` before any action |
| Collapsible error detail on dashboard | Show truncated error inline, expand on click; avoids navigating to node detail page | Low | CSS + 2 lines of JS for toggle |
| Retry provisioning after power-on failure | If auto-power-on fails (BMC unreachable, wrong credentials), surface a clear "retry with power" action | Low | New action in `ACTION_CONFIG` |

## Anti-Features

Features to explicitly NOT build. Each adds complexity without proportional value for an internal ops tool.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Redfish session-based auth | Session management adds token lifecycle, renewal, cleanup. Basic auth is sufficient for internal BMC calls that happen infrequently (power ops are rare). | HTTP Basic auth on every Redfish request. Internal network, TLS to BMC, no session state to manage. |
| Per-host BMC credential storage | Database, encryption, credential management UI. Way beyond scope. | Single set of BMC credentials in env vars (`INFERENCE_PROXY_REDFISH__USERNAME`, `INFERENCE_PROXY_REDFISH__PASSWORD`). All QUADS lab BMCs use the same credentials. |
| Automatic System ID discovery from `/redfish/v1/Systems` | Multi-system BMCs exist but QUADS lab servers are single-system. Hypermedia walking adds complexity. | Default `system_id = "1"` in config. Override per-host if needed later. |
| IPMI fallback | Some older servers lack Redfish. Adds a second protocol path. | Redfish only. Servers without Redfish get manual power management. Flag as unsupported. |
| Continuous power state polling | Background thread polling BMCs for power state wastes BMC resources and adds load. | Query power state on-demand when dashboard loads or before provisioning. Cache briefly (30s TTL). |
| Chassis/thermal/fan monitoring | Redfish exposes far more than power state. Scope creep into full hardware monitoring. | Power state and reset actions only. Hardware monitoring is a separate product. |
| Firmware update via Redfish | Redfish `UpdateService` is a separate complex domain. | Out of scope. Firmware is managed through existing lab processes. |
| Provisioning log streaming to dashboard | WebSocket/SSE stream of provisioning output to the UI. Complex, adds persistent connections. | Poll `/admin/provisioning/tasks` as today. Error detail shows what failed. Full logs are in structlog output. |
| Error notification system (email/Slack) | Notification infrastructure for provisioning failures. | Toast notifications in dashboard UI. Operators are watching the dashboard. |

## Feature Dependencies

```
RedfishSettings (config)         -->  Redfish client (needs BMC URL pattern, credentials)
Redfish client                   -->  Power on / off / restart actions
Redfish client                   -->  Power status query
Power status query               -->  Auto-power-on (check if Off before powering on)
Auto-power-on                    -->  SSH readiness poll (wait for OS boot after power-on)
SSH readiness poll                -->  Existing preflight (TCP probe to port 22)

Step-level error capture          -->  ProvisioningState model (extend error field)
Step-level error capture          -->  NodeProvisioner._update_state (capture exception details)
AdminNodeResponse extension       -->  Dashboard error display (add error fields to API response)
Dashboard error display           -->  dashboard.js (render error inline in fleet table)
```

## Redfish API Details

### Standard Action URI

```
POST /redfish/v1/Systems/{system_id}/Actions/ComputerSystem.Reset
Content-Type: application/json
Authorization: Basic <base64(username:password)>

{"ResetType": "On"}
```

Where `{system_id}` is typically `"1"` for single-system BMCs (Dell iDRAC, HPE iLO) or `"system"` for OpenBMC. Configurable via `INFERENCE_PROXY_REDFISH__SYSTEM_ID`.

### ResetType Values (Use These Four)

| ResetType | When to Use | Current PowerState Must Be |
|-----------|-------------|---------------------------|
| `On` | Power on a server that is off | Off |
| `ForceOff` | Immediate power cut (like pulling the plug) | On |
| `GracefulRestart` | Clean OS shutdown then restart | On |
| `ForceRestart` | Immediate restart (power cycle, no OS shutdown) | On |

Other ResetType values exist (`GracefulShutdown`, `Nmi`, `ForceOn`, `PushPowerButton`, `PowerCycle`) but are not needed for this use case. `GracefulShutdown` is notable but the gateway already has SSH-based graceful teardown that does `podman stop` first.

### PowerState Values (Read-Only)

| PowerState | Meaning | Operator Action |
|------------|---------|-----------------|
| `On` | Server is powered on and running | Can SSH, can provision |
| `Off` | Server is powered off (BMC has AUX power) | Must power on before provisioning |
| `PoweringOn` | Transitioning to On (BIOS POST, etc.) | Wait; poll until On |
| `PoweringOff` | Transitioning to Off | Wait; poll until Off |

### Power Status Query

```
GET /redfish/v1/Systems/{system_id}
Authorization: Basic <base64(username:password)>

Response includes: {"PowerState": "On", ...}
```

### Error Responses from Redfish

| HTTP Status | Meaning | Retry? |
|-------------|---------|--------|
| 200/204 | Success | -- |
| 400 | Invalid ResetType for current state (e.g., `On` when already On) | No, check PowerState first |
| 401 | Bad credentials | No, fix config |
| 403 | Insufficient privilege | No, fix BMC account |
| 404 | Wrong system ID or path | No, fix config |
| 409 | Reset already in progress | Wait, then retry |
| 500 | BMC internal error | Retry once with backoff |
| 503 | BMC busy/overloaded | Retry with backoff |

Redfish returns extended error info in the response body:
```json
{
  "error": {
    "@Message.ExtendedInfo": [
      {
        "MessageId": "Base.1.0.ActionNotSupported",
        "Message": "The action ComputerSystem.Reset is not supported...",
        "Resolution": "..."
      }
    ]
  }
}
```

### BMC URL Pattern

BMC addresses are typically derived from the hostname. Common patterns in QUADS labs:
- `mgmt-{hostname}` (e.g., `mgmt-host01.example.com`)
- `{hostname}-drac` (Dell iDRAC convention)
- `{hostname}-ilo` (HPE iLO convention)

Configurable via `INFERENCE_PROXY_REDFISH__BMC_HOST_PATTERN` defaulting to `"mgmt-{hostname}"`. The `{hostname}` placeholder is replaced with the short hostname.

## Step-Level Error Capture Details

### Current State

The existing `ProvisioningState` model captures:
- `failed_step: str | None` -- the step name where failure occurred (e.g., `"RemoteCommandError"`, `"teardown"`)
- `error: str | None` -- the exception message string

Problems:
1. `failed_step` stores the exception class name, not the provisioning step name
2. `error` is a raw exception string, not structured for display
3. No distinction between transient errors (SSH timeout) and permanent errors (GPU not found)

### Proposed Enhancement

Capture the actual `ProvisioningStep` that was active when the failure occurred, plus a human-readable error summary:

```python
# In NodeProvisioner.provision(), the except block currently does:
await self._update_state(
    hostname, ProvisioningStep.FAILED,
    failed_step=type(exc).__name__,  # <-- exception class name
    error=str(exc),
)

# Change to:
await self._update_state(
    hostname, ProvisioningStep.FAILED,
    failed_step=current_step_name,  # <-- "nvidia_driver", "health_poll", etc.
    error=str(exc),
)
```

This is a minimal change -- track the current step name as a local variable and pass it to `_update_state` on failure. The `ProvisioningState` model already has the right fields; the provisioner just populates `failed_step` with the wrong value.

## Dashboard Error Display Details

### Current State

- **Fleet table (dashboard.html):** Shows state badge (`available`, `healthy`, `unhealthy`, `provisioning`, `failed`) but no error info. Operator must click through to node detail page.
- **Node detail page:** Shows provisioning tasks table with error column. Already renders `task.error` as red text.

### Proposed Enhancement

Add error info to the fleet table for failed nodes:

1. Extend `AdminNodeResponse` with optional `error` and `failed_step` fields
2. In `UnifiedNodeService._from_etcd()`, look up the provisioning task for the node and attach error info
3. In `dashboard.js`, render a small error summary below the state badge for failed nodes

UI pattern: Below the "failed" badge, show a truncated error line (e.g., "Failed at nvidia_driver: exit code 1"). No expand/collapse needed in v1 -- clicking the node ID already navigates to the detail page with full error text.

## MVP Recommendation

Build in this order -- each step is independently useful:

1. **Redfish client + config** -- `RedfishSettings` pydantic model, `RedfishClient` class with httpx Basic auth, power status query, reset action. Tests with `pytest-httpx` mocking.
2. **Admin API power endpoints** -- `POST /admin/nodes/{id}/power` with `action` body field. Returns 202.
3. **Auto-power-on in provisioning** -- Before PREFLIGHT, check power state. If Off, send `On`, poll until SSH port 22 reachable. New `POWER_ON` step in `ProvisioningStep`.
4. **Step-level error capture fix** -- Fix `failed_step` to use the actual provisioning step name instead of exception class name.
5. **Dashboard error display** -- Add `failed_step` and `error` to `AdminNodeResponse`, render inline in fleet table for failed nodes.
6. **Power action buttons in dashboard** -- Add power_on, power_off, power_restart to `ACTION_CONFIG` and `_STATE_ACTIONS`.

**Defer:** Power status column in fleet table (requires BMC calls per node on every poll), BMC reachability pre-check, collapsible error detail. Add when the core power flow works.

## Configuration Shape

```python
class RedfishSettings(BaseModel):
    """Redfish BMC configuration."""
    username: str = "root"
    password: str = ""
    bmc_host_pattern: str = "mgmt-{hostname}"
    system_id: str = "1"
    verify_ssl: bool = False  # Lab BMCs use self-signed certs
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    power_on_wait_timeout: int = 300  # 5 min for server to POST and boot
    power_on_poll_interval: int = 10
```

Env vars: `INFERENCE_PROXY_REDFISH__USERNAME`, `INFERENCE_PROXY_REDFISH__PASSWORD`, `INFERENCE_PROXY_REDFISH__BMC_HOST_PATTERN`, etc.

## Sources

- [DMTF Redfish Resource and Schema Guide (DSP2046)](https://www.dmtf.org/sites/default/files/standards/documents/DSP2046_2024.2.html) -- PowerState enum, ComputerSystem.Reset action, ResetType values
- [DMTF Redfish Specification (DSP0266)](http://redfish.dmtf.org/schemas/DSP0266_1.0.html) -- Action URI format, AllowableValues annotation, error response structure
- [Redfish Authentication and Sessions (HPE)](https://servermanagementportal.ext.hpe.com/docs/concepts/redfishauthentication) -- Basic auth vs session auth, X-Auth-Token flow
- [Redfish Error Responses (HPE)](https://servermanagementportal.ext.hpe.com/docs/concepts/errorresponses) -- Extended error info, MessageId, Resolution
- [NVIDIA DGX Redfish API Support](https://docs.nvidia.com/dgx/dgxh100-user-guide/redfish-api-supp.html) -- Reset action example, supported ResetType values
- [OpenBMC Redfish Cheatsheet](https://github.com/openbmc/docs/blob/master/REDFISH-cheatsheet.md) -- System ID conventions, power control examples
- [Redfish Protocol Overview (AI Infrastructure KB)](https://ai-infrastructure.net/redfish-protocol/) -- PowerState values, ComputerSystem resource
- [OpenStack Ironic Redfish Power Driver](https://docs.openstack.org/ironic/train/_modules/ironic/drivers/modules/redfish/power.html) -- PoweringOn/PoweringOff to On/Off mapping
- [Dell iDRAC Redfish Scripting](https://github.com/dell/iDRAC-Redfish-Scripting) -- Direct REST call patterns for power management
- [Sushy (OpenStack Redfish Library)](https://pypi.org/project/sushy/) -- Reference for Redfish client design, though we use httpx directly
- [Microsoft Entra Provisioning Logs](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/concept-provisioning-logs) -- Step-level provisioning status patterns (Success/Failure/Skipped)
- [Azure Monitoring Best Practices](https://learn.microsoft.com/en-us/azure/architecture/best-practices/monitoring) -- Multi-stage diagnostics pipeline pattern
