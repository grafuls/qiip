---
phase: 04-intelligent-routing
plan: 01
subsystem: routing
tags: [routing, load-balancing, least-connections, model-filtering, error-handling]
dependency_graph:
  requires: []
  provides: [ConnectionTracker, NodeSelector, model_not_found_error, model_unavailable_error]
  affects: [inference_proxy/routing/, inference_proxy/api/errors.py]
tech_stack:
  added: []
  patterns: [thread-safe-counter, strategy-class, constructor-injection, random-tie-break]
key_files:
  created:
    - inference_proxy/routing/connection_tracker.py
    - inference_proxy/routing/node_selector.py
    - tests/routing/__init__.py
    - tests/routing/test_connection_tracker.py
    - tests/routing/test_node_selector.py
  modified:
    - inference_proxy/api/errors.py
    - tests/api/test_errors.py
decisions:
  - "ConnectionTracker uses dict[str, int] + threading.Lock following NodeRegistry pattern (D-01)"
  - "NodeSelector is a strategy class with constructor injection of registry and tracker (D-07)"
  - "Tie-breaking uses random.choice among nodes with equal minimum connection counts (D-03)"
  - "has_model checks all nodes regardless of status to distinguish 404 vs 503 (D-04, D-06)"
metrics:
  duration: 4m
  completed: 2026-06-24
---

# Phase 04 Plan 01: Routing Building Blocks Summary

Thread-safe connection counter, least-connections model-aware node selector with random tie-breaking, and OpenAI error factories for model-not-found (404) and model-unavailable (503).

## Commits

| Hash | Type | Description |
|------|------|-------------|
| f7bcb6b | test | Add failing tests for ConnectionTracker, NodeSelector, and error factories (RED) |
| 281527b | feat | Implement ConnectionTracker, NodeSelector, and error factories (GREEN) |

## What Was Built

### ConnectionTracker (`inference_proxy/routing/connection_tracker.py`)
Thread-safe per-node active connection counter using `dict[str, int]` protected by `threading.Lock`, following the NodeRegistry pattern. Methods: `increment`, `decrement` (floored at 0), `get` (defaults to 0), `get_all` (returns copy), `remove`. Structlog debug logging on all mutations.

### NodeSelector (`inference_proxy/routing/node_selector.py`)
Strategy class replacing Phase 3's `select_node` pure function. Constructor takes `NodeRegistry` and `ConnectionTracker` via dependency injection. `select(model=None)` filters to HEALTHY nodes, optionally filters by exact model name match, sorts by active connection count, and breaks ties randomly via `random.choice`. `has_model(model)` checks if any node (any status) serves the model -- used by callers to distinguish 404 from 503. Exposes `tracker` property for route handlers to access for increment/decrement.

### Error Factories (`inference_proxy/api/errors.py`)
Two new factory functions following the existing `no_nodes_error` pattern:
- `model_not_found_error(model)` returns `(404, ErrorResponse)` with `type="invalid_request_error"`, `code="model_not_found"`
- `model_unavailable_error(model)` returns `(503, ErrorResponse)` with `type="server_error"`, `code="model_unavailable"`

## Test Coverage

| Test File | Tests | Coverage |
|-----------|-------|----------|
| tests/routing/test_connection_tracker.py | 9 | increment, decrement, get, get_all, remove, floor-at-zero, copy semantics |
| tests/routing/test_node_selector.py | 13 | empty registry, single node, least-connections, tie-breaking, model filtering, status filtering (DRAINING/UNHEALTHY/UNKNOWN), has_model |
| tests/api/test_errors.py | 2 new | model_not_found_error (404), model_unavailable_error (503) |

Total: 154 tests pass (24 new + 130 existing), 0 failures.

## Verification Results

- `uv run pytest -x --tb=short`: 154 passed
- `uv run ruff check`: All checks passed
- `uv run mypy inference_proxy/routing/ inference_proxy/api/errors.py`: Success, no issues found

## Deviations from Plan

None -- plan executed exactly as written.

## TDD Gate Compliance

- RED gate: `f7bcb6b` (test commit exists before implementation)
- GREEN gate: `281527b` (feat commit exists after RED)
- REFACTOR gate: Not needed -- code was clean after GREEN

## Known Stubs

None -- all components are fully implemented with production logic.

## Self-Check: PASSED
