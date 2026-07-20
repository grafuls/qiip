# Phase 16: Background Polling - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Gateway maintains a fresh cached list of QUADS hosts without blocking request handling. Builds a QUADSPoller class that periodically calls the existing QUADSClient to fetch and cache host data and availability, tracks staleness metadata, and integrates with the FastAPI lifespan for clean start/stop. No unified node list merge (Phase 17), no dashboard changes (Phase 18). This is the caching/scheduling layer — fully testable in isolation with a mocked QUADSClient.

</domain>

<decisions>
## Implementation Decisions

### Polling Mechanism
- **D-01:** Use `asyncio.Task` for the background poller, not `threading.Thread`. QUADSClient is already async (httpx.AsyncClient), so asyncio.Task is the natural fit — no thread overhead, no asyncio.to_thread() wrapping.
- **D-02:** Poller starts via `asyncio.create_task()` in the lifespan and is cancelled on shutdown (task.cancel() + await).
- **D-03:** QUADSPoller is a class with `start()` and `stop()` methods. Holds the cache, staleness state, and the background task internally. Lifespan calls `poller.start()` / `await poller.stop()`.

### Poller Location
- **D-04:** QUADSPoller lives in `inference_proxy/quads/poller.py`. Keeps polling/caching logic separate from the API client (`quads/client.py`). Follows package-per-domain convention (like `discovery/watcher.py`).

### Cache Scope
- **D-05:** Each poll cycle calls both `get_hosts()` and `get_available()`. Phase 17 needs host details (GPU info) AND availability status for the unified list. Two fast HTTP GETs per interval — negligible cost.
- **D-06:** Cached data is accessed via properties on QUADSPoller: `poller.hosts` and `poller.available_hostnames`. Phase 17 gets the poller from `app.state`.

### Staleness Model
- **D-07:** Poller tracks `last_sync` (datetime of last successful poll) and `consecutive_failures` (int, reset on success). Sufficient for DASH-04's connected/stale/unavailable indicator.
- **D-08:** Cached data remains available when QUADS API is unreachable — stale cache is better than no data. Only the staleness metadata changes on failure.

### Claude's Discretion
- Staleness thresholds (what defines "stale" vs "unavailable") — can be simple multiples of the poll interval
- Polling interval config field naming and default value in QUADSSettings
- Internal error handling within the poll loop (log + continue pattern)
- Whether to do an initial poll at startup before the first interval tick

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### QUADS Client (what the poller wraps)
- `inference_proxy/quads/client.py` — QUADSClient with get_hosts() and get_available() methods, QUADSConnectionError exception
- `inference_proxy/models/quads.py` — QUADSHost Pydantic model (hostname, gpu_vendor, gpu_model, gpu_count)

### Background Task Patterns (existing precedent)
- `inference_proxy/resilience/health_checker.py` — Existing background poller pattern (threading-based, but loop/error structure is reusable reference)
- `inference_proxy/main.py` — Lifespan startup/shutdown, app.state service registration, QUADSClient creation (lines 169-179)

### Configuration
- `inference_proxy/config/settings.py` — QUADSSettings class (add poll_interval field here), Settings root class
- `inference_proxy/config/dependencies.py` — DI pattern for app.state services

### Project Context
- `.planning/ROADMAP.md` — Phase 16 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — QUADS-02 requirement definition
- `.planning/phases/15-quads-client-and-models/15-CONTEXT.md` — Prior phase decisions (D-08 through D-11)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `QUADSClient` — already has `get_hosts()` and `get_available()` async methods with QUADSConnectionError handling
- `QUADSSettings` — add `poll_interval` field following existing pattern (timeout field already there)
- `threading.Event` + `stop_event.wait(timeout=interval)` — sleep-with-cancellation pattern from health_checker.py (asyncio equivalent: `asyncio.sleep()` with task cancellation)

### Established Patterns
- Package-per-domain: `quads/poller.py` alongside `quads/client.py`
- Frozen Pydantic models for data — QUADSHost is already frozen
- structlog for all logging — follow existing bound logger pattern
- `app.state` for service registration — poller stored here like other services

### Integration Points
- `main.py` lifespan — create QUADSPoller (if quads configured), call start(), store in app.state, call stop() on shutdown
- `config/settings.py` — add poll_interval to QUADSSettings
- `config/dependencies.py` — add `get_quads_poller()` DI provider for Phase 17

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

*Phase: 16-Background Polling*
*Context gathered: 2026-07-16*
