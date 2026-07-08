# Phase 14: Dashboard Operations - Research

**Researched:** 2026-07-08
**Domain:** Frontend (Jinja2 + vanilla JavaScript + CSS)
**Confidence:** HIGH

## Summary

Phase 14 is a frontend-only phase. The backend is complete (Phase 13 delivered POST /admin/nodes/setup, DELETE /admin/nodes/{id}, GET /admin/provisioning/tasks). This phase adds three UI elements to the existing Jinja2+vanilla JS dashboard: (1) a setup form with hostname input, (2) teardown buttons per node row, (3) a provisioning tasks panel. No new packages, no backend changes, no framework adoption.

The existing codebase establishes clear patterns: Jinja2 renders an HTML shell, `refreshDashboard()` fetches JSON from `/admin/*` endpoints via `Promise.all`, and `document.createElement()` builds DOM rows. All three additions follow these patterns directly. The tasks panel piggybacks on the existing poll interval by adding `/admin/provisioning/tasks` to the existing `Promise.all` fetch group.

**Primary recommendation:** Extend the existing three files (dashboard.html, dashboard.js, dashboard.css) following established DOM-building and badge patterns. No abstractions, no templating libraries, no build tools.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Inline form above the node fleet table. Always visible -- no toggle, no modal. Simple hostname text input + "Setup" button.
- **D-02:** Hostname-only input. No model override or GPU count fields.
- **D-03:** On submit: disable button for ~2 seconds, flash "Setup started for {hostname}" confirmation, then re-enable. Prevents double-submit.
- **D-04:** Client-side validation: non-empty check only. Backend handles SSH reachability via preflight. No hostname regex.
- **D-05:** Separate "Provisioning Tasks" panel below the node fleet table. Lists active/recent tasks with hostname, current step, status badge, and timestamp.
- **D-06:** Current step + status badge per task row. No step progress bar.
- **D-07:** Completed/failed tasks stay visible. They persist in etcd until the next operation on that host overwrites them.
- **D-08:** Tasks panel polls on the same interval as the node table. Add `/admin/provisioning/tasks` to the existing `Promise.all` in `refreshDashboard()`. One timer, one refresh function.
- **D-09:** New "Actions" column in the node fleet table. Each row gets a "Teardown" button.
- **D-10:** `window.confirm()` dialog before teardown. Message: "Teardown node {id}? This will drain connections and stop the container."
- **D-11:** Force teardown is API-only -- not exposed in dashboard UI. Dashboard always triggers graceful teardown.
- **D-12:** Teardown button disabled when node status is PROVISIONING or DRAINING. Prevents conflicting operations.

### Claude's Discretion
- CSS styling for setup form, tasks panel, and action buttons (follow existing simple.css + dashboard.css patterns)
- Status badge colors for provisioning steps (extend existing badge pattern)
- Tasks panel empty state text
- Error display when POST /admin/nodes/setup or DELETE /admin/nodes/{id} returns non-2xx

### Deferred Ideas (OUT OF SCOPE)
None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | Dashboard has a setup form where operator enters hostname and triggers setup | D-01 through D-04 lock the form design. HTML form in dashboard.html, submit handler in dashboard.js, POST to /admin/nodes/setup. |
| DASH-02 | Each node row has a teardown button | D-09 through D-12 lock the button design. Actions column in node table, DELETE to /admin/nodes/{id}, window.confirm() guard. |
| DASH-03 | Dashboard displays setup/teardown progress with per-step status | D-05 through D-08 lock the tasks panel. Fetch /admin/provisioning/tasks in existing Promise.all, render task rows with step badge. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Setup form UI | Browser / Client | -- | Pure DOM: input + button + fetch POST |
| Teardown button | Browser / Client | -- | Button click + fetch DELETE, confirm dialog |
| Tasks panel rendering | Browser / Client | -- | Fetch GET + DOM table build on poll interval |
| Setup/teardown execution | API / Backend (Phase 13) | -- | Already built. JS only calls the endpoints. |
| Task state persistence | Database / Storage (etcd) | -- | Already built. GET /admin/provisioning/tasks reads from etcd. |

## Standard Stack

No new libraries. This phase uses only what is already loaded in `dashboard.html`:

| Asset | Already Loaded | Purpose |
|-------|---------------|---------|
| Simple.css (CDN) | Yes | Base form styling -- `<input>`, `<button>` styled automatically |
| dashboard.css | Yes | Badge classes, layout utilities |
| dashboard.js | Yes | `refreshDashboard()`, `Promise.all`, DOM building |
| Jinja2 templates | Yes | HTML shell rendering server-side |

