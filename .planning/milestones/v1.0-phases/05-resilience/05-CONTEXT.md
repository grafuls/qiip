# Phase 5: Resilience - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Transparent failure handling for the gateway — periodic health checks detect unhealthy vLLM nodes, failed pre-stream requests retry on another healthy node, per-node circuit breakers prevent cascading failures after consecutive errors, and the gateway shuts down gracefully by draining in-flight requests. This phase fills the `resilience/` module stub created in Phase 1.

</domain>

<decisions>
## Implementation Decisions

### Health Check Probing
- **D-01:** Health checker runs in a dedicated `threading.Thread` with a `threading.Event` for shutdown signaling — consistent with the watcher thread pattern from Phase 2 (D-03).
- **D-02:** Probes each node's `/health` endpoint (vLLM's built-in readiness check). Uses synchronous HTTP calls from the health check thread.
- **D-03:** A node is marked `UNHEALTHY` after 3 consecutive health check failures. This tolerates brief network blips at the default 30s interval (90s before marking unhealthy).
- **D-04:** A node recovers to `HEALTHY` after 1 successful `/health` probe. If the node answers, it's ready to serve.

### Circuit Breaker Design
- **D-05:** Circuit breaker state lives in a separate `CircuitBreaker` class in `inference_proxy/resilience/`, managed by a `CircuitBreakerRegistry`. Keeps resilience logic out of the node registry, consistent with how `ConnectionTracker` lives in `routing/`.
- **D-06:** Circuit breaker trips open after 3 consecutive request failures (proxy errors, timeouts, 5xx responses). Counts actual request failures, separate from health check failures.
- **D-07:** When the circuit breaker trips, it marks the node `UNHEALTHY` in the `NodeRegistry`. `NodeSelector` already skips non-HEALTHY nodes — one source of truth for "can this node receive traffic."
- **D-08:** No explicit half-open state. The background health checker probes unhealthy nodes on its regular interval. When `/health` passes, the health checker resets the breaker to closed and restores the node to `HEALTHY`. Health checks and circuit breakers work together naturally.

### Shutdown Coordination
- **D-09:** Gateway sets a `shutting_down` flag in `app.state` when shutdown begins. A FastAPI middleware checks this flag and returns 503 for all new requests. In-flight requests continue to completion.
- **D-10:** Configurable drain timeout via `graceful_shutdown_timeout` in `GatewaySettings` (default 30s). After the timeout, the gateway stops even if in-flight requests remain.
- **D-11:** Health check thread stops immediately when shutdown begins (receives the stop `Event`). No point probing nodes if we're not accepting new requests.
- **D-12:** The `/health` endpoint keeps returning 200 during shutdown. Uvicorn handles connection refusal when the process stops.

### Retry Behavior
- **D-13:** Retry logic details (which errors trigger retry, how to exclude the failed node, streaming pre-first-byte retry) are left to Claude's discretion based on RESL-02 requirements and existing code patterns.

### Claude's Discretion
- Retry implementation details: which HTTP errors trigger retry, backoff strategy, how to exclude the failed node from retry selection
- Whether pre-first-byte streaming failures should retry (RESL-02 says "does not retry mid-stream" but is silent on pre-first-byte)
- Health check thread internal implementation (how to iterate nodes, HTTP client choice for sync probing)
- Circuit breaker counter reset strategy (reset on success or use sliding window)
- Middleware implementation details for the shutdown flag
- Test fixture design for health checks, circuit breakers, and graceful shutdown

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `PLAN.md` — Architecture design document with gateway pseudocode and system workflow diagrams

### Requirements
- `.planning/REQUIREMENTS.md` — RESL-01 (health checks), RESL-02 (retry with failover), RESL-03 (circuit breaker), RESL-04 (graceful shutdown)
- `.planning/ROADMAP.md` — Phase 5 success criteria and dependencies

### Technology Stack
- `CLAUDE.md` §Technology Stack — httpx, FastAPI, structlog, tenacity (retry logic), anyio (structured concurrency)

### Prior Phases
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-01 (package layout with resilience/ stub), D-05/D-08 (config design, DI pattern)
- `.planning/phases/02-service-discovery/02-CONTEXT.md` — D-03 (watcher thread pattern), D-09/D-10 (startup/shutdown behavior)
- `.planning/phases/04-intelligent-routing/04-CONTEXT.md` — D-07/D-08 (NodeSelector strategy, DI injection), D-10/D-11 (drain coordination)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `inference_proxy/resilience/__init__.py` — Empty stub from Phase 1, ready for `CircuitBreaker` and health check modules
- `inference_proxy/config/settings.py:RoutingSettings` — Already has `health_check_interval=30`, `max_retries=3`, `timeout=30`
- `inference_proxy/models/node.py:NodeStatus` — `UNHEALTHY` status already defined in the enum
- `inference_proxy/discovery/registry.py:NodeRegistry` — Thread-safe with `get_all()`, `get()`, `add()`, `remove()`. Supports `model_copy(update={...})` for status transitions via frozen Pydantic models.
- `inference_proxy/routing/node_selector.py:NodeSelector` — Already skips non-HEALTHY nodes in `select()`. Circuit breaker integration is additive.
- `inference_proxy/routing/connection_tracker.py:ConnectionTracker` — Pattern to follow for circuit breaker state management

### Established Patterns
- Dedicated `threading.Thread` + `threading.Event` for long-running background work (watcher)
- FastAPI lifespan for startup/shutdown lifecycle management
- `Depends()` injection for shared resources (`get_registry()`, `get_node_selector()`, `get_proxy_client()`)
- Frozen Pydantic models with `model_copy(update={...})` for state transitions
- `threading.Lock` for thread-safe shared state
- Route handlers delegate to injected objects — keep business logic out of route functions

### Integration Points
- `inference_proxy/main.py:lifespan` — Start health check thread, create circuit breaker registry, add `shutting_down` flag, extend shutdown to drain in-flight requests
- `inference_proxy/api/routes.py` — Record request failures in circuit breaker, add retry logic around proxy calls
- `inference_proxy/config/settings.py:GatewaySettings` — Add `graceful_shutdown_timeout` field
- `inference_proxy/config/dependencies.py` — Add DI function for circuit breaker registry if needed
- `inference_proxy/main.py` — Add shutdown middleware for 503 rejection

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

*Phase: 5-Resilience*
*Context gathered: 2026-06-24*
