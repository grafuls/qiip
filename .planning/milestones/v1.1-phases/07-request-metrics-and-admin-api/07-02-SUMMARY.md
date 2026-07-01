---
phase: "07"
plan: "02"
subsystem: "routing, api, admin"
tags: [metrics, di, admin-api, request-counting]
dependency_graph:
  requires: [RequestMetrics, AdminMetricsResponse, CircuitBreaker.state]
  provides: [get_request_metrics, "/admin/metrics endpoint", "request counting on proxy calls"]
  affects: [inference_proxy/api/routes.py, inference_proxy/api/admin.py, inference_proxy/main.py]
tech_stack:
  added: []
  patterns: [fastapi-depends-injection, app-state-lifespan-wiring]
key_files:
  created: []
  modified:
    - inference_proxy/config/dependencies.py
    - inference_proxy/main.py
    - inference_proxy/api/routes.py
    - inference_proxy/api/admin.py
    - tests/conftest.py
    - tests/api/test_admin.py
decisions:
  - "Wired conftest request_metrics in Task 1 (not Task 2) to keep tests green between commits"
metrics:
  duration: "5m 54s"
  completed: "2026-06-29T21:02:24Z"
---

# Phase 07 Plan 02: Admin Endpoint Wiring and Request Counting Summary

RequestMetrics wired into DI/lifespan/route handlers with per-request counting, plus /admin/metrics endpoint serving aggregate counters -- 247 tests pass.

## What Was Done

### Task 1: Wire DI, lifespan, and counter increments in route handlers
- Added `get_request_metrics` DI provider in dependencies.py following existing `get_circuit_breaker_registry` pattern
- Created `RequestMetrics()` in lifespan, stored on `app.state.request_metrics`
- `_proxy_non_streaming`: calls `record_request` on first attempt, `record_node_attempt` on retries (per D-03)
- `_stream_completion`: calls `record_request` after `tracker.increment` (no retries in streaming)
- Both `chat_completions` and `text_completions` inject `request_metrics` via `Depends(get_request_metrics)`
- Wired `request_metrics` fixture and DI override into test conftest to keep existing tests green
- Commit: 708b614

### Task 2: Add /admin/metrics endpoint and enriched admin tests
- Added `GET /admin/metrics` returning `AdminMetricsResponse` with total_requests, per_model, per_node
- Added `TestAdminNodesEnriched` (3 tests): active_connections from tracker, circuit_breaker_state default closed, circuit_breaker_state open after failures
- Added `TestAdminMetrics` (3 tests): returns 200, empty by default, reflects recorded data
- 247 total tests pass (6 new)
- Commit: 65c7d6b

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wired conftest request_metrics in Task 1 instead of Task 2**
- **Found during:** Task 1
- **Issue:** After adding `request_metrics` as a required parameter to `_proxy_non_streaming` and `_stream_completion`, existing tests that exercised proxy routes failed with `AttributeError: 'State' object has no attribute 'request_metrics'`
- **Fix:** Added `request_metrics` fixture and DI override to `tests/conftest.py` in Task 1 to keep tests green between commits
- **Files modified:** tests/conftest.py
- **Commit:** 708b614

## Verification

- `uv run pytest tests/api/test_admin.py -x -q`: 11 passed
- `uv run pytest tests/ -x -q`: 247 passed
- Import check: `from inference_proxy.config.dependencies import get_request_metrics` succeeds
- Lint (ruff): pre-existing B008 warnings only (Depends pattern used throughout codebase)
- Type check (mypy --strict): pre-existing errors in etcd_client.py and watcher.py only

## Self-Check: PASSED