**No packages to install. No build step. No package legitimacy audit needed.**

## Architecture Patterns

### System Architecture Diagram

```
[Operator Browser]
      |
      |--- GET /dashboard -----------> [FastAPI: dashboard.py] --renders--> dashboard.html
      |                                                                         |
      |<--- HTML shell + JS + CSS <--------------------------------------------|
      |
      |--- (on load + every POLL_INTERVAL_MS) ---------------------------+
      |    GET /admin/nodes                                              |
      |    GET /admin/metrics             [Promise.all in dashboard.js]  |
      |    GET /admin/provisioning/tasks  <-- NEW fetch added here       |
      |                                                                  |
      |<--- JSON responses <---------------------------------------------+
      |
      |--- JS rebuilds DOM tables + tasks panel from JSON
      |
      |--- (operator clicks "Setup")
      |    POST /admin/nodes/setup {hostname} -----> [admin.py] ---> provisioner.provision()
      |<--- 202 {task_id}
      |
      |--- (operator clicks "Teardown" on node row)
      |    DELETE /admin/nodes/{id} -----> [admin.py] ---> provisioner.teardown()
      |<--- 202 {task_id}
```

### Recommended Project Structure

No new files beyond extending three existing ones:

```
inference_proxy/
├── templates/
│   └── dashboard.html       # EXTEND: add form section, actions column, tasks panel section
├── static/
│   ├── js/
│   │   └── dashboard.js     # EXTEND: add tasks fetch, form handler, teardown handler, tasks renderer
│   └── css/
│       └── dashboard.css    # EXTEND: add form, tasks panel, action button, provisioning badge styles
tests/
└── api/
    └── test_dashboard.py    # EXTEND: add tests for new HTML elements and CSS classes
```

### Pattern 1: Extending refreshDashboard() with Tasks Fetch

**What:** Add `/admin/provisioning/tasks` to the existing `Promise.all` in `refreshDashboard()`.
**When to use:** D-08 requires tasks panel polls on the same interval as nodes.
**Example:**
```javascript
// Current pattern in dashboard.js
const [nodesResp, metricsResp] = await Promise.all([
  fetch("/admin/nodes"),
  fetch("/admin/metrics"),
]);

// Extended pattern -- add tasks fetch
const [nodesResp, metricsResp, tasksResp] = await Promise.all([
  fetch("/admin/nodes"),
  fetch("/admin/metrics"),
  fetch("/admin/provisioning/tasks"),
]);
```
[VERIFIED: inference_proxy/static/js/dashboard.js line 8-11]

### Pattern 2: DOM Table Row Building

**What:** Use `document.createElement()` for building rows, matching the existing node table pattern.
**When to use:** For both the tasks panel rows and the new Actions column cell.
**Example:**
```javascript
// Existing pattern from dashboard.js (lines 30-66)
const tr = document.createElement("tr");
const td = document.createElement("td");
td.textContent = someValue;
tr.appendChild(td);

// Badge pattern (lines 44-48)
const badge = document.createElement("span");
badge.className = `badge badge-${statusValue}`;
badge.textContent = statusValue;
td.appendChild(badge);
```
[VERIFIED: inference_proxy/static/js/dashboard.js lines 30-66]

### Pattern 3: POST/DELETE from Vanilla JS

**What:** Use `fetch()` with method/headers/body for setup and teardown calls.
**When to use:** Setup form submit handler and teardown button click handler.
**Example:**
```javascript
// Setup: POST with JSON body
const resp = await fetch("/admin/nodes/setup", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ hostname: value }),
});

// Teardown: DELETE (no body needed)
const resp = await fetch(`/admin/nodes/${nodeId}`, {
  method: "DELETE",
});
```
[ASSUMED -- standard fetch API usage]

### Pattern 4: Temporary Button Disable (D-03)

**What:** Disable submit button for ~2 seconds after successful setup POST, show confirmation text.
**When to use:** Prevents double-submit per D-03.
**Example:**
```javascript
button.disabled = true;
statusEl.textContent = `Setup started for ${hostname}`;
setTimeout(() => { button.disabled = false; }, 2000);
```
[ASSUMED -- standard setTimeout pattern]

### Anti-Patterns to Avoid
- **innerHTML for dynamic content:** The codebase uses `document.createElement()`. Don't switch to innerHTML templates or string concatenation -- it's inconsistent and opens XSS risk with user-provided hostnames.
- **Separate poll timer for tasks panel:** D-08 explicitly requires tasks panel to share the existing `setInterval(refreshDashboard, POLL_INTERVAL_MS)`. Don't create a second timer.
- **New JS files:** All dashboard JS lives in one file. Don't split into multiple JS files for three simple features.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Form styling | Custom CSS for inputs/buttons | Simple.css auto-styling | Already loaded, handles form elements out of the box |
| Confirmation dialog | Custom modal component | `window.confirm()` | D-10 locks this. Zero extra DOM. |
| Polling | Custom WebSocket or SSE listener | Existing `setInterval` + `fetch` | D-08 locks this. Already works. |

