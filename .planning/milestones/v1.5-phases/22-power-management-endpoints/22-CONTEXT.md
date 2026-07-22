# Phase 22: Power Management Endpoints - Context

**Gathered:** 2026-07-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Expose the RedfishClient (built in Phase 21) as admin API endpoints so operators can power on/off/restart servers and query power state. Two endpoints on the existing admin router: GET for power state, POST for power actions.

</domain>

<decisions>
## Implementation Decisions

### Node Identification
- **D-01:** Use bare hostname as URL path parameter (e.g., `/admin/nodes/{hostname}/power`)
- **D-02:** Apply `canonical_hostname()` normalization on the path parameter — same as setup endpoint
- **D-03:** Works on unprovisioned hosts — no etcd registration required for power operations

### Endpoint Structure
- **D-04:** Single resource model: GET `/admin/nodes/{hostname}/power` returns current power state, POST `/admin/nodes/{hostname}/power` with `{"action": "On"}` executes action
- **D-05:** POST response returns final state only: `{"hostname": "x", "power_state": "On"}` — synchronous, blocks until RedfishClient polling completes
- **D-06:** Expose Redfish actions directly: On, ForceOff, GracefulRestart, ForceRestart — no alias translation layer
- **D-07:** Return 503 when `get_redfish_client` yields None (Redfish not configured)

### Claude's Discretion
- Pydantic request/response model design (PowerActionRequest, PowerStateResponse)
- Error mapping from RedfishError to HTTP status codes (400/503/etc.)
- Whether to add power endpoints to existing `admin.py` or create a separate `power.py` router file (SOLID SRP consideration)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Admin API (primary analog)
- `inference_proxy/api/admin.py` — Current admin router with setup/teardown/nodes/metrics endpoints; new power endpoints integrate here
- `inference_proxy/models/admin.py` — Pydantic response models for admin API; add power models here or alongside

### Redfish Client (Phase 21 output)
- `inference_proxy/redfish/client.py` — RedfishClient with get_power_state() and power_action() methods
- `inference_proxy/redfish/errors.py` — RedfishError exception and extract_error_message()

### Dependency Injection
- `inference_proxy/config/dependencies.py` — `get_redfish_client` provider (returns RedfishClient | None)

### Hostname Utilities
- `inference_proxy/quads/client.py` — `canonical_hostname()` function for hostname normalization

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `RedfishClient.get_power_state(hostname)` — returns On/Off/PoweringOn/PoweringOff
- `RedfishClient.power_action(hostname, action)` — check-before-act + polling, returns final state
- `canonical_hostname()` — hostname normalization already used by setup endpoint
- `get_redfish_client` DI provider — returns None when unconfigured

### Established Patterns
- Admin endpoints use `Depends()` for DI injection
- Response models are frozen Pydantic BaseModel subclasses in `models/admin.py`
- Async background ops return 202 (setup/teardown), but power actions are fast enough for synchronous response
- `_ACTION_TARGET_STATE` dict in client validates allowed actions

### Integration Points
- `admin_router` in `inference_proxy/api/admin.py` — add power endpoints here
- `inference_proxy/models/admin.py` — add PowerActionRequest and PowerStateResponse models
- `inference_proxy/main.py` — no changes needed (admin_router already mounted)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches following the admin API analog.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 22-power-management-endpoints*
*Context gathered: 2026-07-22*
