# Phase 18: Dashboard UI Update - Research

**Researched:** 2026-07-17
**Domain:** Frontend (vanilla JS + Jinja2 + CSS) with one small backend endpoint
**Confidence:** HIGH

## Summary

This phase updates the dashboard frontend to consume the Phase 17 unified node list API (`GET /admin/nodes` returning `AdminNodeResponse` with `state`, `actions`, `gpu_vendor`, `gpu_model`, `gpu_count`). The work is entirely in three files (`dashboard.html`, `dashboard.js`, `dashboard.css`) plus one new backend endpoint (`GET /admin/quads/status`) and its Pydantic model. No new dependencies. No new frameworks.

The existing codebase already has every pattern needed: badge CSS classes, `showToast()`, `handleTeardown()` with `window.confirm()`, `fetch()` + JSON body POSTs, `createElement`/`appendChild` DOM construction, and `setInterval` polling. The phase is an expansion of existing patterns, not an introduction of new ones.

**Primary recommendation:** Modify the three dashboard files in-place using established patterns. Add one lightweight `GET /admin/quads/status` endpoint to `admin.py` returning poller staleness data. Update existing tests. No abstractions, no libraries, no build tools.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Keep current table structure. Add GPU Vendor and GPU Model columns after Node ID. Column order: Node ID, GPU Vendor, GPU Model, Endpoint, Model, State, Active Connections, Circuit Breaker, Requests, Actions.
- **D-02:** Replace "Status" column with "State" -- show unified state from Phase 17. Remove raw etcd status column.
- **D-03:** Available nodes show em-dash in cells that don't apply (endpoint, model, connections, circuit breaker, requests).
- **D-04:** Remove standalone "Provision Node" card. Add "Manual setup" toggle link below Node Fleet card title.
- **D-05:** Toggle is a simple text link ("+ Manual setup") with vanilla JS display toggle. No animation, no `<details>`.
- **D-06:** Color-coded action buttons by intent: Setup=blue, Teardown=red outline, Retry=amber, Cancel=red, Force Teardown=red.
- **D-07:** `window.confirm` required for destructive actions (Teardown, Force Teardown, Cancel). Setup and Retry fire without confirmation.
- **D-08:** Multiple actions: primary as button, secondary in dropdown/menu. Primary = first item in `actions` list.
- **D-09:** QUADS status badge in dashboard header alongside "Last updated". Badge with color matching status.
- **D-10:** Backend: expose QUADS poller staleness via new field on existing endpoint or lightweight dedicated endpoint.

### Claude's Discretion
- Exact wording and icon for QUADS status badge
- Staleness thresholds (stale vs unavailable) -- align with poller's `consecutive_failures`
- Whether QUADS status comes from `/admin/quads/status` or embedded in `/admin/nodes`
- Dropdown/menu implementation details for secondary actions
- CSS class naming for new action button variants
- How to wire Setup action from inline buttons through existing `POST /admin/nodes/setup`

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | Dashboard displays single unified table showing all nodes across all states | D-01 column layout, `refreshDashboard()` consuming `GET /admin/nodes` which already returns unified list from Phase 17 |
| DASH-02 | Dashboard shows inline action buttons per node based on current state | D-06/D-07/D-08 button styling, `_STATE_ACTIONS` mapping consumed via `node.actions` field, existing `handleTeardown()` pattern |
| DASH-03 | Standalone setup form removed, replaced by inline controls with collapsed manual hostname fallback | D-04/D-05 manual setup toggle, inline Setup buttons wired to `POST /admin/nodes/setup` |
| DASH-04 | Dashboard shows QUADS connection status indicator with cache age | D-09/D-10 QUADS status badge, new `GET /admin/quads/status` endpoint exposing poller staleness |
| DASH-05 | Dashboard shows GPU hardware info per host inline in the node list | D-01 GPU Vendor and GPU Model columns, data already in `AdminNodeResponse.gpu_vendor`/`gpu_model` |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Unified node table rendering | Browser / Client | -- | DOM construction from JSON API response, vanilla JS |
| Action button dispatch (setup/teardown/retry) | Browser / Client | API / Backend | Client sends fetch() to existing admin endpoints |
| QUADS status indicator | Browser / Client | API / Backend | Client polls new endpoint, backend reads poller state |
| Manual hostname fallback | Browser / Client | -- | Pure DOM toggle, reuses existing setup form handler |
| QUADS staleness data | API / Backend | -- | New endpoint reads QUADSPoller properties |