## Common Pitfalls

### Pitfall 1: Race Between Setup POST and Next Poll

**What goes wrong:** Operator clicks "Setup", the POST returns 202 immediately, but the next poll cycle fires before the provisioner has written the task state to etcd. Tasks panel shows nothing.
**Why it happens:** POST /admin/nodes/setup fires `provisioner.provision()` as a background task. The first etcd write (PENDING state) may take a moment.
**How to avoid:** Accept this as expected behavior. The task will appear on the next poll cycle. D-03's "Setup started for {hostname}" flash message provides immediate feedback. No need to force-refresh.
**Warning signs:** Task doesn't appear in panel for 1-2 poll cycles after setup. This is normal, not a bug.

### Pitfall 2: Stale Button State After Teardown

**What goes wrong:** Teardown button stays enabled after clicking if the poll hasn't refreshed yet. Operator could double-click.
**Why it happens:** The `DELETE` returns 202 immediately but the node status doesn't change to DRAINING until the provisioner writes to etcd and the watcher propagates.
**How to avoid:** Immediately disable the teardown button in the click handler after the DELETE succeeds. The next poll cycle will rebuild the entire table (including button states from fresh data).
**Warning signs:** Clicking teardown twice on the same node before the poll fires.

### Pitfall 3: Column Count Mismatch

**What goes wrong:** Adding the "Actions" column header (th) to the table head but forgetting to add the corresponding td in the JS row-building loop. Or the "No nodes registered" colspan is wrong.
**Why it happens:** The current table has 7 columns (colspan="7" in the empty state). Adding Actions makes it 8.
**How to avoid:** Update the colspan from 7 to 8 in both the HTML template default row and the JS empty-state branch.
**Warning signs:** Misaligned table cells or "No nodes registered" not spanning full width.

### Pitfall 4: Tasks Panel Error Swallowing

**What goes wrong:** If `/admin/provisioning/tasks` returns non-2xx (e.g., etcd is down), the entire `refreshDashboard()` catch block fires, making it look like the node table also failed.
**Why it happens:** All three fetches are in one `Promise.all`. One failure rejects the whole group.
**How to avoid:** Check each response individually before parsing JSON. The existing pattern already does `if (!nodesResp.ok) throw new Error(...)` per response. Continue this pattern for tasksResp. Consider letting the tasks panel degrade gracefully (show "Tasks unavailable") without failing the node table update.
**Warning signs:** Node table stops updating when etcd has transient issues.

## Code Examples

### API Response Shapes (from existing admin.py models)

**GET /admin/provisioning/tasks** returns:
```json
[
  {
    "hostname": "gpu01",
    "current_step": "nvidia_driver",
    "started_at": "2026-07-08T10:00:00Z",
    "updated_at": "2026-07-08T10:05:00Z",
    "failed_step": null,
    "error": null
  }
]
```
[VERIFIED: inference_proxy/models/admin.py TaskStatusResponse]

**POST /admin/nodes/setup** accepts `{"hostname": "gpu01"}`, returns 202:
```json
{"task_id": "gpu01"}
```
[VERIFIED: inference_proxy/api/admin.py lines 78-85]

**DELETE /admin/nodes/{id}** returns 202:
```json
{"task_id": "gpu01"}
```
[VERIFIED: inference_proxy/api/admin.py lines 103-114]

### ProvisioningStep Enum Values (for badge CSS classes)

All possible `current_step` values from `ProvisioningStep`:
```
pending, preflight, nvidia_repo, system_update, nvidia_driver, nvidia_cdi,
nfs_mount, firewall, starting_vllm, health_poll, registering,
draining, stopping_container, deregistering, teardown_complete,
complete, failed
```
[VERIFIED: inference_proxy/provisioning/state.py lines 19-37]

Terminal states: `complete`, `teardown_complete`, `failed`.
In-progress states: everything else.

### Badge Color Mapping Strategy

Extend existing badge CSS convention (`badge-{status}`):

