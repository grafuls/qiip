# Phase 4: Intelligent Routing - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Least-connections load balancing with model-aware filtering for vLLM node selection. The gateway routes requests to the optimal node based on active connection count and requested model. This phase replaces the "first healthy node" selector from Phase 3 with intelligent routing — health checks, retry logic, and circuit breakers are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Connection Tracking
- **D-01:** Active connection counts live in a separate counter structure, not inside the NodeRegistry. The registry remains a pure node store; connection tracking is a routing concern.
- **D-02:** Connection counts are managed via a context manager in the route handlers — increment before proxying, decrement after (in finally block). This keeps the tracking close to the request lifecycle.
- **D-03:** When multiple nodes have the same lowest connection count, ties break randomly.

### Model-Not-Found Behavior
- **D-04:** When a client requests a model that no registered node serves, return a 404 with OpenAI-compatible error schema (`{"error": {"type": "invalid_request_error", "message": "model not found"}}`).
- **D-05:** Model filtering uses exact string match only — no prefix, fuzzy, or alias matching.
- **D-06:** When nodes exist for the requested model but all are unhealthy/draining, return 503 ("model temporarily unavailable") — distinct from the 404 "model not found" case. This lets clients distinguish between "model doesn't exist" and "model is down, retry later."

### Node Selection Strategy
- **D-07:** Replace the `select_node` pure function with a `NodeSelector` strategy class that holds references to the registry and connection tracker. Exposes a `select(model=None) -> Node | None` method.
- **D-08:** The `NodeSelector` is injected into route handlers via FastAPI `Depends()`, consistent with existing `ProxyClient` and `NodeRegistry` DI patterns.
- **D-09:** The `model` parameter on `select()` is optional (default `None`). When `None`, selects among all healthy nodes regardless of model — backwards-compatible with Phase 3 behavior and useful for non-model-specific operations.

### Drain Coordination
- **D-10:** When etcd signals a node removal, the node is marked `DRAINING` in the registry. The selector skips DRAINING nodes for new requests. In-flight requests finish naturally — no active waiting or polling.
- **D-11:** After a draining node's connection count reaches 0, it is automatically removed from the registry. No timeout — relies on httpx request timeouts to bound stuck connections.

### Claude's Discretion
- Drain trigger ownership: whether the watcher directly sets DRAINING or the registry exposes a `drain()` method — Claude picks the cleanest separation given the existing watcher/registry boundary
- Whether DRAINING nodes appear in `/v1/models` response — Claude picks based on what makes most sense for client experience
- Internal connection counter implementation details (dict, atomic counters, lock strategy)
- Test fixture design for connection tracking and drain coordination

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `PLAN.md` — Architecture design document with gateway pseudocode and system workflow diagrams

### Requirements
- `.planning/REQUIREMENTS.md` — DISC-03 (model-aware filtering), LBAL-01 (least-connections), LBAL-02 (drain before removal)
- `.planning/ROADMAP.md` — Phase 4 success criteria and dependencies

### Technology Stack
- `CLAUDE.md` §Technology Stack — httpx, FastAPI, Pydantic conventions

### Prior Phases
- `.planning/phases/02-service-discovery/02-CONTEXT.md` — D-06 through D-10 (registry design, watcher thread, startup/shutdown behavior)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `inference_proxy/proxy/node_selector.py:select_node` — Current simple selector to replace with `NodeSelector` strategy class. Module docstring already anticipates this change.
- `inference_proxy/discovery/registry.py:NodeRegistry` — Thread-safe node store with `get_all()`, `get()`, `add()`, `remove()`. Connection counter will live alongside, not inside.
- `inference_proxy/models/node.py:NodeStatus.DRAINING` — Already defined in the enum, ready for drain coordination.
- `inference_proxy/models/node.py:Node.model` — String field for model name, used for exact-match filtering.
- `inference_proxy/config/dependencies.py` — DI functions for `get_registry()` and `get_proxy_client()`. Add `get_node_selector()` following same pattern.

### Established Patterns
- FastAPI `Depends()` injection for shared resources — follow for NodeSelector
- Frozen Pydantic models (`Node`) — use `model_copy(update={...})` for status transitions
- `threading.Lock` in NodeRegistry — connection counter may need similar thread safety if accessed from watcher thread
- Route handlers delegate to pure functions/objects — keep business logic out of route functions

### Integration Points
- `inference_proxy/api/routes.py` — Replace `select_node(registry)` calls with `node_selector.select(model=...)`. Add connection tracking context manager around proxy calls.
- `inference_proxy/main.py:lifespan` — Create NodeSelector with registry + connection tracker, store in app.state for DI.
- `inference_proxy/discovery/watcher.py` — Hook drain transition on node removal events (set DRAINING instead of immediate remove).
- `inference_proxy/api/errors.py` — Add 404 model-not-found and 503 model-unavailable error factories.

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

*Phase: 4-Intelligent Routing*
*Context gathered: 2026-06-24*
