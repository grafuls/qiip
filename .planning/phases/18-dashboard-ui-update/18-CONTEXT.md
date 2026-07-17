# Phase 18: Dashboard UI Update - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Dashboard displays the unified node list with inline provisioning controls. Consumes the Phase 17 `GET /admin/nodes` API returning `AdminNodeResponse` with `state`, `actions`, `gpu_vendor`, `gpu_model`, `gpu_count`. Removes the standalone setup form. Adds a QUADS connection status indicator. All changes are in the frontend layer (HTML template, JS, CSS) with one small backend addition for QUADS staleness data. No new API routes for node operations — all existing endpoints are consumed as-is.

</domain>

<decisions>
## Implementation Decisions

### Table Column Layout
- **D-01:** Keep the current table structure with all columns visible for all rows. Add GPU Vendor and GPU Model columns after Node ID. Column order: Node ID → GPU Vendor → GPU Model → Endpoint → Model → State → Active Connections → Circuit Breaker → Requests → Actions.
- **D-02:** Replace the "Status" column with "State" — show the unified state from Phase 17 (`available`, `healthy`, `unhealthy`, `provisioning`, `draining`). Remove the raw etcd status column.
- **D-03:** Available nodes show em-dash (—) in cells that don't apply (endpoint, model, connections, circuit breaker, requests). Consistent with the existing task table pattern.

### Manual Hostname Fallback
- **D-04:** Remove the standalone "Provision Node" card. Add a "Manual setup" toggle link below the Node Fleet card title that expands an inline input row (hostname text input + Setup button).
- **D-05:** Toggle is a simple text link ("+ Manual setup") that toggles visibility with vanilla JS display toggle. No animation, no `<details>` element.

### Action Button Styling
- **D-06:** Color-coded by intent: Setup = blue/accent (positive), Teardown = red outline (destructive), Retry = amber/yellow (recovery), Cancel = red, Force Teardown = red. Matches existing badge color conventions in the CSS.
- **D-07:** Confirmation dialogs (`window.confirm`) required for all destructive actions: Teardown, Force Teardown, and Cancel. Setup and Retry fire without confirmation.
- **D-08:** When a node has multiple actions (e.g. unhealthy has teardown + retry), show the primary action as a button and secondary actions in a small dropdown/menu. Primary action = first item in the `actions` list from the API.

### QUADS Status Indicator
- **D-09:** QUADS connection status (connected/stale/unavailable) with cache age displayed in the dashboard header alongside the existing "Last updated" text. Uses a badge with color matching the status.
- **D-10:** Backend: expose QUADS poller staleness via a new field on an existing endpoint or a lightweight dedicated endpoint. The poller already tracks `last_sync` and `consecutive_failures`.

### Claude's Discretion
- Exact wording and icon for the QUADS status badge
- Staleness thresholds (what defines "stale" vs "unavailable") — align with poller's `consecutive_failures`
- Whether QUADS status comes from a new `/admin/quads/status` endpoint or is embedded in the `/admin/nodes` response
- Dropdown/menu implementation details for secondary actions
- CSS class naming for new action button variants
- How to wire the Setup action from inline buttons through the existing `POST /admin/nodes/setup` endpoint

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Dashboard Files (what gets modified)
- `inference_proxy/templates/dashboard.html` — Jinja2 template with node table, setup form, tasks panel
- `inference_proxy/static/js/dashboard.js` — Vanilla JS: refreshDashboard(), handleTeardown(), setup form handler, toast notifications
- `inference_proxy/static/css/dashboard.css` — Dark theme styles, badge classes, table styling, toast system

### Admin API (data contract consumed by dashboard)
- `inference_proxy/api/admin.py` — GET /admin/nodes (unified list), POST /admin/nodes/setup, DELETE /admin/nodes/{node_id}, GET /admin/provisioning/tasks
- `inference_proxy/models/admin.py` — AdminNodeResponse with state, actions, gpu_vendor, gpu_model, gpu_count fields
- `inference_proxy/services/unified_nodes.py` — UnifiedNodeService with _STATE_ACTIONS mapping and merge logic

### QUADS Staleness (data for status indicator)
- `inference_proxy/quads/poller.py` — QUADSPoller with `last_sync` and `consecutive_failures` properties

### Prior Phase Context
- `.planning/phases/17-unified-node-list-and-admin-api/17-CONTEXT.md` — D-04 (extended AdminNodeResponse), D-06 (actions list = single source of truth), D-07 (action mapping)
- `.planning/ROADMAP.md` — Phase 18 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — DASH-01 through DASH-05 requirement definitions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `showToast(message, type)` — Toast notification system for action feedback
- `handleTeardown(nodeId)` — Existing teardown handler pattern (confirm + fetch + toast)
- Badge CSS classes — `.badge-healthy`, `.badge-unhealthy`, `.badge-provisioning`, `.badge-draining` already exist
- `refreshDashboard()` — Polling loop that fetches nodes + metrics + tasks in parallel
- `_STATE_ACTIONS` mapping in `unified_nodes.py` — Canonical action-to-state reference

### Established Patterns
- Vanilla JS DOM construction (createElement + appendChild) for table rows
- `setInterval(refreshDashboard, POLL_INTERVAL_MS)` for auto-refresh
- `window.confirm()` for destructive action confirmation
- Badge-based status display with color-coded CSS classes
- `fetch()` with JSON body for POST requests, simple DELETE for teardown

### Integration Points
- `refreshDashboard()` — must be updated to render new columns (GPU, State) and action buttons from `node.actions`
- Setup form handler — rewire to work from both inline buttons and manual fallback input
- CSS — add new badge class for "available" state, new button color variants for action types
- Dashboard header — add QUADS status indicator element

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

*Phase: 18-Dashboard UI Update*
*Context gathered: 2026-07-17*
