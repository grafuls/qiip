# Project Research Summary

**Project:** QUADS LLM Inference Proxy -- v1.3 QUADS Integration
**Domain:** QUADS REST API integration for GPU host discovery and unified node management
**Researched:** 2026-07-15
**Confidence:** HIGH

## Executive Summary

v1.3 integrates the QUADS bare-metal lab management API into the existing inference gateway to provide a unified view of all GPU hosts -- both those already provisioned with vLLM (tracked in etcd) and those available in the lab (tracked in QUADS). The integration is read-only: the gateway polls QUADS for host inventory and availability, merges that data with etcd-registered nodes at request time, and presents a single table with inline Setup/Teardown actions. Zero new dependencies are needed. The existing stack (httpx, Pydantic, structlog, Jinja2, pydantic-settings) covers every requirement.

The recommended approach is a new `inference_proxy/quads/` package containing a thin httpx-based QUADS API client and a background asyncio.Task poller that caches host data in memory. The admin API merges QUADS hosts with etcd nodes via a pure function, and the dashboard renders one unified table with state-driven action buttons. The merge key is hostname. The setup form is removed in favor of inline buttons, but a manual hostname input is retained as a fallback for QUADS outages. Total estimated scope is 525-850 new LOC across 4 new files and 5 modified files -- comparable to v1.1 (dashboard), not v1.2 (provisioning).

The primary risks are: (1) a race condition between clicking "Setup" and the host appearing in etcd -- during the gap, duplicate setups can fire; (2) stale QUADS cache leading operators to provision hosts that were just assigned to another team; (3) hostname format mismatch between QUADS (FQDN) and etcd (short name) causing duplicate entries in the merged view; (4) QUADS API unavailability degrading the entire dashboard. All are preventable with specific patterns detailed in this summary.

## Key Findings

### Recommended Stack

No new dependencies. The existing stack handles everything.

**Reused (zero additions):**
- **httpx** (sync Client in thread or AsyncClient in task) -- HTTP calls to QUADS REST API, same pattern as health checker
- **Pydantic v2** -- `QUADSHost` model for parsing QUADS JSON responses, `UnifiedNodeResponse` for merged API output
- **pydantic-settings** -- `QUADSSettings` sub-model (base_url, poll_interval, enabled)
- **structlog** -- log QUADS poll timing, failures, host counts
- **Jinja2 + vanilla JS** -- extend existing dashboard, no build step

**What NOT to add:**
- `quads` pip package (pulls Flask + SQLAlchemy for 2 GET endpoints)
- `requests` (httpx already installed)
- APScheduler/schedule (4 lines of `while/sleep` suffice)
- tenacity (failed poll retries on next cycle anyway)
- cachetools (in-memory dict IS the cache)
- WebSocket/SSE libs (JS polling already works)

### QUADS API Reference

All GET endpoints are **unauthenticated** (verified against QUADS blueprints source). Write endpoints use `@check_access` but we only read.

| Endpoint | Returns | Purpose |
|----------|---------|---------|
| `GET /api/v3/hosts` | `list[HostDict]` | All hosts with model, cloud, processors, broken/retired |
| `GET /api/v3/hosts?model={m}` | `list[HostDict]` | Filter by hardware model |
| `GET /api/v3/available` | `list[str]` | Hostnames currently available (no active schedule) |
| `GET /api/v3/schedules/current` | Schedule list | Current assignments (for tooltip info, deferred) |

GPU hosts identified by `processors` array containing entries with `processor_type == "GPU"`. Host availability determined by presence in `/available` response or by `cloud.name == default_cloud.name` (spare pool).

### Expected Features

**Must have (table stakes):**
- QUADS API client module (httpx, 3-4 endpoints, read-only)
- Background polling of QUADS on configurable interval
- Unified node list merging QUADS hosts + etcd nodes by hostname
- GPU indicator per host (vendor + product from processors)
- Host availability status from QUADS
- Inline "Setup" button for available GPU hosts
- Inline "Teardown" button for provisioned nodes
- QUADS base URL + poll interval configuration
- Remove standalone setup form (replace with inline actions)

**Should have (differentiators):**
- State-based action buttons (available->Setup, healthy->Teardown, provisioning->disabled)
- Hardware summary inline (GPU model, memory)
- Visual status grouping/sorting
- Filter/search in node list

**Defer (v2+):**
- Cloud/assignment tooltip details (extra API call, low-value info)
- Write operations to QUADS API (we are a consumer, not admin)
- Auto-provisioning of available hosts (dangerous scope creep)
- Per-host detail pages (inline info suffices)
- Real-time QUADS sync (QUADS has no push mechanism)

### Architecture Approach

