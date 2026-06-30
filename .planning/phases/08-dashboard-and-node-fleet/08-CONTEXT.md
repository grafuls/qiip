# Phase 8: Dashboard and Node Fleet - Context

**Gathered:** 2026-06-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Jinja2-rendered operations dashboard served at `/dashboard` by the existing FastAPI app. Displays a node fleet table with all registered nodes and their operational state. No auto-refresh in this phase (Phase 9 adds polling).

</domain>

<decisions>
## Implementation Decisions

### Dashboard Route & Data
- **D-01:** Dashboard served at `/dashboard` — dedicated path, separate from `/admin/*` JSON API.
- **D-02:** Client-side fetch — serve an HTML shell, then JS fetches `/admin/nodes` on page load to populate the table. Phase 9 polling reuses the same fetch logic.

### Node Status Styling
- **D-03:** Color badges (pill/badge) next to the status text — green for healthy, red for unhealthy, yellow for draining.
- **D-04:** Circuit breaker state also gets color badges — green/closed, red/open, yellow/half-open. Same visual language as node status.

### CSS Approach
- **D-05:** Use Simple.css classless library for base styling — semantic HTML gets instant polish with no design effort.
- **D-06:** Load Simple.css from CDN (`<link>` tag). Small override CSS for badges only.

### Claude's Discretion
- Page layout and structure — Claude decides information hierarchy (summary header vs pure table, page title, etc.)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Admin API (data source for dashboard)
- `inference_proxy/api/admin.py` — `/admin/nodes` and `/admin/metrics` endpoints the dashboard JS will fetch
- `inference_proxy/models/admin.py` — `AdminNodeResponse` (6 fields: node_id, endpoint, model, status, active_connections, circuit_breaker_state) and `AdminMetricsResponse`

### Application Wiring
- `inference_proxy/main.py` — `create_app()` factory, router registration, lifespan setup — dashboard router mounts here
- `inference_proxy/config/dependencies.py` — Dependency injection pattern via `app.state`

### Requirements
- `.planning/REQUIREMENTS.md` — DASH-01, DASH-03, NODE-01, NODE-02, TMPL-01, TMPL-02

### Prior Phase Context
- `.planning/phases/07-request-metrics-and-admin-api/07-CONTEXT.md` — Phase 7 decisions (metrics data layer this dashboard consumes)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `AdminNodeResponse`: Pydantic model with all 6 fields the dashboard table needs — JS fetches this as JSON
- `AdminMetricsResponse`: Total and per-dimension request counts — available for Phase 9
- `admin_router`: Existing `/admin` APIRouter pattern for JSON endpoints

### Established Patterns
- Router registration via `app.include_router()` in `main.py`
- Dependency injection via `app.state` + `Depends()`
- Frozen Pydantic models with `ConfigDict(frozen=True)` for responses

### Integration Points
- `main.py` `create_app()`: mount new dashboard router and configure Jinja2 templates + static files
- `GET /admin/nodes`: JSON API the dashboard JS fetches on page load
- `pyproject.toml`: add `jinja2` dependency

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

*Phase: 08-dashboard-and-node-fleet*
*Context gathered: 2026-06-30*
