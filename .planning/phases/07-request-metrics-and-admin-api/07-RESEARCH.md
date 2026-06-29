# Phase 7: Request Metrics and Admin API - Research

**Researched:** 2026-06-29
**Domain:** In-memory request counters + admin API enrichment (Python, FastAPI, threading)
**Confidence:** HIGH

## Summary

Phase 7 adds in-memory request counters and enriches the existing `/admin/nodes` endpoint with `active_connections` and `circuit_breaker_state` fields. No new dependencies are needed. The codebase already has the exact pattern to follow: `ConnectionTracker` is a thread-safe dict+lock counter class. A new `RequestMetrics` class follows the same shape for request counts (total, per-node, per-model).

The admin endpoint enrichment requires reading from three data sources already wired into `app.state`: `NodeRegistry` (node list), `ConnectionTracker` (active connections), and `CircuitBreakerRegistry` (breaker state). Two minor accessor methods are missing from existing classes (`CircuitBreaker.state` property and `CircuitBreakerRegistry.get_state(node_id)`) -- these are trivial additions.

**Primary recommendation:** Follow the `ConnectionTracker` dict+lock pattern for `RequestMetrics`. Inject it via `app.state` like every other service. Increment in `_proxy_non_streaming` and `_stream_completion` in `routes.py`. No new dependencies, no new files beyond one metrics module and its tests.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Count proxied inference requests only -- POST /v1/chat/completions and POST /v1/completions. Do not count admin, health, or models endpoint traffic.
- **D-02:** Track total counts only (simple integers). No success/error breakdown in v1.1.
- **D-03:** Count each retry attempt separately per node. Total request counter increments once per client request; per-node counters increment on every attempt (including retries). This reflects actual load per node.

### Claude's Discretion
- Metrics API shape: whether to add a new `/admin/metrics` endpoint, extend `/admin/nodes`, or both -- pick what best serves the dashboard (Phase 8/9)
- Counter structure: follow `ConnectionTracker`'s dict+lock pattern or choose a different approach -- whatever fits cleanly with the existing codebase

### Deferred Ideas (OUT OF SCOPE)
None

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| METR-01 | Gateway tracks total request count, per-model count, and per-node count in memory | `RequestMetrics` class following `ConnectionTracker` pattern; dict+lock for thread safety; increment in route handlers |
| METR-03 | Admin API `/admin/nodes` extended with active_connections and circuit_breaker_state fields | Enrich `AdminNodeResponse` Pydantic model with 2 new fields; read from `ConnectionTracker.get()` and `CircuitBreaker.state` in admin handler |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Request counting | API / Backend | -- | Counters live in the proxy layer where requests are handled |
| Counter storage | API / Backend | -- | In-memory only; no database tier involved |
| Admin API enrichment | API / Backend | -- | Extends existing FastAPI admin endpoint |
| Data for dashboard | API / Backend | -- | Phase 8/9 will consume this JSON; this phase provides the data |

## Standard Stack

### Core

No new libraries needed. Everything required is already installed and in use.

| Library | Version | Purpose | Already Installed |
|---------|---------|---------|-------------------|
| FastAPI | >=0.135 | Admin endpoint handler | Yes |
| Pydantic | >=2.10 | AdminNodeResponse model | Yes |
| structlog | >=26.1.0 | Logging counter operations | Yes |
| threading (stdlib) | -- | Lock for thread-safe counters | Yes (stdlib) |
| pytest | >=8.0 | Testing | Yes |

### Supporting
None needed.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| dict+Lock | `collections.Counter` | Counter is not thread-safe; still need a Lock wrapper, adds no value |
| dict+Lock | `asyncio` primitives | Existing codebase uses `threading.Lock` consistently; mixing paradigms adds confusion |
| Separate `/admin/metrics` endpoint | Extend `/admin/nodes` only | Both approaches work; recommendation below |

## Architecture Patterns

### Metrics API Shape Recommendation (Claude's Discretion)

**Recommendation: Both.** Extend `/admin/nodes` with `active_connections` and `circuit_breaker_state` (required by METR-03) AND add a lightweight `/admin/metrics` endpoint returning aggregate counters (total, per-model, per-node). Rationale:

