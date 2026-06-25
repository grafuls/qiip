---
phase: 06-observability-and-admin
plan: 01
subsystem: api/middleware
tags: [observability, middleware, logging, structlog]
dependency_graph:
  requires: [05-01, 05-02]
  provides: [request-logging-middleware, target-node-tracking]
  affects: [inference_proxy/api/routes.py, inference_proxy/main.py]
tech_stack:
  added: []
  patterns: [BaseHTTPMiddleware, request.state cross-layer data passing]
key_files:
  created:
    - inference_proxy/api/middleware.py
    - tests/api/test_middleware.py
  modified:
    - inference_proxy/api/routes.py
    - inference_proxy/main.py
decisions:
  - "Used time.perf_counter() for monotonic high-resolution timing"
  - "Placed middleware in api/middleware.py alongside route handlers (SRP: HTTP-layer concerns together)"
  - "Named Starlette request parameter starlette_request to avoid shadowing Pydantic request parameter"
metrics:
  duration: 352s
  completed: "2026-06-25T12:33:17Z"
  tasks_completed: 1
  tasks_total: 1
  test_count: 6
  files_created: 2
  files_modified: 2
---

# Phase 06 Plan 01: Request Logging Middleware Summary

RequestLoggingMiddleware via BaseHTTPMiddleware producing structured log entries with method, path, status_code, duration_ms, and target_node for every HTTP request using structlog.

## Completed Tasks

| # | Task | Commit | Type |
|---|------|--------|------|
| 1 | RequestLoggingMiddleware and route handler target_node tracking (RED) | 4a13ded | test |
| 1 | RequestLoggingMiddleware and route handler target_node tracking (GREEN) | 1eaa0a5 | feat |

## What Was Built

### RequestLoggingMiddleware (`inference_proxy/api/middleware.py`)
- BaseHTTPMiddleware subclass following the ShutdownMiddleware pattern
- Measures request duration using `time.perf_counter()` (monotonic, high-resolution)
- Reads `target_node` from `request.state` using safe `getattr(..., None)` access
- Emits structured log entry via `structlog.get_logger().info("request", ...)` with method, path, status_code, duration_ms, target_node
- Logs ALL requests per D-03 -- no path filtering or log level differentiation

### Route Handler Modifications (`inference_proxy/api/routes.py`)
- Added `starlette_request: StarletteRequest` parameter to `chat_completions` and `text_completions` handlers
- Added `starlette_request: StarletteRequest | None = None` parameter to `_proxy_non_streaming` and `_stream_completion` helpers
- Both helpers set `starlette_request.state.target_node = node.endpoint` after successful node selection, guarded by `if starlette_request is not None`
- Import of `Request as StarletteRequest` from fastapi added alongside existing imports

### Middleware Wiring (`inference_proxy/main.py`)
- `RequestLoggingMiddleware` added after `ShutdownMiddleware` (LIFO ordering: logging is outermost, wraps everything including shutdown 503 responses)

### Test Coverage (`tests/api/test_middleware.py`)
- 6 test methods across 3 test classes using `structlog.testing.capture_logs()`
- `TestRequestLoggingFields`: health and models routes log with target_node=None
- `TestRequestLoggingTargetNode`: chat completions, text completions, and streaming routes log with target_node set to node endpoint
- `TestRequestLoggingErrorCases`: failed requests (no nodes) still produce log entries with error status codes

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all functionality fully wired.

## Verification Results

- `uv run pytest tests/api/test_middleware.py -x --tb=short -q` -- 6 passed
- `uv run pytest tests/ -x --tb=short -q` -- 219 passed (213 existing + 6 new, no regressions)
- `uv run ruff check inference_proxy/api/middleware.py inference_proxy/api/routes.py inference_proxy/main.py` -- only pre-existing warnings (B008 for FastAPI Depends, UP035 for typing import)

## TDD Gate Compliance

- RED gate: `test(06-01)` commit 4a13ded -- 6 failing tests for middleware behavior
- GREEN gate: `feat(06-01)` commit 1eaa0a5 -- all tests passing with implementation
- REFACTOR gate: skipped (no cleanup needed; code follows existing patterns)

## Self-Check: PASSED

- inference_proxy/api/middleware.py: FOUND
- tests/api/test_middleware.py: FOUND
- Commit 4a13ded (RED): FOUND
- Commit 1eaa0a5 (GREEN): FOUND
- 06-01-SUMMARY.md: FOUND
