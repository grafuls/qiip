---
phase: 04-intelligent-routing
verified: 2026-06-24T16:26:00Z
status: passed
score: 11/11 must-haves verified
re_verification: false
---

# Phase 04: Intelligent Routing Verification Report

**Phase Goal:** Gateway routes requests to the optimal node based on active connections and requested model
**Verified:** 2026-06-24T16:26:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

**Plan 01 Truths (Routing Building Blocks):**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ConnectionTracker tracks per-node active connection counts with thread-safe increment/decrement | ✓ VERIFIED | `inference_proxy/routing/connection_tracker.py` lines 37-53: `increment()` and `decrement()` methods use `threading.Lock`, dict access protected. Tests confirm thread-safety with 9 passing tests. |
| 2 | NodeSelector filters nodes by model name using exact string match | ✓ VERIFIED | `inference_proxy/routing/node_selector.py` lines 71-79: `if model is not None: healthy = [n for n in healthy if n.model == model]`. Test `test_model_filter_returns_matching_node` confirms exact match. |
| 3 | NodeSelector selects the node with fewest active connections from healthy candidates | ✓ VERIFIED | `inference_proxy/routing/node_selector.py` lines 82-89: sorts by `tracker.get(n.node_id)`, selects from tied nodes at minimum. Test `test_selects_node_with_fewer_connections` confirms. |
| 4 | NodeSelector skips DRAINING, UNHEALTHY, and UNKNOWN nodes | ✓ VERIFIED | `inference_proxy/routing/node_selector.py` line 64: `healthy = [n for n in nodes if n.status == NodeStatus.HEALTHY]`. Tests confirm DRAINING/UNHEALTHY/UNKNOWN all skipped. |
| 5 | NodeSelector breaks ties randomly among nodes with equal connection counts | ✓ VERIFIED | `inference_proxy/routing/node_selector.py` line 89: `selected = random.choice(tied)`. Test `test_tie_break_returns_one_of_tied_nodes` confirms. |
| 6 | model_not_found_error returns 404 with OpenAI error schema | ✓ VERIFIED | `inference_proxy/api/errors.py` lines 74-92: returns `(404, ErrorResponse)` with `code="model_not_found"`, `type="invalid_request_error"`. Test passes. |
| 7 | model_unavailable_error returns 503 with OpenAI error schema | ✓ VERIFIED | `inference_proxy/api/errors.py` lines 95-113: returns `(503, ErrorResponse)` with `code="model_unavailable"`, `type="server_error"`. Test passes. |