1. `/admin/nodes` is per-node data -- `active_connections` and `circuit_breaker_state` belong there naturally.
2. Aggregate counters (total requests, per-model totals) do not belong on each node entry -- they are system-level, not node-level.
3. The Phase 8 dashboard needs both: a node table (from `/admin/nodes`) and a summary header (from `/admin/metrics`).

This keeps each endpoint's response model focused (ISP) without forcing the dashboard to compute aggregates client-side.

### Counter Structure Recommendation (Claude's Discretion)

**Recommendation: Follow `ConnectionTracker` pattern exactly.** A single `RequestMetrics` class with three internal dicts behind one lock:

```python
# Source: follows ConnectionTracker pattern in routing/connection_tracker.py
class RequestMetrics:
    def __init__(self) -> None:
        self._total: int = 0
        self._per_node: dict[str, int] = {}
        self._per_model: dict[str, int] = {}
        self._lock = threading.Lock()

    def record_request(self, node_id: str, model: str | None) -> None:
        with self._lock:
            self._total += 1
            self._per_node[node_id] = self._per_node.get(node_id, 0) + 1
            if model:
                self._per_model[model] = self._per_model.get(model, 0) + 1

    def record_node_attempt(self, node_id: str) -> None:
        with self._lock:
            self._per_node[node_id] = self._per_node.get(node_id, 0) + 1
```

Per D-03: `_total` increments once per client request. `_per_node` increments on every attempt including retries. Two methods: `record_request()` for the first attempt (increments total + per-node + per-model) and `record_node_attempt()` for retry attempts (per-node only).

### System Data Flow

```
Client Request (POST /v1/chat/completions or /v1/completions)
    |
    v
routes.py: chat_completions() / text_completions()
    |
    +-- record_request(node_id, model)    <-- total++, per_node[node]++, per_model[model]++
    |
    +-- [on retry to different node]
    |       record_node_attempt(node_id)  <-- per_node[retry_node]++ only
    |
    v
Admin reads (GET /admin/nodes, GET /admin/metrics)
    |
    +-- /admin/nodes: registry.get_all() + tracker.get(node_id) + breaker.state
    +-- /admin/metrics: metrics.get_total(), metrics.get_per_model(), metrics.get_per_node()
    |
    v
Dashboard (Phase 8/9 consumer)
```

### Recommended Project Structure

```
inference_proxy/
├── routing/
│   ├── connection_tracker.py    # existing -- active connections
│   ├── node_selector.py         # existing
│   └── request_metrics.py       # NEW -- request counters (total, per-node, per-model)
├── models/
│   └── admin.py                 # MODIFY -- add active_connections, circuit_breaker_state
├── api/
│   └── admin.py                 # MODIFY -- enrich /admin/nodes, add /admin/metrics
├── config/
│   └── dependencies.py          # MODIFY -- add get_request_metrics()
└── main.py                      # MODIFY -- create RequestMetrics in lifespan
```

New file: 1. Modified files: 4.

### Integration Points

**Where to increment counters in routes.py:**

Non-streaming (`_proxy_non_streaming`):
- Line ~170 (before the retry loop body): Increment total + per-model once (first attempt only)
- Line ~185 (after `tracker.increment(node.node_id)`): Increment per-node counter on every attempt

Streaming (`_stream_completion`):
- Line ~359 (after `tracker.increment(node.node_id)`): Increment total + per-model + per-node (no retries for streaming)

**Where to read data in admin.py:**

`list_nodes()`:
- Inject `ConnectionTracker` (via `node_selector.tracker`) and `CircuitBreakerRegistry`
- For each node: `active_connections=tracker.get(n.node_id)`, `circuit_breaker_state=breaker_registry.get_or_create(n.node_id).state`

### Missing Accessor: CircuitBreaker.state

The `CircuitBreaker` class has `is_open` (returns bool) but no `state` property (returns the string "closed"/"open"). Need to add:

```python
# In circuit_breaker.py CircuitBreaker class
@property
def state(self) -> str:
    """Return the current state as a string ('closed' or 'open')."""
    with self._lock:
        return self._state
```

This is a 3-line addition. The admin endpoint needs the string, not the bool.

