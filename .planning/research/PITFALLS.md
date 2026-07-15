# Domain Pitfalls

**Domain:** QUADS REST API Integration and Unified Node List for LLM Inference Gateway
**Researched:** 2026-07-15
**Confidence:** HIGH (verified against existing codebase architecture, QUADS API documentation, and real integration patterns)

**Scope:** Pitfalls specific to adding QUADS API integration, unified node list, and inline provisioning controls to the existing v1.2 gateway. Prior pitfalls (v1.0 streaming/etcd, v1.2 SSH provisioning) are in git history.

---

## Critical Pitfalls

Mistakes that cause outages, data corruption, or require architectural rework.

### Pitfall 1: Race Between QUADS "Available" State and Provisioning Transition

**What goes wrong:** QUADS reports host-A as available. Operator clicks "Setup" in the unified node list. The gateway fires `POST /admin/nodes/setup` (background task, returns 202). The QUADS poller runs its next cycle before the provisioner registers the node in etcd as PROVISIONING. The unified node list still shows host-A as "available" because QUADS still reports it as available and etcd has no entry yet. The operator (or a different operator) sees it as available and clicks "Setup" again. Two concurrent provisioning tasks now race on the same host.

The existing v1.2 code has no guard against this. `POST /admin/nodes/setup` (admin.py line 78-85) fires `provisioner.fire_background()` with no deduplication. The provisioner registers the node in etcd as PROVISIONING only AFTER preflight passes (provisioner.py line 196-206) -- a gap of 10+ seconds where the host appears in neither etcd nor any in-progress tracking visible to the UI.

**Why it happens:** Two independent data sources (QUADS and etcd) with no shared state. The transition from "QUADS available" to "etcd PROVISIONING" is not atomic. During the gap, the UI shows stale state from the QUADS source.

**Consequences:**
- Concurrent SSH sessions running setup.sh on the same host (Pitfall 9 from v1.2).
- Corrupted package state, driver install races.
- Two background tasks for the same host, only one can succeed, the other fails with confusing errors.
- Dashboard flickers between "available" and "provisioning" on subsequent poll cycles.

**Prevention:**
- Add a client-side in-memory set of "in-flight" hostnames. When setup is triggered, add the hostname to this set BEFORE firing the background task. The unified node list API must check this set and report the host as "provisioning" even before the etcd write.
- The existing `_background_tasks` set in NodeProvisioner tracks tasks but not hostnames. Add a `pending_hosts: set[str]` that is populated on setup request and cleared on provisioning completion (success or failure). The admin endpoint checks this set and returns 409 Conflict on duplicate setup requests.
- The `/admin/nodes` response (or a new unified endpoint) must merge three sources: QUADS available hosts, in-flight provisioning set, and etcd registry. A host present in the in-flight set is shown as "provisioning" regardless of what QUADS says.
- This is the same per-host lock pattern from v1.2 Pitfall 9, but now it must also be visible to the UI merge logic.

**Phase:** Must be in the unified API endpoint design. The merge logic and the guard are the same feature.

---

### Pitfall 2: Stale QUADS Cache Showing Hosts That Are No Longer Available

**What goes wrong:** The QUADS poller fetches available hosts every N seconds (e.g., 60s). Between polls, a host gets assigned to another team's cloud in QUADS. The gateway's cache still shows it as "available." An operator clicks "Setup." The SSH connection succeeds (the host is reachable), setup.sh runs, vLLM starts -- on a host that was just allocated to someone else. That team's workload is now competing with or displaced by vLLM.

Worse: QUADS moves the host to a different network/VLAN as part of the cloud assignment. SSH works briefly (cached ARP), then fails mid-setup. The host is partially provisioned on a network it's being pulled off of.

**Why it happens:** QUADS is the source of truth for host allocation. The gateway's QUADS cache is a snapshot that ages. The longer the poll interval, the larger the window for stale data. But even a 5-second poll interval cannot eliminate the race -- only shrink it.