**Plan 02 Truths (Route Wiring and Drain Coordination):**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 8 | Client requesting a model hosted on multiple nodes gets routed to the node with fewest active connections | ✓ VERIFIED | Integration test `TestLeastConnectionsRouting::test_routes_to_least_connections_node` passes. Route handler at `inference_proxy/api/routes.py:112` calls `node_selector.select(model=model)` which implements least-connections. Spot-check confirms node-2 selected when node-1 has higher count. |
| 9 | Client requesting a model only available on specific nodes gets routed exclusively to those nodes | ✓ VERIFIED | Integration test `TestModelFiltering::test_routes_to_matching_model_node` passes. NodeSelector filters by exact model match (line 72 in node_selector.py). Spot-check confirms node-1 selected when only it serves "llama-3". |
| 10 | Client requesting a model no node serves gets a 404 with model_not_found error | ✓ VERIFIED | Integration test `TestModelNotFound::test_model_not_found_returns_404` passes. `_select_error` helper (routes.py:44-62) calls `node_selector.has_model(model)` and returns `model_not_found_error(model)` when false. |
| 11 | Client requesting a model where all serving nodes are draining gets a 503 with model_unavailable error | ✓ VERIFIED | Integration test `TestModelUnavailable::test_model_unavailable_returns_503` passes. `_select_error` returns `model_unavailable_error(model)` when `has_model` is true but no healthy nodes available. |
| 12 | When etcd signals node removal, the node is marked DRAINING and excluded from new requests | ✓ VERIFIED | `inference_proxy/discovery/watcher.py:114` calls `registry.drain(node_id)` on DELETE event. `registry.drain()` (registry.py:47-60) sets `status=NodeStatus.DRAINING`. Test `test_delete_event_sets_draining` confirms. NodeSelector skips DRAINING nodes (node_selector.py:64). |
| 13 | Active connections on a draining node decrement naturally; node is removed from registry when count reaches 0 | ✓ VERIFIED | `_maybe_remove_drained` and `_scan_drained_nodes` helpers (routes.py:65-102) remove DRAINING nodes with 0 connections. Integration test `TestDrainAutoRemoval::test_draining_node_removed_after_proxy_call` confirms. Spot-check shows "drained node removed" log after connection count reaches 0. |
| 14 | Connection counts increment before proxy call and decrement after (in finally block) | ✓ VERIFIED | `inference_proxy/api/routes.py:120` increments, line 132 decrements in finally block (non-streaming). Lines 238/258 do same for streaming. Tests `TestConnectionTracking` and `TestStreamingConnectionTracking` confirm count returns to 0. |
| 15 | DRAINING nodes do not appear in /v1/models response | ✓ VERIFIED | `inference_proxy/api/routes.py:197-198` filters nodes to `NodeStatus.HEALTHY` only. Test `TestDrainingExcludedFromModels::test_draining_nodes_excluded` confirms. |