### Anti-Patterns to Avoid
- **Middleware-based counting:** Don't use FastAPI middleware for counting -- it catches ALL requests including /health and /admin. The decisions explicitly say count only inference endpoints. Increment in the route handlers directly.
- **Async-only counters:** Don't use `asyncio.Lock` -- the codebase consistently uses `threading.Lock` because etcd operations run in threads. Stay consistent.
- **Counter reset on node removal:** Don't zero counters when a node drains out. Historical request counts should persist for the dashboard.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thread-safe counter | Custom async lock scheme | `threading.Lock` + dict (ConnectionTracker pattern) | Proven in this codebase, consistent with all other shared state |
| Admin response enrichment | Separate aggregation service | Direct reads from existing registries in the admin handler | Three data sources already wired into app.state |

**Key insight:** This phase adds zero new infrastructure. It reuses the exact concurrency pattern that already works, reads from services that already exist in `app.state`, and extends a Pydantic model and admin handler that are already tested.

## Common Pitfalls

### Pitfall 1: Double-counting total requests on retries
**What goes wrong:** Total request count inflates because it increments on every retry attempt.
**Why it happens:** Mixing up "client request" vs "node attempt" in the retry loop.
**How to avoid:** Per D-03, increment total ONCE before the retry loop. Increment per-node inside the loop.
**Warning signs:** Total count exceeds sum of client requests in logs.

### Pitfall 2: Lock contention on hot path
**What goes wrong:** Single lock for all counter updates blocks request throughput.
**Why it happens:** Every proxied request touches the metrics lock.
**How to avoid:** Keep the critical section minimal (three integer increments). At the traffic levels of an internal gateway this is a non-issue. The `ConnectionTracker` uses the same pattern on the same hot path without problems.
**Warning signs:** Not expected to manifest at this scale. `# ponytail: single lock, split per-node/per-model locks if throughput matters`

### Pitfall 3: Enriched admin test breaks existing assertions
**What goes wrong:** Existing test `test_each_node_has_exactly_four_fields` explicitly asserts `"active_connections" not in node` and checks for exactly 4 keys.
**Why it happens:** The test was written for Phase 6's D-07 (core fields only). Phase 7 changes the contract.
**How to avoid:** Update the test to assert 6 fields (add `active_connections`, `circuit_breaker_state`). This is expected -- the requirement explicitly extends the response.
**Warning signs:** Test failure on `test_each_node_has_exactly_four_fields`.

### Pitfall 4: CircuitBreaker state for nodes never proxied to
**What goes wrong:** `get_or_create()` creates a breaker for every node when the admin endpoint is hit, even nodes that never had traffic.
**Why it happens:** Lazy creation is fine for the proxy path but creates phantom breakers in the admin path.
**How to avoid:** Use a method that returns `None` for unknown nodes, or just accept that the default "closed" state is correct for nodes with no failures. The latter is simpler and accurate -- a node with no failures IS closed.

## Code Examples

### RequestMetrics class (verified pattern from ConnectionTracker)

```python
# Source: follows inference_proxy/routing/connection_tracker.py pattern
class RequestMetrics:
    """Thread-safe request counters: total, per-node, per-model."""

    def __init__(self) -> None:
        self._total: int = 0
        self._per_node: dict[str, int] = {}
        self._per_model: dict[str, int] = {}
        self._lock = threading.Lock()

    def record_request(self, node_id: str, model: str | None) -> None:
        """Record a new client request (first attempt)."""
        with self._lock:
            self._total += 1
            self._per_node[node_id] = self._per_node.get(node_id, 0) + 1
            if model:
                self._per_model[model] = self._per_model.get(model, 0) + 1

    def record_node_attempt(self, node_id: str) -> None:
        """Record a retry attempt to a node (per-node only, no total increment)."""
        with self._lock:
            self._per_node[node_id] = self._per_node.get(node_id, 0) + 1

    def get_total(self) -> int:
        with self._lock:
            return self._total

    def get_per_node(self) -> dict[str, int]:
        with self._lock:
            return dict(self._per_node)

    def get_per_model(self) -> dict[str, int]:
        with self._lock:
            return dict(self._per_model)
```

### Enriched AdminNodeResponse

```python
# Source: extends inference_proxy/models/admin.py
class AdminNodeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    endpoint: str
    model: str
    status: str
    active_connections: int     # NEW (METR-03)
    circuit_breaker_state: str  # NEW (METR-03)
```

### Enriched admin handler