New `inference_proxy/quads/` package with `QUADSClient` (stateless async HTTP) and `QUADSPoller` (asyncio.Task caching results in memory). The merge happens at read time in the admin endpoint via a pure function -- QUADS data never enters etcd or NodeRegistry. The poller maintains its own cache, separate from the proxy httpx client (different timeout settings). Dashboard JS renders one table from a single unified API endpoint.

**New components:**
1. **QUADSClient** (`quads/client.py`) -- async httpx calls to QUADS API, returns Pydantic models
2. **QUADSPoller** (`quads/poller.py`) -- background asyncio.Task, caches host list, tracks staleness
3. **QUADSHost** (`models/quads.py`) -- Pydantic model for QUADS host data
4. **merge_node_list()** (`api/merge.py`) -- pure function merging QUADS + etcd + pending hosts

**Modified components:**
5. `settings.py` -- add `QUADSSettings` nested model
6. `dependencies.py` -- add `get_quads_poller()` DI
7. `admin.py` -- `GET /admin/nodes` returns `UnifiedNodeResponse`
8. `main.py` -- create/destroy QUADSClient and QUADSPoller in lifespan
9. `dashboard.html` -- unified table, inline actions, remove setup form

### Critical Pitfalls (Ranked)

1. **Setup race condition** -- Between clicking "Setup" and etcd registration (10+ seconds), the host appears available in the UI, inviting duplicate setups. **Prevention:** Add `pending_hosts: set[str]` to provisioner, checked by merge logic and returning 409 on duplicates.

2. **Stale cache -> provisioning wrong host** -- QUADS says available, but host was just assigned to another team. **Prevention:** Re-validate availability with a fresh QUADS API call at setup time, not from cache. Display cache age in UI.

3. **Hostname identity mismatch** -- QUADS returns FQDNs, etcd has short names. Merge fails silently, showing duplicates. **Prevention:** Canonical hostname normalization function applied in QUADS client, provisioner, and merge logic. Must be solved before merge logic.

4. **QUADS outage degrades dashboard** -- If QUADS is a hard dependency, its outage breaks the node list that worked fine in v1.2. **Prevention:** QUADS data is supplementary. Serve from poller cache. Return etcd nodes even when QUADS is unreachable. Show degradation indicator.

5. **JS state explosion** -- Unified list has 6+ states and conditional buttons. Vanilla JS DOM manipulation becomes unmaintainable. **Prevention:** Data-driven rendering with `STATE_CONFIG` map. Backend sends computed `state` and `available_actions` per node. No framework needed.

## Implications for Roadmap

### Phase 1: QUADS Client + Models + Configuration
**Rationale:** Foundation with zero integration risk. Fully testable in isolation with httpx mocking. Hostname normalization must be solved here before any merge logic.
**Delivers:** `QUADSClient`, `QUADSHost` model, `QUADSSettings`, `canonical_hostname()` function.
**Addresses:** FEATURES: QUADS API client, configuration. PITFALLS: #4 (hostname mismatch -- normalization), #8 (response format surprises -- Pydantic with `extra="ignore"`), #13 (separate httpx client with own timeouts).
**Avoids:** Building merge logic on mismatched identities.

### Phase 2: Background Poller + Lifespan Wiring
**Rationale:** Depends on QUADSClient from Phase 1. Adds the caching layer that all downstream features read from. Must be wired into existing shutdown lifecycle.
**Delivers:** `QUADSPoller` (asyncio.Task), staleness tracking (`last_successful_sync`, `consecutive_failures`), lifespan integration, graceful degradation on QUADS failure.
**Addresses:** FEATURES: periodic background polling. PITFALLS: #3 (QUADS outage -- serve stale data), #7 (lifecycle -- use existing stop_event), #10 (polling drift -- staleness tracking + exponential backoff).
**Avoids:** Dashboard depending on live QUADS calls.

### Phase 3: Merge Logic + Unified Admin API
**Rationale:** Pure data transformation. Depends on QUADSHost model (Phase 1) and poller cache (Phase 2). The merge function is the core v1.3 deliverable. Must include the setup deduplication guard.
**Delivers:** `merge_node_list()` pure function, `UnifiedNodeResponse` model, modified `GET /admin/nodes`, `pending_hosts` guard on `POST /admin/nodes/setup` (409 on duplicate), fresh QUADS availability check at setup time.
**Addresses:** FEATURES: unified node list, availability status, GPU indicator. PITFALLS: #1 (setup race -- pending_hosts set), #2 (stale cache -- fresh check at setup), #6 (merge in backend, not frontend).
**Avoids:** Duplicate setups, stale-data provisioning, frontend merge race conditions.