## Standard Stack

No new packages. This phase uses only what is already installed.

### Core (already installed)
| Library | Version | Purpose | Role in This Phase |
|---------|---------|---------|-------------------|
| FastAPI | >=0.135 | HTTP framework | One new `GET /admin/quads/status` endpoint in `admin.py` |
| Pydantic | >=2.10 | Data validation | One new `QUADSStatusResponse` model |
| Jinja2 | (transitive) | HTML templates | Modify `dashboard.html` |

### Frontend (no libraries)
| Technology | Purpose | Role in This Phase |
|------------|---------|-------------------|
| Vanilla JS | DOM manipulation | Modify `dashboard.js` -- new table columns, action buttons, QUADS status |
| CSS | Styling | Modify `dashboard.css` -- new badge class, button variants, dropdown menu |
| HTML | Template | Modify `dashboard.html` -- column headers, remove setup card, add toggle |

## Architecture Patterns

### System Architecture Diagram

```
[Browser: dashboard.js]
    |
    |--- GET /admin/nodes -------> [FastAPI admin.py] -> [UnifiedNodeService] -> merged list
    |--- GET /admin/metrics -----> [FastAPI admin.py] -> [RequestMetrics]
    |--- GET /admin/provisioning/tasks -> [FastAPI admin.py] -> [etcd]
    |--- GET /admin/quads/status -> [FastAPI admin.py] -> [QUADSPoller] (NEW)
    |
    |--- POST /admin/nodes/setup -> [FastAPI admin.py] -> [NodeProvisioner]
    |--- DELETE /admin/nodes/{id} -> [FastAPI admin.py] -> [NodeProvisioner]
    |
    v
[DOM: Node Fleet table, QUADS badge, toast notifications]
```

### Recommended Changes by File

```
inference_proxy/
  api/admin.py                  # Add GET /admin/quads/status endpoint
  models/admin.py               # Add QUADSStatusResponse model
  templates/dashboard.html      # Update table headers (10 cols), remove setup card, add toggle
  static/js/dashboard.js        # Update refreshDashboard(), add action handlers, QUADS status
  static/css/dashboard.css      # Add .badge-available, .btn-* variants, .action-group, .action-menu
tests/
  api/test_admin.py             # Add tests for GET /admin/quads/status
  api/test_dashboard.py         # Update column header assertions, setup form assertions
```

### Pattern 1: Action Button Dispatch

**What:** Map each action string from `node.actions` to an HTTP request and confirmation behavior.
**When to use:** Rendering the Actions cell for each node row.

Action-to-handler mapping (extends existing `handleTeardown` pattern):

```javascript
// [VERIFIED: codebase inspection of dashboard.js and admin.py]
const ACTION_CONFIG = {
  setup:          { method: "POST",   url: (id) => "/admin/nodes/setup", body: (id) => ({ hostname: id }), confirm: false, label: "Setup Node", css: "btn-setup" },
  teardown:       { method: "DELETE", url: (id) => `/admin/nodes/${id}`, body: null,                       confirm: true,  label: "Teardown",   css: "btn-teardown" },
  retry:          { method: "POST",   url: (id) => "/admin/nodes/setup", body: (id) => ({ hostname: id }), confirm: false, label: "Retry",      css: "btn-retry" },
  cancel:         { method: "DELETE", url: (id) => `/admin/nodes/${id}`, body: null,                       confirm: true,  label: "Cancel",     css: "btn-cancel" },
  force_teardown: { method: "DELETE", url: (id) => `/admin/nodes/${id}?force=true`, body: null,            confirm: true,  label: "Force Teardown", css: "btn-force-teardown" },
};
```

This replaces the current hardcoded teardown button with a data-driven approach. Each action in `node.actions` looks up its config and renders the appropriate button.

### Pattern 2: QUADS Status Endpoint