```css
/* Existing pattern */
.badge-healthy, .badge-closed { background-color: #16a34a; color: #fff; }  /* green */
.badge-unhealthy, .badge-open { background-color: #dc2626; color: #fff; }  /* red */
.badge-draining, .badge-half_open, .badge-unknown { background-color: #ca8a04; color: #fff; }  /* amber */

/* New provisioning step badges -- three categories: */
/* GREEN (success): complete, teardown_complete */
/* RED (failure): failed */
/* BLUE (in-progress): all other steps */
```
[VERIFIED: inference_proxy/static/css/dashboard.css existing badge classes]

A single `.badge-in-progress` class (blue) for all non-terminal steps is cleaner than 13 individual step classes. Terminal states reuse existing green/red patterns.

### NodeStatus Values That Disable Teardown (D-12)

```javascript
const disableStatuses = ["provisioning", "draining"];
button.disabled = disableStatuses.includes(node.status);
```
[VERIFIED: inference_proxy/models/node.py NodeStatus enum -- PROVISIONING="provisioning", DRAINING="draining"]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| innerHTML string templates | document.createElement() | Established in Phase 9 | Consistent with codebase, safer against XSS |
| Separate polling per panel | Single Promise.all in refreshDashboard() | Established in Phase 9 | One timer, one refresh, atomic update |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | fetch() with method/headers/body for POST/DELETE is the correct vanilla JS pattern | Code Examples | Near-zero risk -- this is standard Web API |
| A2 | setTimeout for 2-second button disable is sufficient for D-03 | Code Examples | Low risk -- could use a flag instead but effect is identical |
| A3 | Simple.css auto-styles form inputs and buttons without extra classes | Don't Hand-Roll | Low risk -- easily verified by rendering; fallback is minimal custom CSS |

## Open Questions

None. This phase is well-constrained by CONTEXT.md decisions and the existing codebase patterns. All three requirements (DASH-01, DASH-02, DASH-03) have clear implementation paths.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + FastAPI TestClient |
| Config file | pyproject.toml |
| Quick run command | `uv run pytest tests/api/test_dashboard.py -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | Setup form HTML elements present in dashboard | unit | `uv run pytest tests/api/test_dashboard.py -x -k "setup_form"` | Extend existing |
| DASH-02 | Actions column header present in dashboard table | unit | `uv run pytest tests/api/test_dashboard.py -x -k "actions_column"` | Extend existing |
| DASH-03 | Tasks panel HTML section present, badge CSS classes for provisioning steps exist | unit | `uv run pytest tests/api/test_dashboard.py -x -k "tasks_panel or provisioning_badge"` | Extend existing |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/api/test_dashboard.py -x`
- **Per wave merge:** `uv run pytest -x`
- **Phase gate:** Full suite green before /gsd:verify-work

### Wave 0 Gaps
None -- existing test infrastructure (tests/api/test_dashboard.py, conftest.py with client fixture) covers all needed patterns. New tests extend the existing file.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Internal network only, no auth in v1 |
| V3 Session Management | No | Stateless dashboard |
| V4 Access Control | No | Internal network only |
| V5 Input Validation | Yes | Non-empty hostname check client-side; backend validates via SSH preflight |
| V6 Cryptography | No | No secrets handled in frontend |

### Known Threat Patterns for Vanilla JS Dashboard

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via hostname display | Tampering | Use `textContent` (not `innerHTML`) for all user-provided values. Already established pattern. |
| CSRF on setup/teardown | Tampering | Internal network only mitigates. SameSite cookies not applicable (no auth). |
| Double-submit on setup | Tampering | D-03 button disable + 2s timeout. |

## Sources

### Primary (HIGH confidence)
- `inference_proxy/static/js/dashboard.js` -- existing DOM-building and fetch patterns
- `inference_proxy/static/css/dashboard.css` -- existing badge CSS class convention
- `inference_proxy/templates/dashboard.html` -- existing HTML structure and Jinja2 patterns
- `inference_proxy/api/admin.py` -- admin API endpoints (Phase 13 output)
- `inference_proxy/models/admin.py` -- TaskStatusResponse, SetupRequest, SetupResponse, TeardownResponse
- `inference_proxy/provisioning/state.py` -- ProvisioningStep enum values
- `inference_proxy/models/node.py` -- NodeStatus enum values (PROVISIONING, DRAINING)
- `tests/api/test_dashboard.py` -- existing test patterns for dashboard HTML assertions
- `.planning/phases/14-dashboard-operations/14-CONTEXT.md` -- all D-01 through D-12 decisions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, extending existing patterns only
- Architecture: HIGH -- all patterns verified from codebase, endpoints verified from Phase 13 code
- Pitfalls: HIGH -- derived from reading the actual code flow (Promise.all rejection, colspan, button state)

**Research date:** 2026-07-08
**Valid until:** 2026-08-08 (stable -- no moving parts, all patterns are codebase-internal)
