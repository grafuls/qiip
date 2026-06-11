---
phase: 02-service-discovery
plan: 01
subsystem: discovery
tags: [etcd, etcd3gw, pydantic, threading, serialization]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Node model, EtcdSettings config, project structure
provides:
  - node_from_etcd and node_to_etcd serialization functions
  - Thread-safe NodeRegistry with add/remove/get/get_all
  - EtcdClient wrapper around etcd3gw with typed interface
  - etcd3gw installed as project dependency
affects: [02-service-discovery plan 02 (watcher + lifespan integration)]

# Tech tracking
tech-stack:
  added: [etcd3gw>=2.5.0]
  patterns: [DIP wrapper for external libraries, threading.Lock for cross-thread safety, graceful error handling with None returns]

key-files:
  created:
    - inference_proxy/discovery/serializer.py
    - inference_proxy/discovery/registry.py
    - inference_proxy/discovery/etcd_client.py
    - tests/discovery/__init__.py
    - tests/discovery/test_serializer.py
    - tests/discovery/test_registry.py
    - tests/discovery/test_etcd_client.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Only etcd_client.py imports etcd3gw -- all other modules depend on the wrapper (DIP)"
  - "threading.Lock chosen over asyncio.Lock because watch thread is an OS thread"
  - "node_from_etcd returns None on parse failure rather than raising exceptions"

patterns-established:
  - "DIP wrapper: External library isolated behind a thin typed wrapper class"
  - "Graceful parse: Return None + structlog warning for malformed data"
  - "Copy-on-read: get_all() returns list() copy to prevent external mutation"
  - "TDD for discovery modules: RED (import error) -> GREEN (implementation) flow"

requirements-completed: [DISC-01]

# Metrics
duration: 4min
completed: 2026-06-11
---

# Phase 2 Plan 01: Discovery Core Modules Summary

**Serializer, registry, and etcd client wrapper delivering the data layer for service discovery with 24 tests and etcd3gw dependency**

## Performance

- **Duration:** 3m 48s
- **Started:** 2026-06-11T06:22:42Z
- **Completed:** 2026-06-11T06:26:30Z
- **Tasks:** 3
- **Files created:** 7
- **Files modified:** 2 (pyproject.toml, uv.lock)

## Accomplishments
- Node serializer with graceful error handling for malformed/missing JSON from etcd
- Thread-safe NodeRegistry with concurrent access verified across 10 threads
- EtcdClient wrapper as sole consumer of etcd3gw (Dependency Inversion Principle)
- etcd3gw 2.7.0 installed as project dependency
- 24 tests (9 serializer + 9 registry + 6 etcd client) all passing
- Full test suite (81 tests) green with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Node serializer with graceful error handling** - `f5d8369` (test + feat)
2. **Task 2: Thread-safe NodeRegistry** - `f91e2e4` (feat)
3. **Task 3: etcd client wrapper with etcd3gw installation** - `9fb5c1f` (feat)

## Files Created/Modified
- `inference_proxy/discovery/serializer.py` - node_from_etcd/node_to_etcd conversion with graceful error handling
- `inference_proxy/discovery/registry.py` - Thread-safe NodeRegistry with threading.Lock
- `inference_proxy/discovery/etcd_client.py` - Thin DIP wrapper around etcd3gw.Etcd3Client
- `tests/discovery/__init__.py` - Package marker
- `tests/discovery/test_serializer.py` - 9 tests for serializer edge cases and roundtrip
- `tests/discovery/test_registry.py` - 9 tests including concurrent thread safety
- `tests/discovery/test_etcd_client.py` - 6 tests with mocked etcd3gw client
- `pyproject.toml` - Added etcd3gw>=2.5.0 to dependencies
- `uv.lock` - Updated lockfile with etcd3gw and transitive dependencies

## Decisions Made
- Only etcd_client.py imports etcd3gw (DIP compliance verified: 0 violations)
- threading.Lock used for registry (not asyncio.Lock) because watch thread is OS-level
- Serializer catches ValidationError in addition to json/type/value errors for Pydantic validation failures
- node_from_etcd handles both bytes and str keys defensively per RESEARCH.md Pitfall 2
- discovery/__init__.py kept empty (no public re-exports yet)

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None -- no external service configuration required.

## Next Phase Readiness
- Serializer, registry, and etcd client are ready for consumption by Plan 02 (watcher + lifespan integration)
- EtcdClient.get_prefix() and watch_prefix() delegate to etcd3gw, ready for watcher loop
- NodeRegistry ready to be stored in app.state and exposed via get_registry() dependency

## Self-Check: PASSED

All 7 created files verified on disk. All 3 task commits (f5d8369, f91e2e4, 9fb5c1f) found in git log.

---
*Phase: 02-service-discovery*
*Completed: 2026-06-11*