**What:** Lightweight endpoint exposing poller staleness.
**When to use:** Dashboard header QUADS connection indicator.

```python
# [VERIFIED: codebase inspection of poller.py properties and dependencies.py]
class QUADSStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: str  # "connected" | "stale" | "unavailable"
    last_sync: datetime | None
    consecutive_failures: int

@admin_router.get("/quads/status")
async def quads_status(
    poller: QUADSPoller | None = Depends(get_quads_poller),
) -> QUADSStatusResponse:
    if poller is None:
        return QUADSStatusResponse(status="unavailable", last_sync=None, consecutive_failures=0)
    failures = poller.consecutive_failures
    if poller.last_sync is None or failures >= 3:
        status = "unavailable"
    elif failures >= 1:
        status = "stale"
    else:
        status = "connected"
    return QUADSStatusResponse(status=status, last_sync=poller.last_sync, consecutive_failures=failures)
```

Staleness thresholds: `connected` = 0 failures, `stale` = 1-2 failures, `unavailable` = 3+ or never synced. These align with the poller's `consecutive_failures` counter. [ASSUMED -- thresholds are discretionary per CONTEXT.md]

### Pattern 3: Dropdown Menu for Secondary Actions

**What:** When `node.actions.length > 1`, primary button + caret dropdown for secondary actions.
**When to use:** Unhealthy nodes (teardown + retry), draining nodes (force_teardown -- only 1 action, no dropdown needed).

```javascript
// [VERIFIED: codebase inspection -- only unhealthy has 2+ actions]
// _STATE_ACTIONS: unhealthy -> ["teardown", "retry"]
// All other states have exactly 1 action -> no dropdown needed
```

Implementation: wrap primary button + caret in `.action-group` div. Caret toggles `.action-menu.open`. Document-level click listener closes menu when clicking outside.

### Anti-Patterns to Avoid
- **Fetching node list AND QUADS status separately then joining client-side:** QUADS status is system-level metadata, not per-node. Keep it as a separate fetch added to `Promise.all`.
- **Building a component framework for buttons:** The action button config object is sufficient. No need for a button factory class.
- **Using `<details>` for the manual setup toggle:** D-05 explicitly says no `<details>`. Use vanilla JS display toggle.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Action dispatch | Custom event system | Simple config object lookup | 5 actions, static mapping, no runtime registration needed |
| Dropdown menu | Full dropdown component library | 20 lines of vanilla JS | Only one use case (unhealthy nodes), document click listener suffices |
| Relative time formatting | Date formatting library | `Math.floor((now - then) / 60000)` + string template | Only need "Xm ago" / "Xh ago", not full i18n |

## Common Pitfalls

### Pitfall 1: Stale Buttons After Action
**What goes wrong:** User clicks Setup, the button stays enabled, user clicks again before poll refresh.
**Why it happens:** Action fires async but DOM doesn't update until next `refreshDashboard()` cycle.
**How to avoid:** Disable button on click immediately. The next poll cycle rebuilds the entire table body so stale buttons are naturally replaced. [VERIFIED: existing `handleTeardown` already does this]
**Warning signs:** Double-submit 409 errors from the dedup guard.

### Pitfall 2: Dropdown Menu Not Closing
**What goes wrong:** Click outside the dropdown doesn't close it.
**Why it happens:** Document click listener not registered, or `event.stopPropagation()` prevents bubbling.
**How to avoid:** Add a single document-level click listener that closes all open `.action-menu` elements. Do NOT use `stopPropagation()` on the caret button -- instead check `contains()`.
**Warning signs:** Multiple menus open simultaneously.

### Pitfall 3: colspan Mismatch
**What goes wrong:** Empty-state row ("No nodes found") doesn't span full table width.
**Why it happens:** Old colspan="8", new table has 10 columns.
**How to avoid:** Update colspan to 10 in both HTML template and JS empty-state rendering.
**Warning signs:** Visual misalignment in empty state.

### Pitfall 4: Available Nodes Missing GPU Data Display
**What goes wrong:** GPU Vendor/Model columns show "null" or empty for available nodes.
**Why it happens:** `AdminNodeResponse` returns `gpu_vendor: str | None`. JS renders `null` as text "null".
**How to avoid:** Use `node.gpu_vendor || "---"` with em-dash fallback for null/empty values.
**Warning signs:** "null" appearing as text in table cells.

