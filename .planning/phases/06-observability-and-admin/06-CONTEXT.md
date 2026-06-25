# Phase 6: Observability and Admin - Context

**Gathered:** 2026-06-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Operational visibility for the gateway — a request logging middleware that produces structured JSON log entries for every HTTP request, plus an admin API endpoint that exposes the live node fleet with models and health status. This is the final phase of the v1 milestone.

</domain>

<decisions>
## Implementation Decisions

### Request Logging
- **D-01:** Request logging is implemented as a FastAPI middleware (following the ShutdownMiddleware pattern), not per-route logging. A single middleware intercepts all requests and produces a structured log entry on response.
- **D-02:** Log entries include the OBSV-01 minimum fields only: method, path, status_code, duration_ms, target_node. No request_id, model name, or other enrichment in v1.
- **D-03:** The middleware logs ALL requests — /health, /v1/models, admin endpoints, and proxy routes. Target node is null/absent for non-proxy routes.
- **D-04:** The target node is communicated from route handlers to the middleware via `request.state.target_node`. Route handlers set this after node selection; the middleware reads it in the response phase.

### Admin API
- **D-05:** Admin endpoint lives at `/admin/nodes` under a separate `/admin` namespace, not mixed into the `/v1` proxy API.
- **D-06:** The admin router is a separate `APIRouter` in `inference_proxy/api/admin.py` with `prefix="/admin"`, included via `app.include_router()` in `main.py`. Separate from proxy routes (SRP).
- **D-07:** The endpoint returns core fields per node only: node_id, endpoint, model, status. Matches DISC-04 exactly. No operational data (connection counts, circuit breaker state) in v1.
- **D-08:** Response is a flat node list — no top-level summary stats. Clients derive counts from the array.

### Claude's Discretion
- Middleware class name and module placement (e.g., `inference_proxy/api/middleware.py` or `inference_proxy/observability/`)
- How to measure request duration (time.monotonic, time.perf_counter, etc.)
- Log level for request log entries (info vs debug for different route types)
- Admin response Pydantic model design (inline or in models/)
- Whether to add the admin router to the OpenAPI docs or exclude it
- Test fixture design for logging middleware and admin endpoint

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — OBSV-01 (structured JSON request logs), DISC-04 (admin node endpoint)
- `.planning/ROADMAP.md` — Phase 6 success criteria and dependencies

### Technology Stack
- `CLAUDE.md` §Technology Stack — structlog for structured logging, FastAPI for routes
- `inference_proxy/config/logging.py` — Existing structlog configuration (JSON/console renderers)

### Prior Phases
- `.planning/phases/05-resilience/05-CONTEXT.md` — D-09 (ShutdownMiddleware pattern for middleware design), D-05 (CircuitBreakerRegistry pattern)
- `.planning/phases/04-intelligent-routing/04-CONTEXT.md` — D-07/D-08 (NodeSelector, DI injection pattern)

### Existing Patterns
- `inference_proxy/resilience/shutdown.py` — BaseHTTPMiddleware subclass pattern (the model for logging middleware)
- `inference_proxy/api/routes.py` — Existing route handler structure and DI injection
- `inference_proxy/config/dependencies.py` — DI provider pattern for admin endpoint dependencies

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `inference_proxy/config/logging.py` — structlog already configured with JSON renderer (production) and console renderer (dev), timestamping, log level filtering
- `inference_proxy/resilience/shutdown.py:ShutdownMiddleware` — BaseHTTPMiddleware pattern to follow for logging middleware
- `inference_proxy/discovery/registry.py:NodeRegistry.get_all()` — Returns all nodes with status, endpoint, model — the data source for the admin endpoint
- `inference_proxy/models/node.py:Node` — Has node_id, endpoint, model, status fields — the shape of admin response data
- `structlog.get_logger()` — Already used throughout the codebase for consistent logging

### Established Patterns
- `BaseHTTPMiddleware` subclass with `async def dispatch(self, request, call_next)` for cross-cutting concerns
- `APIRouter` per domain (proxy routes in `api/routes.py`) with `app.include_router()` in `main.py`
- `Depends()` injection for shared resources (registry, node_selector, proxy_client, circuit_breaker_registry)
- Frozen Pydantic `BaseModel` for response schemas (see `inference_proxy/models/openai.py`)

### Integration Points
- `inference_proxy/main.py` — Add logging middleware via `app.add_middleware()`, include admin router via `app.include_router()`
- `inference_proxy/api/routes.py` — Route handlers set `request.state.target_node` after node selection for the logging middleware to read
- `inference_proxy/config/dependencies.py` — DI provider for registry (already exists as `get_registry`)

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

*Phase: 6-Observability and Admin*
*Context gathered: 2026-06-25*
