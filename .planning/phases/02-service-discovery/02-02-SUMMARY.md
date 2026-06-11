---
phase: 02-service-discovery
plan: 02
subsystem: discovery
tags: [watcher, lifespan, threading, reconnection, dependency-injection]

# Dependency graph
requires:
  - phase: 02-service-discovery
    plan: 01
    provides: EtcdClient, NodeRegistry, serializer, etcd3gw dependency
provides:
  - run_watcher function with reconnection loop and event dispatch
  - _initial_load function for startup node fetch
  - get_registry FastAPI dependency
  - Lifespan integration with full discovery pipeline
affects: [03-routing (registry available via Depends(get_registry))]

# Tech tracking
tech-stack:
  added: []
  patterns: [reconnection loop for etcd watch, threading.Event for shutdown signaling, app.state for service injection]

key-files:
  created:
    - inference_proxy/discovery/watcher.py
  modified:
    - inference_proxy/main.py
    - inference_proxy/config/dependencies.py
    - tests/discovery/test_watcher.py
    - tests/conftest.py
    - tests/test_app.py

key-decisions:
  - "run_watcher uses stop_event.wait(timeout=retry_delay) for interruptible sleep on reconnect"
  - "get_registry reads from request.app.state (no @lru_cache) because registry is created during lifespan"
  - "_initial_load is synchronous at startup per D-05 -- acceptable during lifespan init"
  - "Watch thread is daemon=True so it does not block process exit if join times out"

patterns-established:
  - "Reconnection loop: while not stop_event.is_set() wrapping watch_prefix with try/except/finally(cancel)"
  - "Event dispatch: event.get('type', 'PUT') handles proto3 JSON absent-field semantics"
  - "Defensive encoding: isinstance check for bytes vs str on both keys and values"
  - "Lifespan service wiring: create services before yield, cleanup after yield"

requirements-completed: [DISC-02]

# Metrics
duration: 3m 56s
completed: 2026-06-11
---

# Phase 2 Plan 02: Watcher and Lifespan Integration Summary

**Watch thread with reconnection loop, lifespan-managed discovery pipeline, and get_registry dependency completing the service discovery layer with 14 new tests**

## Performance

- **Duration:** 3m 56s
- **Started:** 2026-06-11T06:30:10Z
- **Completed:** 2026-06-11T06:34:06Z
- **Tasks:** 2
- **Files created:** 1 (watcher.py)
- **Files modified:** 5 (main.py, dependencies.py, test_watcher.py, conftest.py, test_app.py)

## Accomplishments
- Watch thread with reconnection loop handles etcd stream disconnections transparently
- Event dispatch correctly handles PUT (type field absent) and DELETE events per proto3 JSON semantics
- Bytes and str keys/values handled defensively throughout
- cancel() always called via finally block preventing resource leaks
- Lifespan wires full discovery pipeline: EtcdClient -> _initial_load -> watch thread -> app.state.registry
- etcd unavailability at startup handled gracefully (empty registry, warning log) per D-09
- get_registry dependency exposes NodeRegistry to FastAPI handlers via Depends()
- Full test suite: 95 tests passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Watch thread with reconnection loop (TDD)**
   - RED: `f5d7191` - failing tests for watcher event dispatch and reconnection
   - GREEN: `e042d6a` - watcher implementation with all 10 tests passing
2. **Task 2: Lifespan integration and get_registry dependency** - `c598027`

## Files Created/Modified
- `inference_proxy/discovery/watcher.py` - run_watcher with reconnection loop, _handle_event with PUT/DELETE dispatch
- `inference_proxy/main.py` - Lifespan with EtcdClient, NodeRegistry, _initial_load, watch thread start/stop
- `inference_proxy/config/dependencies.py` - get_registry(request) dependency returning app.state.registry
- `tests/discovery/test_watcher.py` - 10 tests: PUT/DELETE events, bytes handling, reconnection, stop, cancel
- `tests/conftest.py` - Added test_registry fixture, wired into app fixture
- `tests/test_app.py` - 4 new tests: registry in app.state, lifespan integration, etcd unavailability, get_registry

## Decisions Made
- run_watcher uses stop_event.wait(timeout=retry_delay) for interruptible sleep -- cleaner than time.sleep with polling
- get_registry does NOT use @lru_cache because the registry is a per-app singleton stored in app.state, not constructed by the dependency
- _initial_load wraps entire body in try/except for graceful degradation when etcd is unavailable
- Watch thread created as daemon=True so it cannot block process exit if join(timeout=10) times out

## Deviations from Plan

None -- plan executed exactly as written.

## TDD Gate Compliance

Task 1 followed the RED/GREEN cycle:
1. RED gate: `f5d7191` - `test(02-02)` commit with failing tests (ModuleNotFoundError)
2. GREEN gate: `e042d6a` - `feat(02-02)` commit with passing implementation
3. REFACTOR: Not needed -- implementation was clean from first pass

## Issues Encountered
None

## User Setup Required
None -- no external service configuration required.

## Self-Check: PASSED

All 1 created file and 5 modified files verified on disk. All 3 task commits (f5d7191, e042d6a, c598027) found in git log.

---
*Phase: 02-service-discovery*
*Completed: 2026-06-11*
