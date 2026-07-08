# Phase 14: Dashboard Operations - Context

**Gathered:** 2026-07-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Operators can trigger and monitor setup/teardown from the web dashboard. Adds a setup form (hostname input), teardown buttons per node, and a provisioning tasks panel to the existing Jinja2+vanilla JS dashboard. No backend changes — Phase 13 admin API endpoints already exist. This is purely frontend: HTML, CSS, JS additions to the existing dashboard.

</domain>

<decisions>
## Implementation Decisions

### Setup Form
- **D-01:** Inline form above the node fleet table. Always visible — no toggle, no modal. Simple hostname text input + "Setup" button.
- **D-02:** Hostname-only input. No model override or GPU count fields. GPU auto-detection and model selection happen on the remote host via setup.sh (per PROV-03).
- **D-03:** On submit: disable button for ~2 seconds, flash "Setup started for {hostname}" confirmation, then re-enable. Prevents double-submit.
- **D-04:** Client-side validation: non-empty check only. Backend handles SSH reachability via preflight. No hostname regex.

### Progress Display
- **D-05:** Separate "Provisioning Tasks" panel below the node fleet table. Lists active/recent tasks with hostname, current step, status badge, and timestamp.
- **D-06:** Current step + status badge per task row. No step progress bar. Satisfies DASH-03 ("per-step status") with minimal DOM manipulation.
- **D-07:** Completed/failed tasks stay visible. They persist in etcd until the next operation on that host overwrites them (per Phase 13 D-07). No client-side filtering.
- **D-08:** Tasks panel polls on the same interval as the node table. Add `/admin/provisioning/tasks` to the existing `Promise.all` in `refreshDashboard()`. One timer, one refresh function.

### Teardown Button
- **D-09:** New "Actions" column in the node fleet table. Each row gets a "Teardown" button. Matches DASH-02 requirement.
- **D-10:** `window.confirm()` dialog before teardown. Message: "Teardown node {id}? This will drain connections and stop the container." Zero extra UI.
- **D-11:** Force teardown is API-only — not exposed in dashboard UI. Dashboard always triggers graceful teardown. Power users use `DELETE /admin/nodes/{id}?force=true` directly.
- **D-12:** Teardown button disabled when node status is PROVISIONING or DRAINING. Prevents conflicting operations. Re-enables on next poll cycle when state changes.

### Claude's Discretion
- CSS styling for setup form, tasks panel, and action buttons (follow existing simple.css + dashboard.css patterns)
- Status badge colors for provisioning steps (extend existing badge pattern)
- Tasks panel empty state text
- Error display when POST /admin/nodes/setup or DELETE /admin/nodes/{id} returns non-2xx

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Dashboard Code (what gets extended)
- `inference_proxy/templates/dashboard.html` — Jinja2 template with node fleet table, poll_interval injection
- `inference_proxy/static/js/dashboard.js` — refreshDashboard() with Promise.all fetch pattern, DOM table rendering
- `inference_proxy/static/css/dashboard.css` — Badge styles, status colors, layout utilities
- `inference_proxy/api/dashboard.py` — dashboard_router, Jinja2Templates setup

### Admin API (endpoints to call from JS)
- `inference_proxy/api/admin.py` — POST /admin/nodes/setup, DELETE /admin/nodes/{id}, GET /admin/provisioning/tasks
- `inference_proxy/models/admin.py` — SetupRequest, SetupResponse, TeardownResponse, TaskStatusResponse

### State and Status Models
- `inference_proxy/provisioning/state.py` — ProvisioningStep enum (all setup + teardown steps), ProvisioningState model
- `inference_proxy/models/node.py` — NodeStatus enum (HEALTHY, UNHEALTHY, DRAINING, PROVISIONING, UNKNOWN)

### Project Context
- `.planning/ROADMAP.md` — Phase 14 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — DASH-01, DASH-02, DASH-03 requirement definitions
- `.planning/phases/13-teardown-and-admin-api/13-CONTEXT.md` — Phase 13 decisions (admin API design, task tracking, drain behavior)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `refreshDashboard()` in dashboard.js — existing Promise.all pattern for parallel API fetches; extend with /admin/provisioning/tasks
- Badge CSS classes (`.badge-healthy`, `.badge-unhealthy`, `.badge-draining`) — extend for provisioning step states
- `POLL_INTERVAL_MS` — already injected by Jinja2 from settings.dashboard.poll_interval
- Simple.css — external CSS framework already loaded, provides form styling out of the box

### Established Patterns
- Jinja2 renders HTML shell, JS fetches data and builds DOM — no server-side rendering of dynamic content
- `document.createElement()` for table rows — no innerHTML templates, no framework
- Status badges with `badge-{status}` CSS class convention
- Poll-based refresh via `setInterval(refreshDashboard, POLL_INTERVAL_MS)`

### Integration Points
- `dashboard.html` — add form section above table, tasks panel section below table, Actions column header
- `dashboard.js` — add /admin/provisioning/tasks to Promise.all, add form submit handler, add teardown click handler, add tasks panel rendering
- `dashboard.css` — add styles for form, tasks panel, action buttons, provisioning step badges
- `tests/api/test_dashboard.py` — extend with tests for new dashboard elements

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

*Phase: 14-Dashboard Operations*
*Context gathered: 2026-07-08*
