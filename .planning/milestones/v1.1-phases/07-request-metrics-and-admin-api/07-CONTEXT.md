# Phase 7: Request Metrics and Admin API - Context

**Gathered:** 2026-06-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Add in-memory request counters to the gateway and enrich the existing `/admin/nodes` endpoint with active_connections and circuit_breaker_state fields. This phase provides the data layer that the Phase 8 dashboard and Phase 9 live metrics will consume.

</domain>

<decisions>
## Implementation Decisions

### What Gets Counted
- **D-01:** Count proxied inference requests only — POST /v1/chat/completions and POST /v1/completions. Do not count admin, health, or models endpoint traffic.
- **D-02:** Track total counts only (simple integers). No success/error breakdown in v1.1.
- **D-03:** Count each retry attempt separately per node. Total request counter increments once per client request; per-node counters increment on every attempt (including retries). This reflects actual load per node.

### Claude's Discretion
- Metrics API shape: whether to add a new `/admin/metrics` endpoint, extend `/admin/nodes`, or both — pick what best serves the dashboard (Phase 8/9)
- Counter structure: follow `ConnectionTracker`'s dict+lock pattern or choose a different approach — whatever fits cleanly with the existing codebase

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs — requirements fully captured in decisions above and REQUIREMENTS.md.

### Existing Code (MUST read before implementing)
- `inference_proxy/api/admin.py` — Current admin router, `/admin/nodes` endpoint to extend
- `inference_proxy/models/admin.py` — AdminNodeResponse model (4 fields, needs enrichment)
- `inference_proxy/routing/connection_tracker.py` — Thread-safe dict+lock pattern; active connections data source
- `inference_proxy/resilience/circuit_breaker.py` — CircuitBreakerRegistry; breaker state data source
- `inference_proxy/api/routes.py` — Proxy route handlers where counter increment should happen
- `inference_proxy/config/dependencies.py` — Dependency injection wiring via app.state

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ConnectionTracker`: Thread-safe dict+lock counter — proven pattern to follow for request counters
- `CircuitBreakerRegistry`: Lazy per-node creation pattern — `get_or_create(node_id)`
- `AdminNodeResponse`: Pydantic model with `ConfigDict(frozen=True)` — extend with new fields

### Established Patterns
- Thread-safe dict + `threading.Lock` for shared mutable state (ConnectionTracker, CircuitBreakerRegistry)
- Dependency injection via `app.state` + `Depends()` in FastAPI routes
- Admin endpoints return flat JSON arrays (AdminNodeResponse list)
- Admin router separated from proxy router (`/admin` prefix)

### Integration Points
- `_proxy_non_streaming()` in routes.py: increment per-node counter in the try block, before/after proxy.forward()
- `_stream_completion()` in routes.py: increment in the event_generator try block
- `admin_router.get("/nodes")`: enrich response with connection counts and breaker state
- `app.state` in main.py lifespan: wire new metrics collector into dependency injection
- `get_registry`, `get_circuit_breaker_registry` in dependencies.py: data sources for enriched admin response

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

*Phase: 07-request-metrics-and-admin-api*
*Context gathered: 2026-06-29*