```python
# Source: extends inference_proxy/api/admin.py
@admin_router.get("/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
    node_selector: NodeSelector = Depends(get_node_selector),
    circuit_breaker_registry: CircuitBreakerRegistry = Depends(get_circuit_breaker_registry),
) -> list[AdminNodeResponse]:
    nodes = registry.get_all()
    tracker = node_selector.tracker
    return [
        AdminNodeResponse(
            node_id=n.node_id,
            endpoint=n.endpoint,
            model=n.model,
            status=n.status.value,
            active_connections=tracker.get(n.node_id),
            circuit_breaker_state=circuit_breaker_registry.get_or_create(n.node_id).state,
        )
        for n in nodes
    ]
```

### Increment placement in _proxy_non_streaming

```python
# Source: inference_proxy/api/routes.py _proxy_non_streaming()
# Before the retry loop -- increment total once:
request_metrics.record_request(node.node_id, model)  # first attempt

# Inside retry loop on subsequent attempts:
request_metrics.record_node_attempt(node.node_id)     # retry attempt (per-node only)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Prometheus client library | In-memory counters | Decision for v1.1 | No external dependency; counters reset on restart (acceptable for ops dashboard) |
| Middleware-based counting | Route-handler counting | Phase 7 design | Precise control over which endpoints are counted |

**Deprecated/outdated:**
- None relevant. This phase uses only stdlib and existing project patterns.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `get_or_create()` returning "closed" for never-used nodes is acceptable | Code Examples | Low -- "closed" is semantically correct for zero-failure nodes |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/api/test_admin.py tests/routing/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| METR-01 | record_request increments total, per-node, per-model | unit | `uv run pytest tests/routing/test_request_metrics.py -x` | No -- Wave 0 |
| METR-01 | record_node_attempt increments per-node only, not total | unit | `uv run pytest tests/routing/test_request_metrics.py -x` | No -- Wave 0 |
| METR-01 | Thread safety under concurrent access | unit | `uv run pytest tests/routing/test_request_metrics.py -x` | No -- Wave 0 |
| METR-03 | /admin/nodes includes active_connections field | integration | `uv run pytest tests/api/test_admin.py -x` | Yes (needs update) |
| METR-03 | /admin/nodes includes circuit_breaker_state field | integration | `uv run pytest tests/api/test_admin.py -x` | Yes (needs update) |
| METR-03 | active_connections reflects ConnectionTracker values | integration | `uv run pytest tests/api/test_admin.py -x` | No -- Wave 0 |
| METR-03 | circuit_breaker_state reflects breaker state | integration | `uv run pytest tests/api/test_admin.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/routing/test_request_metrics.py tests/api/test_admin.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/routing/test_request_metrics.py` -- covers METR-01 (unit tests for RequestMetrics)
- [ ] Update `tests/api/test_admin.py` -- covers METR-03 (enriched response assertions)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Internal network only, no auth in v1.1 |
| V3 Session Management | No | Stateless proxy |
| V4 Access Control | No | No access control on admin endpoints (internal network) |
| V5 Input Validation | No | No new user input; counters are server-side only |
| V6 Cryptography | No | No crypto operations |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Counter overflow (integer) | Denial of Service | Python ints have no overflow; non-issue |
| Admin endpoint information disclosure | Information Disclosure | Acceptable -- internal network only per project constraints |

## Sources

### Primary (HIGH confidence)
- `inference_proxy/routing/connection_tracker.py` -- dict+lock pattern, verified by reading source
- `inference_proxy/resilience/circuit_breaker.py` -- CircuitBreaker/Registry API, verified by reading source
- `inference_proxy/api/admin.py` -- current admin handler structure, verified by reading source
- `inference_proxy/api/routes.py` -- proxy handler structure and increment points, verified by reading source
- `inference_proxy/config/dependencies.py` -- DI wiring pattern, verified by reading source
- `inference_proxy/main.py` -- lifespan wiring pattern, verified by reading source
- `tests/conftest.py` -- test fixture patterns, verified by reading source
- `tests/api/test_admin.py` -- existing admin tests that need updating, verified by reading source

### Secondary (MEDIUM confidence)
None needed -- this phase is entirely codebase-internal.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all patterns verified in codebase
- Architecture: HIGH -- follows exact existing patterns (ConnectionTracker, DI via app.state)
- Pitfalls: HIGH -- identified from reading existing tests and code paths

**Research date:** 2026-06-29
**Valid until:** indefinite -- this phase depends only on internal codebase patterns, not external library APIs