**Consequences:**
- Provisioning a host allocated to another team -- operational conflict, potential data loss on the other team's workload.
- Partially provisioned host on a transitioning network -- unreachable after QUADS moves it.
- Trust erosion: operators stop trusting the "available" status in the dashboard.

**Prevention:**
- Re-validate availability with a fresh QUADS API call at setup time, not from cache. The `POST /admin/nodes/setup` handler (or the provisioner's preflight) should call QUADS `/api/v3/available` (or equivalent) synchronously before firing the background task. If the host is no longer available, return 409 with a clear message.
- Display the cache age in the UI. Show "Last QUADS sync: 45s ago" so operators know how fresh the data is.
- Use a short poll interval (30s) but accept that it is not a guarantee. The fresh check at setup time is the real guard.
- Consider adding a QUADS schedule check: query the host's current cloud assignment, not just availability. A host in `cloud01` (spare pool) is truly idle. A host in `cloud15` is assigned.

**Phase:** QUADS client implementation. The fresh-check-at-setup-time is part of the provisioning flow, not a separate feature.

---

### Pitfall 3: QUADS API Unavailability Degrading the Entire Dashboard

**What goes wrong:** QUADS API goes down (service restart, network issue, maintenance). The unified node list endpoint tries to fetch QUADS hosts, gets a connection error or timeout, and either: (a) returns 500 to the dashboard, breaking the entire UI, or (b) blocks for the full timeout duration, making the dashboard sluggish.

The existing dashboard fetches three endpoints in parallel (dashboard.js lines 105-108): `/admin/nodes`, `/admin/metrics`, `/admin/provisioning/tasks`. If the unified endpoint adds QUADS as a fourth dependency, a QUADS outage takes down the dashboard that was previously working fine for monitoring etcd-registered nodes.

**Why it happens:** Coupling two independent data sources into a single API response without graceful degradation. The dashboard worked perfectly without QUADS in v1.2. Adding QUADS as a hard dependency is a regression.

**Consequences:**
- Dashboard shows "Update failed -- retrying..." (dashboard.js line 187) during QUADS outage.
- Operators cannot see the health of currently running nodes during a QUADS outage.
- All operational visibility lost because a non-critical feature (host discovery) failed.
- If the QUADS call blocks for 30s (httpx default timeout), dashboard polling backs up and the UI appears frozen.

**Prevention:**
- QUADS data is supplementary, not required. The unified endpoint must return etcd-registered nodes even when QUADS is unreachable. QUADS hosts are merged in when available, omitted when not.
- Return a degradation indicator in the API response: `{"quads_status": "unavailable", "quads_last_sync": "2026-07-15T10:30:00Z", "nodes": [...]}`. The UI shows a warning banner but still renders the node list.
- Set a short httpx timeout for QUADS calls (5s connect, 10s read). QUADS is a supplementary data source, not on the critical path.
- Cache the last successful QUADS response in memory. On failure, serve the cached response with a staleness indicator. This is the standard stale-while-revalidate pattern.
- Do NOT make the unified node list endpoint await QUADS synchronously. Serve QUADS data from the background poller's cache. The endpoint just reads the cache, never calls QUADS directly.

**Phase:** QUADS client and unified endpoint design. The degradation pattern must be in the initial architecture, not bolted on later.

---

### Pitfall 4: Identity Mismatch Between QUADS Hosts and etcd Nodes

**What goes wrong:** QUADS returns hosts as FQDNs: `host-01.scalelab.redhat.com`. The existing system uses short hostnames as `node_id` in etcd (provisioner.py line 298: `node_id=hostname`). The setup form in v1.2 accepts whatever the operator types. If an operator typed `host-01` (short) in the old form, but QUADS returns `host-01.scalelab.redhat.com` (FQDN), the unified node list shows the same physical host twice: once as a QUADS available host and once as an etcd provisioned node.

The merge logic cannot match them because the keys differ. The dashboard shows "host-01.scalelab.redhat.com (Available)" and "host-01 (Healthy)" side by side -- same host, different identities.

**Why it happens:** No canonical hostname format was enforced in v1.2. The `node_id` is whatever string the operator passes to `POST /admin/nodes/setup`. QUADS has its own naming convention. There is no normalization.

**Consequences:**
- Duplicate entries in the unified node list for the same physical host.
- Operator tries to tear down "host-01" but the QUADS entry for "host-01.scalelab.redhat.com" still shows as available, inviting a re-provision attempt.
- Merge logic silently fails to correlate hosts, making the unified view useless.
- If provisioning uses the FQDN from QUADS but etcd has the short name from a previous manual setup, the node appears twice in the registry.

**Prevention:**
- Canonicalize hostnames. Pick one format (FQDN or short) and normalize everywhere. Since QUADS returns FQDNs, use FQDN as the canonical `node_id`. When provisioning from the unified list, pass the FQDN from QUADS directly.
- Add a normalization function: `def canonical_hostname(name: str) -> str` that strips or appends the domain suffix consistently. Use it in the QUADS client, the provisioner, and the merge logic.
- For backward compatibility with existing etcd entries: the merge logic should try both FQDN and short hostname when matching. Or run a one-time migration to normalize existing etcd entries.
- The `SetupRequest` model (admin.py) should validate and normalize the hostname before passing it to the provisioner.

**Phase:** First phase -- before any merge logic. Hostname normalization is a precondition for correct merging.

---

### Pitfall 5: Removing the Setup Form Before Inline Actions Are Complete and Tested

**What goes wrong:** The v1.3 plan says "Remove separate setup input form and setup buttons -- everything through the node list." The old setup form (dashboard.html lines 24-30, dashboard.js lines 196-223) is simple and works: type a hostname, click Setup. If the inline "Setup" button in the unified node list has a bug, there is no fallback for provisioning.

Scenarios where inline-only breaks:
- QUADS API is down: no available hosts shown, no Setup buttons visible. With the old form, operators could still type a hostname manually.
- QUADS doesn't know about a host (new server not yet registered in QUADS): invisible in the unified list, cannot be provisioned. The old form accepted any hostname.
- A host is in QUADS but filtered out by the GPU/availability query: invisible, cannot be provisioned.

**Why it happens:** Replacing a working UI with a new one in a single step. The old form was a universal fallback -- any hostname, no dependencies. The inline buttons depend on QUADS data being correct and available.

**Consequences:**
- Operators locked out of provisioning when QUADS is unreachable.
- Hosts not in QUADS cannot be provisioned at all.
- Regression discovered in production when QUADS goes down at an inconvenient time.

**Prevention:**
- Keep the manual hostname input as a secondary/collapsed control. The inline buttons are the primary workflow, but a "Manual setup" text input remains for edge cases and QUADS outages. This is one `<input>` and one `<button>` -- not a significant UI burden.
- Alternative: phase the removal. In v1.3.0, add inline buttons alongside the existing form. In v1.3.1 (after validation), collapse the form into a "manual override" section. In v1.4, remove it entirely if nobody uses it.
- At minimum, the admin API endpoint `POST /admin/nodes/setup` must continue accepting arbitrary hostnames. The UI can change, the API should not remove capability.

**Phase:** UI implementation. Do not remove the form in the same phase that adds inline buttons. Add first, validate, then remove.

---

## Moderate Pitfalls

Mistakes that cause significant debugging time or operational headaches.

### Pitfall 6: Merging Data Sources in the Wrong Layer

**What goes wrong:** Two reasonable approaches for merging QUADS hosts and etcd nodes:

(A) **Backend merge:** A new API endpoint returns a unified list, merging QUADS cache and etcd registry server-side. The frontend receives one flat list.

(B) **Frontend merge:** The frontend fetches `/admin/nodes` (etcd) and a new `/admin/quads/hosts` endpoint separately, then merges in JavaScript.

Option B seems simpler (two independent endpoints, frontend combines) but creates problems:
- The merge logic (matching hostnames, determining state priority, handling conflicts) is duplicated if any other consumer needs the unified list (e.g., a future CLI tool, monitoring integration).
- The JavaScript merge runs on every poll cycle (every 10 seconds). Complex merge logic in vanilla JS DOM manipulation (already 224 lines) becomes unmaintainable.
- Race condition: the two fetches return at different times. Between `/admin/nodes` returning and `/admin/quads/hosts` returning, the UI flickers -- a host briefly appears as "available" then jumps to "provisioned" when the second response arrives.

Option A is more work upfront but keeps the merge logic in Python (testable, type-checked) and delivers a consistent snapshot to the frontend.

**Prevention:**
- Merge in the backend. Create a single endpoint (e.g., `GET /admin/fleet`) that returns a unified list. Each entry has a `source` field ("quads", "etcd", or "both") and a computed `state` field ("available", "provisioning", "healthy", "unhealthy", "draining").
- The merge logic is a pure function: `merge(quads_hosts, etcd_nodes, pending_hosts) -> list[UnifiedNode]`. Easy to test, no side effects.
- The frontend fetches one endpoint, renders one table. The existing `refreshDashboard()` pattern (fetch + render) stays the same, just with a different endpoint and richer data.
- Keep the raw `/admin/nodes` endpoint for backward compatibility and API consumers that only care about etcd-registered nodes.

**Phase:** Unified endpoint design. This is an architectural decision that affects everything downstream.

---

### Pitfall 7: Background QUADS Poller Lifecycle Not Integrated with Existing Shutdown

**What goes wrong:** The gateway already has two background threads (etcd watcher, health checker) managed by a shared `stop_event` and joined during shutdown (main.py lines 123-149, 190-198). A new QUADS background poller needs the same lifecycle management. If it is added as a raw `asyncio.create_task()` without proper cancellation, it:
- Keeps running during graceful shutdown, making HTTP calls to QUADS while the gateway is draining.
- Holds open an httpx client that gets closed during shutdown, causing `RuntimeError: Event loop is closed` or `httpx.PoolTimeout`.
- Is not joined on shutdown, so the process exits with the poller mid-request, potentially corrupting the cached state.

**Why it happens:** The existing shutdown pattern uses `threading.Event` + `thread.join()`. A new poller might use `asyncio.Task` (natural for async code) but then misses the `stop_event` signal. Or it uses a thread but with its own httpx client that is not closed in the right order.

**Prevention:**
- Use the same `stop_event` that the etcd watcher and health checker use. The QUADS poller is an async loop that checks `stop_event.is_set()` between poll cycles.
- If the poller is an `asyncio.Task` (preferred since QUADS calls are async httpx), store it in `app.state` and cancel it during the lifespan teardown, before closing the httpx client.
- The poller should use the application's shared httpx client or its own client that is created and closed within the poller's lifecycle. Do not share the proxy httpx client (different timeout/pool settings).
- Add the poller startup/shutdown to the existing lifespan function in main.py, in the same block as the other background services.

**Phase:** QUADS client implementation. Wire into existing lifecycle from the start.

---

### Pitfall 8: QUADS Response Format Surprises

**What goes wrong:** The QUADS API has evolved through multiple versions (v2 with MongoDB backend returning `$oid`/`$date` fields, v3 with PostgreSQL returning standard JSON). The response format depends on the QUADS version deployed in the target environment. Code written against v3 responses breaks when pointed at a v2 QUADS instance, or vice versa.

Specific surprises from the QUADS API:
- Host objects may include MongoDB-style `{"$oid": "..."}` for IDs and `{"$date": 1552923007391}` for timestamps (v2).
- The `cloud` field on a host object may be an object reference (`{"$oid": "..."}`) rather than a cloud name string -- requires a join/follow-up call to get the cloud name.
- The `/api/v2/available` endpoint parameters use CLI-style `--schedule-start` format in the docs but may expect query params (`?schedule_start=...`) in practice.
- Empty responses may be `[]`, `{}`, `""`, or `null` depending on the endpoint and version.
- The `host_type` field is free-form text (not an enum). GPU presence is not a standard field -- it may need to be inferred from hostname patterns, host_type, or a separate metadata query.

**Prevention:**
- Before writing the QUADS client, make a few manual `curl` calls against the actual QUADS instance to observe real response formats. Do not rely solely on documentation.
- Use Pydantic models for QUADS response parsing with `model_config = ConfigDict(extra="ignore")` to tolerate unexpected fields. Define the fields you need, ignore the rest.
- Handle both v2 and v3 response formats in the parser, or pin to the specific version deployed in the target environment and document the requirement.
- For GPU host filtering: determine how GPU hosts are identified in the target QUADS instance (hostname pattern? host_type? metadata field?) and make it configurable, not hardcoded.

**Phase:** QUADS client implementation. Start with manual API exploration, then code the client.

---

### Pitfall 9: Unified Node List State Explosion in Vanilla JS

**What goes wrong:** The current dashboard.js is 224 lines of vanilla JS DOM manipulation. The node table renders 8 columns with one conditional action button (Teardown, disabled during provisioning/draining). The unified node list needs:
- New states: "available" (from QUADS), plus all existing states.
- Conditional action buttons per state: Available -> Setup, Healthy -> Teardown, Unhealthy -> Teardown + Retry, Provisioning -> (disabled), Draining -> (disabled).
- A QUADS status indicator (connected/disconnected/stale).
- Visual distinction between QUADS-only hosts and etcd-registered nodes.
- Potentially more columns (GPU info, cloud assignment, QUADS last seen).

The DOM rendering code becomes a state machine with 5+ branches for button rendering, 6+ status badge variants, and conditional columns. Without a framework, this is 400+ lines of `document.createElement` calls with nested conditionals.

**Why it happens:** Vanilla JS was the right choice for v1.1 (simple table, one button). The v1.3 unified list has enough conditional rendering to exceed what vanilla DOM manipulation handles cleanly.

**Consequences:**
- Bug-prone button state logic. A missed `if` condition means a Setup button appears on a provisioning node.
- Difficult to test. No unit tests for JS rendering (the existing test suite is Python-only).
- Every new state or action requires editing deeply nested createElement chains.

**Prevention:**
- Do NOT switch to React/Vue/Svelte for this. The project constraint is "Jinja2 + vanilla JS, no build step." Respect it.
- Extract rendering into small functions: `renderActionButtons(node)`, `renderStatusBadge(node)`, `renderNodeRow(node)`. Each function handles one concern.
- Use a state-to-config map instead of if/else chains:
  ```javascript
  const STATE_CONFIG = {
    available: { badge: "badge-available", actions: ["setup"] },
    healthy: { badge: "badge-healthy", actions: ["teardown"] },
    unhealthy: { badge: "badge-unhealthy", actions: ["teardown", "retry"] },
    provisioning: { badge: "badge-in-progress", actions: [] },
    draining: { badge: "badge-draining", actions: [] },
  };
  ```
- Keep the rendering data-driven. The backend sends a computed `state` and `available_actions` list per node. The frontend maps these to buttons without needing to know the state machine.

**Phase:** Unified endpoint design (backend sends computed actions) and UI implementation (data-driven rendering).

---

### Pitfall 10: QUADS Polling Thread Hammering the API or Drifting Silently

**What goes wrong:** Two failure modes:

(A) **Too aggressive:** Polling QUADS every 5 seconds with a request that queries all hosts. QUADS is Flask + PostgreSQL and not designed for high-frequency polling. Under load, QUADS responses slow down, the gateway's poller backs up, multiple in-flight requests stack up, QUADS falls over.

(B) **Silent drift:** The poller encounters an error (QUADS returns 500, network timeout). The error is logged but the cached data is retained. The poller retries on the next cycle but keeps failing. The cache serves increasingly stale data (minutes, hours) with no indication to the operator. The UI shows hosts as "available" that were reassigned hours ago.

**Why it happens:** Background pollers are fire-and-forget. Without explicit staleness tracking and alerting, failures are invisible. The existing dashboard polling (dashboard.js) shows "Update failed -- retrying..." on the frontend, but the backend QUADS poller has no equivalent visibility.

**Prevention:**
- Track `last_successful_sync` timestamp and `consecutive_failures` count in the QUADS cache object. Expose these in the API response and the UI.
- Define a staleness threshold (e.g., 5 minutes). If `last_successful_sync` exceeds the threshold, the UI shows a warning: "QUADS data is stale (last sync: 10 minutes ago)." Available hosts are still shown but visually dimmed or flagged.
- Use exponential backoff on consecutive failures: 30s -> 60s -> 120s -> 300s (cap). This prevents hammering a struggling QUADS instance.
- Log at WARNING level on first failure, ERROR level after 3 consecutive failures.
- Default poll interval: 60 seconds. This balances freshness with QUADS load. Make it configurable via `INFERENCE_PROXY_QUADS__POLL_INTERVAL`.

**Phase:** QUADS client implementation. Staleness tracking is part of the cache, not a separate feature.

---

### Pitfall 11: Unified Node List Flickers on Every Poll Cycle

**What goes wrong:** The current `refreshDashboard()` (dashboard.js line 99) replaces the entire table body on every poll: `tbody.innerHTML = ""` then re-appends all rows. This causes a visual flicker -- the table blanks for a frame then re-renders. At 10-second intervals this is barely noticeable with 3-5 nodes.

With the unified list (potentially 20-50+ hosts from QUADS plus provisioned nodes), the flicker becomes pronounced. Worse: if an operator is about to click a button and the table re-renders, the click target moves and they click the wrong action. Setup instead of Teardown.

**Why it happens:** Full DOM replacement is the simplest rendering strategy. The v1.1 implementation chose it for simplicity. With more rows and interactive elements, the trade-off changes.

**Prevention:**
- Diff-and-patch instead of full replace. Compare the new node list with what is currently in the DOM. Only update rows that changed (status changed, connections changed). Add/remove rows as needed.
- Alternative (simpler): use `requestAnimationFrame` to batch the update. Replace `tbody.innerHTML = ""` with building the new content in a `DocumentFragment`, then replacing in one DOM operation. This eliminates the blank-frame flicker.
- Disable buttons during the fetch-and-render cycle to prevent mis-clicks on moving targets.
- A practical middle ground: build the full new tbody content in a fragment, swap it in with `tbody.replaceChildren(...fragment.childNodes)`. One DOM operation, no blank frame.

**Phase:** UI implementation. The `DocumentFragment` approach is a small change to the existing render pattern.

---

## Minor Pitfalls

Issues that cause debugging annoyance or minor operational friction.

### Pitfall 12: QUADS Host List Returns Non-GPU Hosts

**What goes wrong:** QUADS manages all bare-metal servers -- not just GPU servers. A `/api/v3/available` call returns servers with CPUs only, servers with FPGAs, storage nodes, network appliances. The unified node list shows 200+ hosts when only 15 have GPUs suitable for vLLM.

**Prevention:**
- Filter on the QUADS side if the API supports it (e.g., `?host_type=gpu` or metadata filter). If not, filter client-side.
- Make the filter configurable: `INFERENCE_PROXY_QUADS__HOST_FILTER` accepting a regex pattern or a list of host_type values. The QUADS client applies this filter after fetching.
- Default to showing all hosts with a UI filter/search. Operators may want to see non-GPU hosts to understand what is available.
- Determine the filtering mechanism by examining the actual QUADS instance's host_type values and metadata fields before coding.

**Phase:** QUADS client configuration. A config setting, not a code architecture decision.

---

### Pitfall 13: httpx Client Configuration Conflicts

**What goes wrong:** The gateway already has an httpx.AsyncClient configured for proxy traffic (main.py lines 168-181) with specific timeouts (5s connect, 120s read) and pool limits (100 connections). The QUADS poller needs its own httpx client with different settings (5s connect, 10s read -- QUADS calls are fast). If the QUADS client reuses the proxy httpx client, the 120s read timeout means a hung QUADS call blocks for 2 minutes before failing.

**Prevention:**
- Create a separate httpx.AsyncClient for the QUADS poller with its own timeout and pool settings. Create it in the poller's lifecycle (startup), close it on shutdown.
- Do not store it in `app.state` alongside the proxy client -- that invites confusion. Keep it internal to the QUADS client class.
- Set aggressive timeouts: 5s connect, 10s read. QUADS responses should be fast; anything longer indicates a problem.

**Phase:** QUADS client implementation. Constructor parameter, not a concern for the broader architecture.

---

### Pitfall 14: Test Complexity Explosion with Two External Dependencies

**What goes wrong:** Tests now need to mock both etcd responses (existing) and QUADS API responses (new). The conftest.py and fixtures grow to handle both. Integration tests for the unified endpoint need coordinated mock state across two systems: "QUADS says host-A is available AND etcd says host-B is healthy AND host-C is in the pending set."

**Prevention:**
- The QUADS client should be a simple class with a clear interface (e.g., `get_available_hosts() -> list[QuadsHost]`). Inject it via FastAPI's dependency injection, same as the existing provisioner and registry. In tests, override it with a stub.
- The merge function should be a pure function that takes `(quads_hosts, etcd_nodes, pending_hosts)` and returns `list[UnifiedNode]`. Test the merge logic independently with unit tests -- no mocking needed, just pass in lists.
- Do not test the QUADS HTTP client by mocking httpx. Test the merge logic with pure data. Test the QUADS client with a few integration tests using pytest-httpx.

**Phase:** Implementation. Follow the existing dependency injection pattern in `config/dependencies.py`.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| QUADS client + polling | Response format surprises (#8), silent drift (#10), httpx conflicts (#13) | Manual API exploration first, staleness tracking, separate httpx client |
| Hostname normalization | Identity mismatch (#4) | Canonical format function, applied everywhere, before merge logic |
| Unified API endpoint | Wrong merge layer (#6), race on setup (#1), QUADS down degrades all (#3) | Backend merge, pending_hosts set, graceful degradation |
| UI: unified node list | State explosion in JS (#9), table flicker (#11), form removal regression (#5) | Data-driven rendering, DocumentFragment swap, keep manual input |
| Availability validation | Stale cache provisioning wrong host (#2) | Fresh QUADS check at setup time, not from cache |
| Background poller lifecycle | Not wired to shutdown (#7) | Use existing stop_event, create/close httpx client in poller scope |
| Testing | Mock complexity (#14) | Pure merge function, DI for QUADS client, minimal integration tests |
| Host filtering | Non-GPU hosts in list (#12) | Configurable filter, determine filter field from actual QUADS instance |

---

## Sources

- QUADS API documentation: https://github.com/redhat-performance/quads/blob/master/docs/quads-api.md
- QUADS project: https://github.com/redhat-performance/quads
- QUADS project site: https://quads.dev/
- Existing codebase: `inference_proxy/api/admin.py` (setup endpoint, no deduplication)
- Existing codebase: `inference_proxy/provisioning/provisioner.py` (PROVISIONING registration gap)
- Existing codebase: `inference_proxy/main.py` (lifespan shutdown pattern, httpx client config)
- Existing codebase: `inference_proxy/static/js/dashboard.js` (DOM rendering, polling pattern)
- Existing codebase: `inference_proxy/discovery/registry.py` (NodeRegistry, thread-safe access)
- Stale-while-revalidate pattern: standard HTTP caching strategy applied to background polling
