---
phase: 05-resilience
plan: 02
subsystem: resilience
tags: [retry-failover, circuit-breaker-recording, shutdown-middleware, lifespan-wiring, graceful-drain]
dependency_graph:
  requires: [CircuitBreaker, CircuitBreakerRegistry, run_health_checker, ResilienceSettings, get_circuit_breaker_registry]
  provides: [ShutdownMiddleware, retry-with-failover, exclude_node_ids, circuit-breaker-integration]
  affects: [inference_proxy/main.py, inference_proxy/api/routes.py, inference_proxy/routing/node_selector.py]
tech_stack:
  added: []
  patterns: [retry-with-exclude, middleware-based-shutdown, lifespan-health-thread, circuit-breaker-trip-to-unhealthy]
key_files:
  created:
    - inference_proxy/resilience/shutdown.py
    - tests/resilience/test_shutdown.py
  modified:
    - inference_proxy/routing/node_selector.py
    - inference_proxy/api/routes.py
    - inference_proxy/main.py
    - tests/conftest.py
    - tests/api/test_routes.py
    - tests/routing/test_node_selector.py
decisions:
  - "Retry loop uses exclude_node_ids set to avoid re-selecting failed nodes"
  - "_record_failure_and_trip extracted as helper per SRP for circuit breaker failure + UNHEALTHY marking"
  - "_is_retryable predicate separates retry classification from retry flow"
  - "Streaming records circuit breaker on [DONE] receipt (success) or exception (failure) but does not retry"
  - "ShutdownMiddleware uses BaseHTTPMiddleware with getattr for shutting_down safety"
  - "conftest.py max_retries changed from 1 to 3 to match production default and enable retry tests"
metrics:
  duration: 11m
  completed: "2026-06-25T08:27:19Z"
  tasks: 2
  files_created: 2
  files_modified: 6
  tests_added: 20
  tests_total: 213
---

# Phase 05 Plan 02: Resilience Wiring Summary

Retry with failover for non-streaming requests via exclude_node_ids, circuit breaker recording on all proxy calls, and graceful shutdown middleware with /health exemption

## What Was Built

### Task 1: Retry, Circuit Breaker Recording, and Exclude Support

- `NodeSelector.select` extended with `exclude_node_ids: set[str] | None` parameter. After HEALTHY filter, excluded nodes are removed from candidates before model filter and least-connections sort. Defaults to None (no behavior change for existing callers).
- `_proxy_non_streaming` refactored into a retry loop bounded by `max_retries` (from `RoutingSettings`, default 3). On retryable failures (ConnectError, TimeoutException, 5xx HTTPStatusError), the failed node is added to the exclude set and the next attempt selects a different node.
- `_is_retryable` predicate classifies exceptions that should trigger retry.
- `_record_failure_and_trip` helper records circuit breaker failure and marks node UNHEALTHY when breaker trips (D-07).
- Route handlers `chat_completions` and `text_completions` accept `CircuitBreakerRegistry` via `Depends(get_circuit_breaker_registry)` and pass to helper functions.
- `_stream_completion` records `record_success()` on successful stream completion and `record_failure()` + UNHEALTHY marking on exceptions. No mid-stream retry.
- `conftest.py` wires `CircuitBreakerRegistry` fixture, DI override, and `shutting_down = False` into app fixture.

### Task 2: Shutdown Middleware and Lifespan Wiring

- `ShutdownMiddleware` (Starlette `BaseHTTPMiddleware`): checks `app.state.shutting_down`; returns 503 with OpenAI-compatible error body for all routes except `/health` (D-12).
- `main.py` lifespan startup: creates `CircuitBreakerRegistry` with configured threshold, starts health checker thread with configured interval and failure threshold, sets `app.state.shutting_down = False`.
- `main.py` lifespan shutdown: sets `shutting_down = True`, logs shutdown initiation, waits `graceful_shutdown_timeout` seconds for in-flight drain (D-10), then closes HTTP client, sets stop_event, joins both watch and health threads.
- `ShutdownMiddleware` added via `application.add_middleware()` before router inclusion.

## Task Completion

| Task | Name | Commit(s) | Files |
|------|------|-----------|-------|
| 1 | Retry, circuit breaker, exclude_node_ids | a82f2ee (RED), 4b83e9d (GREEN) | node_selector.py, routes.py, conftest.py, test_routes.py, test_node_selector.py |
| 2 | Shutdown middleware and lifespan wiring | fc57774 (RED), b6a673f (GREEN) | shutdown.py, main.py, test_shutdown.py |

## TDD Gate Compliance

- Task 1: RED commit `a82f2ee` (test), GREEN commit `4b83e9d` (feat) -- gate sequence valid
- Task 2: RED commit `fc57774` (test), GREEN commit `b6a673f` (feat) -- gate sequence valid

## Test Results

- 6 node selector exclude tests: all pass
- 8 retry and circuit breaker route tests: all pass
- 6 shutdown middleware tests: all pass
- 213 total tests: all pass (193 existing + 20 new, zero regressions)
- Lint: clean on all created/modified source files (pre-existing B008/UP035/E501 in other files)
- Type check: clean on all created/modified source files (pre-existing errors in discovery modules)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test determinism for retry tests**
- **Found during:** Task 1 GREEN phase
- **Issue:** Retry tests assumed node-1 would be selected first, but with 0 connections on both nodes, random tie-breaking could select node-2 first, causing unused mock assertion errors.
- **Fix:** Increment node-2's connection count before the test to guarantee node-1 is selected first by least-connections.
- **Files modified:** tests/api/test_routes.py
- **Commit:** 4b83e9d

**2. [Rule 1 - Bug] Circuit breaker test DI routing**
- **Found during:** Task 1 GREEN phase
- **Issue:** Tests set `app.state.circuit_breaker_registry` directly but routes used the DI override from conftest, so the custom registry was ignored.
- **Fix:** Tests override `app.dependency_overrides[get_circuit_breaker_registry]` instead of setting app.state directly.
- **Files modified:** tests/api/test_routes.py
- **Commit:** 4b83e9d

**3. [Rule 3 - Blocking] conftest max_retries too low**
- **Found during:** Task 1 GREEN phase
- **Issue:** test_settings had `max_retries=1` which meant only 1 attempt (no retries), preventing retry tests from working.
- **Fix:** Changed `max_retries=1` to `max_retries=3` (matching production default).
- **Files modified:** tests/conftest.py
- **Commit:** 4b83e9d

## Self-Check: PASSED

All 9 files verified present. All 4 commits verified in git log.