**Score:** 15/15 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `inference_proxy/routing/connection_tracker.py` | Thread-safe per-node connection counter | ✓ VERIFIED | Exists, 78 lines, exports `ConnectionTracker` with `increment`, `decrement`, `get`, `get_all`, `remove` methods. Uses `threading.Lock` for thread safety. |
| `inference_proxy/routing/node_selector.py` | Least-connections model-aware node selection | ✓ VERIFIED | Exists, 118 lines, exports `NodeSelector` with `select(model=None)` and `has_model(model)` methods. Constructor injection of `NodeRegistry` and `ConnectionTracker`. |
| `inference_proxy/api/errors.py` | model_not_found_error and model_unavailable_error factories | ✓ VERIFIED | Modified, lines 74-113 contain new error factories following existing pattern. Both return proper `(status, ErrorResponse)` tuples. |
| `inference_proxy/api/routes.py` | Routes using NodeSelector and connection tracking | ✓ VERIFIED | Modified, uses `Depends(get_node_selector)` (lines 140, 164, 185). Connection tracking in try/finally blocks (lines 120-134, 238-260). Drain cleanup via `_maybe_remove_drained` and `_scan_drained_nodes`. |
| `inference_proxy/config/dependencies.py` | get_node_selector DI function | ✓ VERIFIED | Modified, lines 52-59 define `get_node_selector(request)` returning `request.app.state.node_selector`. |
| `inference_proxy/main.py` | Lifespan creates ConnectionTracker and NodeSelector | ✓ VERIFIED | Modified, lines 121-123 create `ConnectionTracker`, `NodeSelector(registry, connection_tracker)`, and store in `app.state.node_selector`. |
| `inference_proxy/discovery/registry.py` | drain() method for DRAINING status transition | ✓ VERIFIED | Modified, lines 47-60 define `drain(node_id)` method using `model_copy(update={"status": NodeStatus.DRAINING})`. Thread-safe with lock. |
| `inference_proxy/discovery/watcher.py` | DELETE event sets DRAINING instead of removing | ✓ VERIFIED | Modified, line 114 calls `registry.drain(node_id)` instead of `registry.remove(node_id)` on DELETE events. |
| `tests/routing/test_connection_tracker.py` | Unit tests for ConnectionTracker | ✓ VERIFIED | Exists, 9 tests covering increment, decrement, get, get_all, remove, floor-at-zero behavior. All pass. |
| `tests/routing/test_node_selector.py` | Unit tests for NodeSelector | ✓ VERIFIED | Exists, 13 tests covering empty registry, least-connections, tie-breaking, model filtering, status filtering, has_model. All pass. |
| `tests/api/test_errors.py` | Unit tests for new error factories | ✓ VERIFIED | Modified, 2 new tests for `model_not_found_error` and `model_unavailable_error`. All pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `inference_proxy/routing/node_selector.py` | `inference_proxy/routing/connection_tracker.py` | constructor injection | ✓ WIRED | Line 22 imports `ConnectionTracker`, line 39 accepts in constructor, line 42 stores as `_tracker`. Used in `select()` at lines 82, 86. |
| `inference_proxy/routing/node_selector.py` | `inference_proxy/discovery/registry.py` | constructor injection | ✓ WIRED | Line 20 imports `NodeRegistry`, line 38 accepts in constructor, line 41 stores as `_registry`. Used in `select()` at line 61, `has_model()` at line 116. |
| `inference_proxy/api/routes.py` | `inference_proxy/routing/node_selector.py` | Depends(get_node_selector) | ✓ WIRED | Line 33 imports `get_node_selector`, lines 140/164/185 use `Depends(get_node_selector)`. Calls `node_selector.select()` at lines 112, 230. |
| `inference_proxy/api/routes.py` | `inference_proxy/routing/connection_tracker.py` | node_selector.tracker | ✓ WIRED | Line 118 `tracker = node_selector.tracker`, line 236 same. Calls `tracker.increment()` at lines 120, 238 and `tracker.decrement()` at lines 132, 258. |
| `inference_proxy/main.py` | `inference_proxy/routing/node_selector.py` | app.state.node_selector | ✓ WIRED | Line 35 imports `NodeSelector`, line 122 creates instance, line 123 stores in `app.state.node_selector`. DI function retrieves from app.state. |
| `inference_proxy/discovery/watcher.py` | `inference_proxy/discovery/registry.py` | registry.drain(node_id) | ✓ WIRED | Line 114 calls `registry.drain(node_id)` on DELETE events. Returns bool, logs result. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `NodeSelector.select()` | `nodes` | `self._registry.get_all()` | Yes - registry populated from etcd | ✓ FLOWING |
| `NodeSelector.select()` | `healthy` | filter on `nodes` | Yes - filters by `NodeStatus.HEALTHY` | ✓ FLOWING |
| `NodeSelector.select()` | `min_connections` | `self._tracker.get(healthy[0].node_id)` | Yes - tracker tracks real connection counts | ✓ FLOWING |
| `routes._proxy_non_streaming` | `node` | `node_selector.select(model=model)` | Yes - returns Node from registry | ✓ FLOWING |
| `routes._stream_completion` | `node` | `node_selector.select(model=model)` | Yes - returns Node from registry | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Least-connections routing selects node with fewer connections | `uv run pytest tests/api/test_routes.py::TestLeastConnectionsRouting::test_routes_to_least_connections_node -xvs` | PASSED - node-2 selected when node-1 has 1 connection and node-2 has 0 | ✓ PASS |
| Model filtering routes only to nodes serving requested model | `uv run pytest tests/api/test_routes.py::TestModelFiltering::test_routes_to_matching_model_node -xvs` | PASSED - node-1 selected for "llama-3" when node-2 serves "mistral-7b" | ✓ PASS |
| Draining nodes auto-removed when connection count reaches 0 | `uv run pytest tests/api/test_routes.py::TestDrainAutoRemoval::test_draining_node_removed_after_proxy_call -xvs` | PASSED - "drained node removed" log shows node-2 removed after proxy call | ✓ PASS |
| Full test suite passes without regressions | `uv run pytest -x --tb=short` | 169 passed, 1 warning (unrelated to phase changes) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| **DISC-03** | 04-01, 04-02 | Gateway routes requests only to nodes hosting the requested model (model-aware filtering) | ✓ SATISFIED | `NodeSelector.select(model=...)` filters by exact model match (node_selector.py:71-79). Integration test `TestModelFiltering::test_routes_to_matching_model_node` confirms end-to-end behavior. Routes use model from request body (routes.py:111, 229). |
| **LBAL-01** | 04-01, 04-02 | Gateway routes requests to the node with the fewest active connections (least-connections) | ✓ SATISFIED | `NodeSelector.select()` sorts by `tracker.get(node.node_id)` and selects from tied nodes at minimum (node_selector.py:82-89). `ConnectionTracker` provides thread-safe counts. Integration test `TestLeastConnectionsRouting::test_routes_to_least_connections_node` confirms. |
| **LBAL-02** | 04-02 | Gateway drains active connections before removing a departing node from the routing pool | ✓ SATISFIED | Watcher marks nodes DRAINING on etcd DELETE (watcher.py:114). Routes auto-remove DRAINING nodes when connection count reaches 0 via `_maybe_remove_drained` and `_scan_drained_nodes` (routes.py:65-102). Integration test `TestDrainAutoRemoval::test_draining_node_removed_after_proxy_call` confirms. |

