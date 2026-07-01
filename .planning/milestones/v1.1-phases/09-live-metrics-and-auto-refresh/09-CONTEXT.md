# Phase 9: Live Metrics and Auto-Refresh - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Add per-node request counts to the existing dashboard node table and JS polling so the page stays current without manual refresh. The dashboard already renders a node fleet table via client-side fetch; this phase adds a "Requests" column populated from `/admin/metrics` and a `setInterval` polling loop that re-fetches both endpoints.

</domain>

<decisions>
## Implementation Decisions

### Metrics Display
- **D-01:** Per-node request counts appear as a new column ("Requests") in the existing node fleet table. No separate metrics section.
- **D-02:** No aggregate total or per-model counts shown on the dashboard — just per-node in the table. Total is implicit (sum the column).

### Polling Configuration
- **D-03:** Polling interval is a backend env var (`INFERENCE_PROXY_DASHBOARD__POLL_INTERVAL`) injected into the Jinja2 template as a JS variable. No UI control on the page.
- **D-04:** Default polling interval is 10 seconds.
- **D-05:** Each poll cycle fetches both `/admin/nodes` and `/admin/metrics` in parallel (two fetches). Existing endpoints stay unchanged — no new fields on `AdminNodeResponse`.

### Refresh UX
- **D-06:** Dashboard shows a "Last updated: HH:MM:SS" timestamp that updates on each successful poll.
- **D-07:** On poll failure, keep the last successful data on screen and show a subtle warning (e.g. "Update failed — retrying...") that clears on next success. Do not replace the table with an error state.

### Claude's Discretion
- Where to place the "Last updated" text (header, footer, or near the table)
- Exact warning text and styling for poll failure state
- Whether to add the new setting to DashboardSettings sub-model or extend an existing settings group

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Dashboard (extend this)
- `inference_proxy/templates/dashboard.html` — Jinja2 template to add Requests column and polling interval JS variable
- `inference_proxy/static/js/dashboard.js` — Existing `loadNodes()` fetch logic to extend with metrics fetch + polling loop
- `inference_proxy/static/css/dashboard.css` — Badge styles; may need styles for last-updated text and warning state
- `inference_proxy/api/dashboard.py` — Dashboard route that renders the template (inject poll interval here)

### Admin API (data sources)
- `inference_proxy/api/admin.py` — `/admin/nodes` and `/admin/metrics` endpoints the polling JS will call
- `inference_proxy/models/admin.py` — `AdminNodeResponse` (6 fields) and `AdminMetricsResponse` (total_requests, per_model, per_node)

### Metrics Data Layer
- `inference_proxy/routing/request_metrics.py` — `RequestMetrics` class with `get_per_node()` returning `dict[str, int]`

### Configuration
- `inference_proxy/config/settings.py` — `Settings` root with sub-models; add poll interval setting here

### Application Wiring
- `inference_proxy/main.py` — `create_app()` factory, router registration, lifespan setup
- `inference_proxy/config/dependencies.py` — DI pattern via `app.state`

### Requirements
- `.planning/REQUIREMENTS.md` — METR-02, DASH-02

### Prior Phase Context
- `.planning/phases/08-dashboard-and-node-fleet/08-CONTEXT.md` — Phase 8 decisions (dashboard structure this phase extends)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `loadNodes()` in `dashboard.js`: Existing fetch-and-render pattern — polling loop wraps this with `setInterval`
- `AdminMetricsResponse.per_node`: `dict[str, int]` keyed by node_id — maps directly to the new table column
- Badge CSS classes: Established pattern for colored pills — reusable for any new visual indicators

### Established Patterns
- Client-side fetch → DOM manipulation (no framework, no template engine in JS)
- Settings via pydantic-settings sub-models with `INFERENCE_PROXY_` env prefix and `__` nested delimiter
- Jinja2 template variables injected from the route handler

### Integration Points
- `dashboard.html` `<thead>`: Add "Requests" column header
- `dashboard.js` `loadNodes()`: Parallel-fetch `/admin/metrics`, match `per_node[node_id]` to table rows
- `dashboard.js`: New `startPolling(intervalMs)` that calls `loadNodes()` (or a combined refresh function) on a `setInterval`
- `settings.py`: New setting for poll interval (integer, seconds)
- `dashboard.py` route handler: Pass `poll_interval` to template context
- `dashboard.html`: `<script>` block or data attribute to inject poll interval from Jinja2

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-live-metrics-and-auto-refresh*
*Context gathered: 2026-07-01*