### Pitfall 5: Test Assertions on Column Count
**What goes wrong:** Existing tests assert 8 column headers; phase changes to 10.
**Why it happens:** `test_contains_all_eight_column_headers` in `test_dashboard.py` has hardcoded header list.
**How to avoid:** Update the test to assert the new 10-column header list with "GPU Vendor", "GPU Model", and "State" replacing "Status".
**Warning signs:** Test failures on the first run.

## Code Examples

### Rendering a Node Row (updated for 10 columns)

```javascript
// [VERIFIED: pattern from existing dashboard.js refreshDashboard()]
function renderNodeRow(node, perNode) {
  const tr = document.createElement("tr");
  
  // 1. Node ID
  appendCell(tr, node.node_id);
  // 2. GPU Vendor (em-dash fallback for null)
  appendCell(tr, node.gpu_vendor || "—");
  // 3. GPU Model
  appendCell(tr, node.gpu_model || "—");
  // 4. Endpoint
  appendCell(tr, node.endpoint || "—");
  // 5. Model
  appendCell(tr, node.model || "—");
  // 6. State (badge)
  appendBadgeCell(tr, node.state, `badge-${node.state}`);
  // 7. Active Connections
  appendCell(tr, node.state === "available" ? "—" : node.active_connections);
  // 8. Circuit Breaker (badge)
  if (node.state === "available") {
    appendCell(tr, "—");
  } else {
    appendBadgeCell(tr, node.circuit_breaker_state, `badge-${node.circuit_breaker_state}`);
  }
  // 9. Requests
  appendCell(tr, node.state === "available" ? "—" : (perNode[node.node_id] || 0));
  // 10. Actions
  appendActionsCell(tr, node);
  
  return tr;
}
```

### QUADS Status Badge Rendering

```javascript
// [VERIFIED: poller.py exposes last_sync and consecutive_failures]
function renderQuadsStatus(data) {
  const el = document.getElementById("quads-status");
  const badge = document.createElement("span");
  badge.className = "badge";
  
  if (data.status === "connected") {
    badge.className += " badge-healthy";
    const ago = relativeTime(data.last_sync);
    badge.textContent = `QUADS: connected — ${ago} ago`;
  } else if (data.status === "stale") {
    badge.className += " badge-draining";
    const ago = relativeTime(data.last_sync);
    badge.textContent = `QUADS: stale — last sync ${ago} ago`;
  } else {
    badge.className += " badge-unhealthy";
    badge.textContent = "QUADS: unavailable";
  }
  
  el.innerHTML = "";
  el.appendChild(badge);
}

function relativeTime(isoString) {
  if (!isoString) return "";
  const diffMs = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  return `${hours}h`;
}
```

### New CSS Classes