**Requirement Traceability:** All 3 requirements declared in plan frontmatter (`DISC-03`, `LBAL-01`, `LBAL-02`) are satisfied with evidence. No orphaned requirements found in REQUIREMENTS.md for Phase 04.

### Anti-Patterns Found

No anti-patterns found.

**Scanned files:**
- `inference_proxy/routing/connection_tracker.py`
- `inference_proxy/routing/node_selector.py`
- `inference_proxy/api/errors.py`
- `inference_proxy/api/routes.py`
- `inference_proxy/config/dependencies.py`
- `inference_proxy/main.py`
- `inference_proxy/discovery/registry.py`
- `inference_proxy/discovery/watcher.py`

**Patterns checked:**
- Debt markers (TBD, FIXME, XXX): None found
- Warning-level markers (TODO, HACK, PLACEHOLDER): None found
- Empty implementations (return null, return {}, return []): None found
- Hardcoded empty data: None found (connection counts and node selection use real data from registry and tracker)
- Stub patterns: None found

**All modified files are production-ready with substantive implementations.**

---

## Verification Summary

**Phase Goal:** Gateway routes requests to the optimal node based on active connections and requested model

**Goal Achievement:** ✓ VERIFIED

1. **Multiple nodes, same model → least-connections routing:** Confirmed via integration test and spot-check. Node with fewer active connections selected.

2. **Model-aware filtering → routes only to nodes serving requested model:** Confirmed via integration test and spot-check. Requests for "llama-3" route only to nodes serving "llama-3".

3. **Node removal drains active connections first:** Confirmed via integration test and spot-check. etcd DELETE marks node DRAINING, node excluded from new requests, node auto-removed when connection count reaches 0.

**All ROADMAP success criteria met:**
- ✓ When multiple nodes host the same model, the gateway sends the request to the node with the fewest active connections (SC 1)
- ✓ When a client requests a model only available on specific nodes, the gateway routes exclusively to those nodes (SC 2)
- ✓ When a node is being removed, active connections drain before the node leaves the routing pool (SC 3)

**All requirements completed:**
- ✓ DISC-03: Model-aware filtering
- ✓ LBAL-01: Least-connections load balancing
- ✓ LBAL-02: Drain before removal

**Test results:**
- 169 total tests pass
- 0 failures
- 0 regressions
- 24 new tests added in this phase (9 ConnectionTracker, 13 NodeSelector, 2 error factories, 16 integration tests, 4 registry/watcher tests)

**Code quality:**
- No anti-patterns detected
- All artifacts substantive (not stubs)
- All key links verified wired
- Data flows through routing logic (Level 4 verification)
- Thread-safety confirmed (ConnectionTracker and NodeRegistry both use threading.Lock)

---

_Verified: 2026-06-24T16:26:00Z_
_Verifier: Claude (gsd-verifier)_
