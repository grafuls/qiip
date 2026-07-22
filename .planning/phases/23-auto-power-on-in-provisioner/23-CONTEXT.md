# Phase 23: Auto-Power-On in Provisioner - Context

**Gathered:** 2026-07-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Insert automatic Redfish power-on into the provisioning sequence so offline servers get powered up before SSH provisioning begins. Add a POWERING_ON step visible in the dashboard and a dedicated SSH wait loop for cold-boot servers.

</domain>

<decisions>
## Implementation Decisions

### Redfish-Unconfigured Behavior
- **D-01:** When RedfishClient is None (not configured), skip the power-on step entirely and proceed directly to preflight — backward-compatible with existing deployments
- **D-02:** Log skip at INFO level: "redfish_not_configured, skipping power check"

### Boot Wait Strategy
- **D-03:** Add a dedicated SSH wait loop (TCP probe retries) before preflight, separate from the existing single-probe preflight check — clean separation of concerns (SRP)
- **D-04:** Single `POWERING_ON` dashboard step covers the entire boot sequence (Redfish power action + SSH wait loop) — operators see "powering on" until SSH is ready
- **D-05:** Default boot wait timeout: 300 seconds (5 minutes), configurable via ProvisioningSettings — covers most cold boots with margin

### Power-On Failure Handling
- **D-06:** Best-effort power-on: if Redfish power action fails (BMC unreachable, timeout, bad credentials), log warning and continue to preflight — server might already be on
- **D-07:** Still show POWERING_ON step in dashboard before transitioning to PREFLIGHT on failure — operator sees the attempt was made

### Claude's Discretion
- SSH wait loop probe interval (e.g., 5-10s between TCP probes)
- Whether to add `boot_wait_timeout` and `boot_wait_interval` as new ProvisioningSettings fields or reuse existing patterns
- Whether `_power_on_if_needed()` is a private method on NodeProvisioner or a standalone helper
- Test structure for the new power-on logic

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provisioning (primary integration target)
- `inference_proxy/provisioning/provisioner.py` — NodeProvisioner with `provision()` method; insert power-on before PREFLIGHT step
- `inference_proxy/provisioning/state.py` — ProvisioningStep enum; add POWERING_ON member

### Redfish Client (Phase 21 output)
- `inference_proxy/redfish/client.py` — RedfishClient with `get_power_state()` and `power_action()` methods
- `inference_proxy/redfish/errors.py` — RedfishError exception for catch-and-continue pattern

### Dependency Injection
- `inference_proxy/config/dependencies.py` — `get_redfish_client` provider (returns RedfishClient | None)
- `inference_proxy/config/settings.py` — ProvisioningSettings for boot wait timeout/interval config

### Application Wiring
- `inference_proxy/main.py` — Lifespan: pass RedfishClient to NodeProvisioner constructor

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `RedfishClient.get_power_state(hostname)` — returns On/Off/PoweringOn/PoweringOff
- `RedfishClient.power_action(hostname, "On")` — check-before-act + poll until "On" confirmed, returns final state
- `ProvisioningStep` StrEnum — add POWERING_ON member; dashboard renders steps dynamically
- `NodeProvisioner._update_state()` — writes step state to etcd for dashboard visibility

### Established Patterns
- Constructor injection: NodeProvisioner accepts SSHClient, EtcdClient, ProvisioningSettings — add optional RedfishClient parameter
- Optional features via None: `RedfishClient | None = None` parameter, skip when None (mirrors QUADSClient pattern)
- TCP probe pattern in preflight: `asyncio.open_connection(hostname, 22)` with timeout — reuse for SSH wait loop
- Best-effort etcd writes: `_update_state()` catches exceptions and logs warnings

### Integration Points
- `NodeProvisioner.__init__()` — add `redfish_client: RedfishClient | None = None` parameter
- `NodeProvisioner.provision()` — insert power-on block between PENDING and PREFLIGHT steps
- `ProvisioningStep` enum — add POWERING_ON before PREFLIGHT
- `inference_proxy/main.py` lifespan — pass `redfish_client` from `app.state` to provisioner constructor

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches following the provisioner's existing patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 23-auto-power-on-in-provisioner*
*Context gathered: 2026-07-22*