```css
/* [VERIFIED: follows existing badge and button patterns in dashboard.css] */

/* Badge for available state (D-02) */
.badge-available {
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
}

/* Action button variants (D-06) */
.btn-setup { color: #3b82f6; border-color: #3b82f6; }
.btn-setup:hover:not(:disabled) { background: #3b82f6; color: #fff; }

.btn-teardown { color: #f87171; border-color: #f87171; }
.btn-teardown:hover:not(:disabled) { background: #f87171; color: #fff; }

.btn-retry { color: #fbbf24; border-color: #fbbf24; }
.btn-retry:hover:not(:disabled) { background: #fbbf24; color: #fff; }

.btn-cancel { color: #f87171; border-color: #f87171; }
.btn-cancel:hover:not(:disabled) { background: #f87171; color: #fff; }

.btn-force-teardown { color: #f87171; border-color: #f87171; }
.btn-force-teardown:hover:not(:disabled) { background: #f87171; color: #fff; }
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + FastAPI TestClient |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/api/test_dashboard.py tests/api/test_admin.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | Unified table with 10 column headers | unit | `uv run pytest tests/api/test_dashboard.py::TestDashboardTableStructure -x` | Exists (needs update) |
| DASH-02 | Action buttons per node state | unit | `uv run pytest tests/api/test_dashboard.py -x` | Exists (needs new test class) |
| DASH-03 | Setup form removed, manual toggle present | unit | `uv run pytest tests/api/test_dashboard.py::TestSetupForm -x` | Exists (needs update) |
| DASH-04 | QUADS status endpoint returns staleness | unit | `uv run pytest tests/api/test_admin.py::TestQuadsStatus -x` | Needs creation |
| DASH-05 | GPU info visible in node list | unit | `uv run pytest tests/api/test_admin.py::TestUnifiedNodeList -x` | Exists (already tests gpu fields) |

### Wave 0 Gaps
- [ ] `tests/api/test_admin.py::TestQuadsStatus` -- covers DASH-04 (new endpoint)
- [ ] Update `tests/api/test_dashboard.py::TestDashboardTableStructure` -- 10 columns, "State" replaces "Status"
- [ ] Update `tests/api/test_dashboard.py::TestSetupForm` -- standalone form removed, toggle link present

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Internal network only, no auth in v1 |
| V3 Session Management | No | Stateless proxy, no sessions |
| V4 Access Control | No | Admin endpoints internal-only |
| V5 Input Validation | Yes | Pydantic model validates `SetupRequest.hostname` (existing) |
| V6 Cryptography | No | No secrets in this phase |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via node_id or hostname in table | Tampering | `textContent` (not `innerHTML`) for all user-facing data -- already the pattern in dashboard.js |
| CSRF on setup/teardown | Tampering | Internal network only, no auth -- accepted risk per project constraints |

The existing codebase uses `textContent` for all DOM text insertion, which prevents XSS. The phase must continue this pattern and never use `innerHTML` for dynamic data. [VERIFIED: codebase inspection of dashboard.js]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Staleness thresholds: connected=0 failures, stale=1-2, unavailable=3+ | Architecture Patterns (Pattern 2) | Badge shows wrong status; easy to adjust thresholds |
| A2 | Separate `/admin/quads/status` endpoint preferred over embedding in `/admin/nodes` | Architecture Patterns | Minor refactor if user prefers embedding; UI-SPEC recommends separate endpoint |
| A3 | Only unhealthy state has 2+ actions requiring dropdown | Architecture Patterns (Pattern 3) | If other states get multiple actions, dropdown code already handles it generically |

## Open Questions

1. **Force teardown query parameter**
   - What we know: `DELETE /admin/nodes/{id}?force=true` is the existing endpoint signature.
   - What's unclear: Should force teardown have a different confirmation message from regular teardown?
   - Recommendation: Use distinct confirmation copy per UI-SPEC: "Force teardown {node_id}? This will immediately stop the container without draining."

2. **QUADS status when QUADS is not configured**
   - What we know: When `quads_poller is None`, the endpoint returns `status: "unavailable"`.
   - What's unclear: Should the QUADS badge be hidden entirely when QUADS is not configured, or show "unavailable"?
   - Recommendation: Show "unavailable" -- it is accurate and requires no special-casing in JS.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `dashboard.html`, `dashboard.js`, `dashboard.css` -- current DOM patterns, CSS classes, JS handlers
- Codebase inspection: `api/admin.py`, `models/admin.py` -- existing endpoints and response models
- Codebase inspection: `services/unified_nodes.py` -- `_STATE_ACTIONS` mapping, `AdminNodeResponse` fields
- Codebase inspection: `quads/poller.py` -- `last_sync`, `consecutive_failures` properties
- Codebase inspection: `config/dependencies.py` -- `get_quads_poller` dependency already exists
- Codebase inspection: `tests/` -- existing test patterns and fixtures

### Secondary (MEDIUM confidence)
- Phase 18 UI-SPEC (`18-UI-SPEC.md`) -- design contract for visual and interaction behavior

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new packages, all patterns exist in codebase
- Architecture: HIGH -- extending existing patterns, one trivial new endpoint
- Pitfalls: HIGH -- all identified from codebase inspection of existing code

**Research date:** 2026-07-17
**Valid until:** 2026-08-17 (stable -- no external dependencies to drift)
