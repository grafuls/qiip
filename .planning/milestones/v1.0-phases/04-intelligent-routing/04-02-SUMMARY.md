---
phase: 04-intelligent-routing
plan: 02
subsystem: routing
tags: [routing, load-balancing, model-filtering, connection-tracking, drain-coordination, DI-wiring]
dependency_graph:
  requires: [ConnectionTracker, NodeSelector, model_not_found_error, model_unavailable_error]
  provides: [get_node_selector, drain-coordination, connection-tracking, model-aware-routing-e2e]
  affects: [inference_proxy/api/routes.py, inference_proxy/config/dependencies.py, inference_proxy/main.py, inference_proxy/discovery/registry.py, inference_proxy/discovery/watcher.py]
tech_stack:
  added: []
  patterns: [drain-on-delete, auto-remove-drained, connection-tracking-try-finally, model-aware-error-branching]
key_files:
  created: []
  modified:
    - inference_proxy/api/routes.py
    - inference_proxy/config/dependencies.py
    - inference_proxy/main.py
    - inference_proxy/discovery/registry.py
    - inference_proxy/discovery/watcher.py
    - tests/conftest.py
    - tests/api/test_routes.py
    - tests/discovery/test_registry.py
    - tests/discovery/test_watcher.py
decisions:
  - "Registry owns drain state transition via drain() method (SRP -- watcher dispatches, registry manages state)"
  - "Empty registry returns 503 no_nodes regardless of requested model (preserves Phase 3 backwards compatibility)"
  - "DRAINING nodes excluded from /v1/models response (clients only see models accepting new requests)"
  - "_scan_drained_nodes runs after every proxy call to clean up any draining nodes with 0 connections"
metrics:
  duration: 8m
  completed: 2026-06-24
---

# Phase 04 Plan 02: Route Wiring and Drain Coordination Summary

End-to-end model-aware least-connections routing with connection tracking, drain-on-delete coordination, and auto-removal of drained nodes when connection count reaches zero.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| ef9071a | test | Add failing tests for registry drain and watcher drain coordination (RED) |
| af9322e | feat | Implement registry drain method and watcher drain coordination (GREEN) |
| b99b356 | test | Add failing tests for NodeSelector DI wiring and model-aware routing (RED) |
| 3dd61a8 | feat | Wire NodeSelector into DI, lifespan, and routes with model-aware routing (GREEN) |
| 200c979 | test | Add failing tests for connection tracking and drain auto-removal (RED) |
| 2b1439e | feat | Add connection tracking and drain auto-removal in route handlers (GREEN) |

## What Was Built

### Task 1: Registry drain method and watcher drain coordination

**Registry drain method** (`inference_proxy/discovery/registry.py`): Added `drain(node_id: str) -> bool` method that transitions a node's status to `NodeStatus.DRAINING` using `model_copy(update={"status": NodeStatus.DRAINING})`. Returns `True` if node was found and transitioned, `False` otherwise. Thread-safe via `self._lock`.

**Watcher drain coordination** (`inference_proxy/discovery/watcher.py`): Changed the DELETE event handler from calling `registry.remove(node_id)` to `registry.drain(node_id)`. When drain returns False (unknown node), logs a debug message and skips. This implements D-10 (DRAINING on etcd DELETE) and the drain trigger half of LBAL-02.

### Task 2: NodeSelector DI wiring, lifespan, and route handlers

**DI function** (`inference_proxy/config/dependencies.py`): Added `get_node_selector(request) -> NodeSelector` following the existing `get_registry`/`get_proxy_client` pattern.

**Lifespan** (`inference_proxy/main.py`): Creates `ConnectionTracker` and `NodeSelector` during startup, stores in `app.state.node_selector`.

**Route handlers** (`inference_proxy/api/routes.py`): Replaced `select_node(registry)` with `node_selector.select(model=model)` in all route handlers. Added `_select_error` helper that distinguishes: empty registry (503 no_nodes), model not found on any node (404 model_not_found), model exists but all nodes draining/unhealthy (503 model_unavailable). Updated `/v1/models` to filter out DRAINING nodes.

### Task 3: Connection tracking and drain auto-removal

**Connection tracking**: Wraps proxy calls with `tracker.increment(node.node_id)` before and `tracker.decrement(node.node_id)` in `finally` block, for both non-streaming and streaming paths. T-04-05 mitigated: try/finally ensures decrement always fires.

**Drain auto-removal** (`_maybe_remove_drained` and `_scan_drained_nodes`): After every proxy call completes, checks if the proxied node (and all other nodes) are DRAINING with 0 connections, and if so removes them from both registry and tracker. T-04-09 mitigated: only removes when both status is DRAINING (set by etcd DELETE) AND connection count is 0 (managed by try/finally). This completes LBAL-02 end-to-end.

## Test Coverage

| Test File | Tests Added | Coverage |
|-----------|-------------|----------|
| tests/discovery/test_registry.py | 4 | drain returns True/False, sets DRAINING status, preserves other fields |
| tests/discovery/test_watcher.py | 2 | DELETE sets DRAINING instead of removing, DELETE on non-existent is no-op |
| tests/api/test_routes.py | 10 | least-connections routing, model filtering, model not found (404), model unavailable (503), draining excluded from models, text completion model routing, streaming model not found, connection tracking (non-streaming + streaming), drain auto-removal |
| tests/conftest.py | 2 fixtures | connection_tracker, node_selector with DI override |

Total: 169 tests pass (16 new + 153 existing), 0 failures, 0 regressions.

## Verification Results

- `uv run pytest -x --tb=short`: 169 passed
- `uv run ruff check inference_proxy/ tests/`: Pre-existing B008 (FastAPI Depends pattern), UP035 (typing import), and test line length warnings only. No new issues introduced.
- `uv run mypy inference_proxy/api/routes.py inference_proxy/config/dependencies.py inference_proxy/main.py inference_proxy/discovery/registry.py`: Pre-existing `type-arg` warning in watcher.py only. No new issues.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed empty registry returning 404 instead of 503**
- **Found during:** Task 2
- **Issue:** With model-aware routing, an empty registry + model name in request triggered `model_not_found_error` (404) instead of `no_nodes_error` (503), breaking the existing test `test_chat_completion_no_nodes_returns_503`.
- **Fix:** Added `if not all_nodes: return no_nodes_error()` check at the top of `_select_error` before model-specific checks.
- **Files modified:** `inference_proxy/api/routes.py`
- **Commit:** 3dd61a8

## TDD Gate Compliance

### Task 1
- RED gate: `ef9071a` (test commit exists before implementation)
- GREEN gate: `af9322e` (feat commit exists after RED)
- REFACTOR gate: Not needed

### Task 2
- RED gate: `b99b356` (test commit exists before implementation)
- GREEN gate: `3dd61a8` (feat commit exists after RED)
- REFACTOR gate: Not needed

### Task 3
- RED gate: `200c979` (test commit exists before implementation)
- GREEN gate: `2b1439e` (feat commit exists after RED)
- REFACTOR gate: Not needed

## Known Stubs

None -- all components are fully implemented with production logic.

## Requirements Completed

- **DISC-03** (Model-aware filtering): Requests route exclusively to nodes serving the requested model via `NodeSelector.select(model=...)`.
- **LBAL-01** (Least-connections): Requests route to the node with fewest active connections via ConnectionTracker + NodeSelector sort.
- **LBAL-02** (Drain before removal): Nodes marked DRAINING on etcd DELETE (Task 1), auto-removed when connection count reaches 0 (Task 3).

## Self-Check: PASSED
