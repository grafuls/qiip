# Phase 5: Resilience - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 5-Resilience
**Areas discussed:** Health check probing, Circuit breaker design, Shutdown coordination

---

## Health Check Probing

### Q1: How should the health checker run?

| Option | Description | Selected |
|--------|-------------|----------|
| Background thread | Dedicated thread with polling loop, consistent with watcher pattern. Uses threading.Event for shutdown. | ✓ |
| asyncio background task | Uses asyncio.create_task in lifespan. More natural for async httpx but adds different concurrency pattern. | |
| You decide | Claude picks whichever fits existing patterns best. | |

**User's choice:** Background thread
**Notes:** Consistency with existing watcher thread pattern was the deciding factor.

### Q2: What endpoint to probe?

| Option | Description | Selected |
|--------|-------------|----------|
| /health endpoint | Standard vLLM readiness check. Fast, low overhead. Returns 200 when model is loaded. | ✓ |
| You decide | Claude picks based on vLLM docs and PLAN.md. | |

**User's choice:** /health endpoint

### Q3: How many failures to mark unhealthy?

| Option | Description | Selected |
|--------|-------------|----------|
| 3 consecutive failures | At 30s interval, 90s before marking unhealthy. Tolerates brief blips. | ✓ |
| 1 failure = unhealthy | Aggressive, pulls nodes immediately. Risks flapping. | |
| Configurable threshold | Add health_check_failures_threshold to RoutingSettings (default 3). | |
| You decide | Claude picks a sensible default. | |

**User's choice:** 3 consecutive failures

### Q4: How should unhealthy nodes recover?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 successful probe | Single /health pass restores to HEALTHY. Simple and responsive. | ✓ |
| N successful probes | Multiple consecutive successes required. More cautious, adds delay. | |
| You decide | Claude picks based on vLLM recovery patterns. | |

**User's choice:** 1 successful probe

---

## Circuit Breaker Design

### Q1: Where should circuit breaker state live?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate class in resilience/ | CircuitBreaker per node, managed by CircuitBreakerRegistry. Consistent with ConnectionTracker in routing/. | ✓ |
| Inside NodeSelector | Add breaker state to NodeSelector. Simpler but violates SRP. | |
| You decide | Claude picks cleanest separation. | |

**User's choice:** Separate class in resilience/

### Q2: How should half-open state work?

| Option | Description | Selected |
|--------|-------------|----------|
| Health checker closes it | Background health check probes unhealthy nodes. When /health passes, reset breaker. No half-open state needed. | ✓ |
| Timer-based half-open | After cooldown, allow one probe request. Classic pattern but adds complexity. | |
| You decide | Claude picks best integration with health check design. | |

**User's choice:** Health checker closes it

### Q3: What failure threshold trips the breaker?

| Option | Description | Selected |
|--------|-------------|----------|
| 5 consecutive failures | Generous, tolerates occasional errors. | |
| 3 consecutive failures | More aggressive. Matches health check threshold for consistency. | ✓ |
| Configurable (default 5) | Add circuit_breaker_threshold to RoutingSettings. | |
| You decide | Claude picks a sensible default. | |

**User's choice:** 3 consecutive failures

### Q4: Should breaker affect node status in registry?

| Option | Description | Selected |
|--------|-------------|----------|
| Mark UNHEALTHY in registry | When breaker opens, set node UNHEALTHY. NodeSelector already skips non-HEALTHY. One source of truth. | ✓ |
| Breaker-only blocking | Node stays HEALTHY but breaker prevents selection. Cleaner separation but dual check. | |

**User's choice:** Mark UNHEALTHY in registry

---

## Shutdown Coordination

### Q1: How to stop accepting new requests?

| Option | Description | Selected |
|--------|-------------|----------|
| Shutdown flag + 503 | Set shutting_down flag, middleware returns 503 for new requests. In-flight continue. | ✓ |
| Rely on Uvicorn's shutdown | Let ASGI server handle it. Simpler but less control. | |
| You decide | Claude picks based on existing lifespan pattern. | |

**User's choice:** Shutdown flag + 503

### Q2: How long to wait for in-flight requests?

| Option | Description | Selected |
|--------|-------------|----------|
| 30 seconds | Matches default request timeout. | |
| Match read_timeout (120s) | Guarantees slow requests finish. Very long shutdown. | |
| Configurable (default 30s) | Add graceful_shutdown_timeout to GatewaySettings. | ✓ |
| You decide | Claude picks sensible default. | |

**User's choice:** Configurable (default 30s)

### Q3: Should health check thread stop during shutdown?

| Option | Description | Selected |
|--------|-------------|----------|
| Stop immediately | Signal stop when shutdown begins. No point probing if not accepting requests. | ✓ |
| Continue until drained | Keep probing for in-flight retry needs. | |
| You decide | Claude picks what makes sense. | |

**User's choice:** Stop immediately

### Q4: Should /health reflect shutting_down state?

| Option | Description | Selected |
|--------|-------------|----------|
| Return 503 when shutting down | Change /health to return 503 with shutting_down status. | |
| Keep returning 200 | Health endpoint stays healthy until process stops. | ✓ |
| You decide | Claude picks based on operational best practices. | |

**User's choice:** Keep returning 200

---

## Claude's Discretion

- Retry implementation details (which errors trigger retry, backoff, failed node exclusion)
- Pre-first-byte streaming retry behavior
- Health check thread internals (node iteration, sync HTTP client choice)
- Circuit breaker counter reset strategy
- Shutdown middleware implementation details
- Test fixture design for all resilience features

## Deferred Ideas

None — discussion stayed within phase scope