### Phase 4: Dashboard UI Update
**Rationale:** Depends on the unified API from Phase 3. Must ship together with Phase 3 (schema change breaks old JS). Retain manual hostname input as fallback.
**Delivers:** Unified table rendering, state-based inline action buttons, QUADS status indicator (connected/stale/unavailable), cache age display, manual hostname input retained as collapsed control.
**Addresses:** FEATURES: inline Setup/Teardown, remove setup form (partially -- keep manual fallback), state-based buttons. PITFALLS: #5 (form removal regression -- keep manual input), #9 (JS state explosion -- data-driven STATE_CONFIG), #11 (table flicker -- DocumentFragment swap).
**Avoids:** Locking operators out when QUADS is unreachable.

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** The poller calls the client. Client and models must exist first.
- **Phase 2 before Phase 3:** The merge function reads from the poller cache. Cache must exist first.
- **Phase 3 and Phase 4 ship together:** The admin API schema changes in Phase 3 break the existing dashboard JS. These phases must land in the same release to avoid a broken dashboard window.
- **Hostname normalization in Phase 1, not Phase 3:** If normalization is deferred, Phase 3 merge logic silently produces duplicates. Fixing it later requires migrating existing etcd entries.
- **Each phase is independently testable:** Phase 1-2 can be tested without UI. Phase 3 can be tested with unit tests on the pure merge function. Phase 4 requires manual browser testing.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Determine the exact QUADS hostname format in the target environment (FQDN vs short name) and the `host_type`/processor metadata available for GPU filtering. A few manual `curl` calls against the live QUADS instance before coding.
- **Phase 3:** The `pending_hosts` deduplication guard touches the existing provisioner. Needs careful review of `NodeProvisioner._background_tasks` and the setup endpoint to avoid regressions.

Phases with standard patterns (skip research):
- **Phase 2:** Background asyncio.Task with periodic polling is a textbook pattern. The codebase already has two background services (watcher, health checker) to follow.
- **Phase 4:** Vanilla JS table rendering with state-driven buttons. The existing dashboard.js is the template. No new patterns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new dependencies. All existing deps verified against current versions. QUADS API endpoints verified against source code. |
| Features | HIGH | Feature set derived from QUADS API source (swagger.yaml, blueprints, models.py) and existing codebase. Concrete, not speculative. |
| Architecture | HIGH | Follows established codebase patterns (DI, lifespan, background tasks, Pydantic models). Component boundaries clear and validated against SOLID. |
| Pitfalls | HIGH | Pitfalls verified against existing codebase (admin.py line 78-85 has no dedup, provisioner.py line 196-206 has registration gap). Race conditions traced through actual code paths. |

**Overall confidence:** HIGH

### Gaps to Address

- **Live QUADS instance exploration:** Research was against QUADS source code, not the actual deployed instance. The hostname format, available host_type values, and processor metadata fields should be verified with `curl` against the live API before coding Phase 1.
- **QUADS API version:** Research covers v3. If the target environment runs QUADS v2 (MongoDB backend), the response format differs significantly (`$oid`, `$date` fields). Pin to v3 and document the requirement.
- **Backward compatibility of `/admin/nodes`:** The response schema changes from `AdminNodeResponse` to `UnifiedNodeResponse`. Since the only consumer is the dashboard JS (internal network, no external clients), this is not a breaking change. But confirm no scripts or monitoring tools hit this endpoint.
- **Existing etcd entries:** If nodes were registered with short hostnames in v1.2, the merge logic needs to handle matching against QUADS FQDNs. A one-time migration or dual-lookup strategy may be needed.

## Sources

### Primary (HIGH confidence)
- QUADS GitHub: https://github.com/redhat-performance/quads -- blueprints, models, swagger.yaml
- QUADS hosts blueprint: `src/quads/server/blueprints/hosts.py` -- GET endpoints unauthenticated
- QUADS available blueprint: `src/quads/server/blueprints/available.py` -- returns list of hostname strings
- QUADS host model: `src/quads/server/models.py` -- Host, Processor, Schedule, Assignment, Cloud
- QUADS swagger: `src/quads/server/swagger.yaml` -- OpenAPI 3.0.0 spec
- QUADS Python client: `src/quads/quads_api.py` -- reference endpoint patterns
- Existing codebase: `inference_proxy/` -- admin.py, provisioner.py, main.py, dashboard.js, settings.py

### Secondary (MEDIUM confidence)
- QUADS API documentation: https://github.com/redhat-performance/quads/blob/master/docs/quads-api.md
- QUADS 2.2 release notes: https://github.com/redhat-performance/quads/releases/tag/v2.2.4 -- GPU awareness

---
*Research completed: 2026-07-15*
*Ready for roadmap: yes*
