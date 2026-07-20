# Phase 17: Unified Node List and Admin API - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Admin API returns a single merged view of all systems — QUADS-discovered GPU hosts joined with etcd-registered nodes by hostname — with computed states, available actions, and a duplicate-setup guard. A new UnifiedNodeService class owns the merge logic. No dashboard UI changes (Phase 18). This phase delivers the API contract the dashboard will consume.

</domain>

<decisions>
## Implementation Decisions

### Merge Strategy
- **D-01:** Merge logic lives in a new `UnifiedNodeService` class (e.g. `services/unified_nodes.py`). Takes QUADSPoller, NodeRegistry, CircuitBreakerRegistry, and ConnectionTracker as injected dependencies. Returns the merged node list.
- **D-02:** Hostname matching uses direct string comparison — QUADS hostnames and etcd node_ids are both short hostnames. No `canonical_hostname()` normalization at merge time.
- **D-03:** Nodes that exist in etcd but do NOT appear in the QUADS host list are excluded from the unified list. Only nodes present in at least one QUADS source appear.
- **D-04:** Extend the existing `AdminNodeResponse` model with optional QUADS fields (gpu_vendor, gpu_model, state, actions) rather than creating a new response model. Keeps one model, dashboard (Phase 18) consumes the extended version.

### State Computation
- **D-05:** Etcd status wins when a host is present in both sources. If hostname is in etcd, use the etcd status (healthy, unhealthy, provisioning, draining). If only in QUADS and available, state is "available". If in QUADS but not available and not in etcd, skip it.
- **D-06:** Server returns an `actions` list per node in the API response. Dashboard renders what the server says — single source of truth for action-to-state mapping.
- **D-07:** Action mapping: available → ["setup"], healthy → ["teardown"], unhealthy → ["teardown", "retry"], provisioning → ["cancel"], draining → ["force_teardown"].

### Duplicate Guard
- **D-08:** Pending hosts guard is a module-level set in the admin endpoint module (`api/admin.py`). Add hostname on setup fire, remove on task completion/failure.
- **D-09:** Guard only blocks in-flight provisioning (pending set). Hosts already in etcd (healthy/unhealthy) can still receive setup requests — re-provisioning is the operator's decision.

### QUADS Re-validation
- **D-10:** Setup endpoint calls `QUADSClient.get_available()` directly at request time for live validation (NODES-05). QUADSClient injected via Depends, not through the poller.
- **D-11:** If QUADS is unreachable at setup time, reject with 503 Service Unavailable. Never provision a host whose availability can't be verified.

### Claude's Discretion
- Module placement for UnifiedNodeService (under `services/` or within `quads/` or `api/`)
- Exact field naming for new AdminNodeResponse fields
- How the pending set cleanup callback is wired to fire_background task completion
- Whether to add a DI provider for UnifiedNodeService or construct inline

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### QUADS Integration (data sources)
- `inference_proxy/quads/poller.py` — QUADSPoller with `.hosts` and `.available_hostnames` cached properties
- `inference_proxy/quads/client.py` — QUADSClient with `get_hosts()`, `get_available()`, `QUADSConnectionError`, `canonical_hostname()`
- `inference_proxy/models/quads.py` — QUADSHost model (hostname, gpu_vendor, gpu_model, gpu_count)

### Admin API (what gets modified)
- `inference_proxy/api/admin.py` — Current admin endpoints: GET /admin/nodes, POST /admin/nodes/setup, DELETE /admin/nodes/{node_id}
- `inference_proxy/models/admin.py` — AdminNodeResponse, SetupRequest, SetupResponse, TeardownResponse, TaskStatusResponse

### Node Registry & State (etcd side)
- `inference_proxy/discovery/registry.py` — NodeRegistry with get_all(), get(), thread-safe
- `inference_proxy/models/node.py` — Node model, NodeStatus enum (HEALTHY, UNHEALTHY, PROVISIONING, DRAINING)
- `inference_proxy/resilience/circuit_breaker.py` — CircuitBreakerRegistry for per-node breaker state
- `inference_proxy/routing/connection_tracker.py` — ConnectionTracker for active connection counts

### Provisioning (setup/teardown operations)
- `inference_proxy/provisioning/provisioner.py` — NodeProvisioner with provision(), teardown(), fire_background(), preflight()

### DI & Configuration
- `inference_proxy/config/dependencies.py` — DI providers (get_registry, get_provisioner, get_quads_poller, etc.)
- `inference_proxy/config/settings.py` — QUADSSettings with base_url, timeout, poll_interval
- `inference_proxy/main.py` — Lifespan startup/shutdown, app.state service registration

### Project Context
- `.planning/ROADMAP.md` — Phase 17 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — NODES-01 through NODES-05 requirement definitions
- `.planning/phases/15-quads-client-and-models/15-CONTEXT.md` — QUADS client decisions (D-01 through D-11)
- `.planning/phases/16-background-polling/16-CONTEXT.md` — Poller decisions (D-01 through D-08)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `QUADSPoller.hosts` — cached list of QUADSHost objects with GPU info
- `QUADSPoller.available_hostnames` — cached list of available hostname strings
- `NodeRegistry.get_all()` — all etcd-registered nodes
- `NodeProvisioner.fire_background()` — schedules async task with GC-safe tracking
- `CircuitBreakerRegistry.get(node_id)` — per-node circuit breaker state
- `ConnectionTracker.get(node_id)` — active connection count per node

### Established Patterns
- DI via `config/dependencies.py` + `Depends()` in FastAPI routes
- Frozen Pydantic models with `ConfigDict(frozen=True)` for response objects
- Package-per-domain structure (`quads/`, `discovery/`, `provisioning/`, `resilience/`)
- structlog bound loggers for all logging
- `asyncio.to_thread()` for wrapping sync etcd3gw calls

### Integration Points
- `api/admin.py` — modify GET /admin/nodes to use UnifiedNodeService, modify POST setup to add dedup + re-validation
- `config/dependencies.py` — add get_quads_client() DI provider for setup re-validation
- `models/admin.py` — extend AdminNodeResponse with state, actions, gpu_vendor, gpu_model fields

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 17-Unified Node List and Admin API*
*Context gathered: 2026-07-16*
