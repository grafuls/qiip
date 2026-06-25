---
phase: 03-request-proxying-and-streaming
plan: 01
subsystem: api
tags: [httpx, httpx-sse, proxy, error-handling, node-selection, dependency-injection]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Pydantic OpenAI models (ErrorDetail, ErrorResponse), Node/NodeStatus models, NodeRegistry, Settings, dependencies.py DI pattern
  - phase: 02-service-discovery
    provides: NodeRegistry with add/remove/get/get_all, EtcdClient wrapper pattern
provides:
  - ProxyClient wrapper around httpx.AsyncClient with forward() and client property
  - select_node() function for first-available healthy node selection
  - map_proxy_error() mapping httpx exceptions to OpenAI-compatible error responses
  - no_nodes_error() helper for 503 when no nodes available
  - ProxySettings with configurable timeouts and connection limits
  - get_proxy_client DI function for FastAPI route handlers
affects: [03-02-PLAN, 04-routing, 05-resilience]

# Tech tracking
tech-stack:
  added: [httpx>=0.28, httpx-sse>=0.4.3]
  patterns: [ProxyClient wrapper (DIP), pure function error mapping, pure function node selection]

key-files:
  created:
    - inference_proxy/proxy/__init__.py
    - inference_proxy/proxy/client.py
    - inference_proxy/proxy/node_selector.py
    - inference_proxy/api/errors.py
    - tests/proxy/__init__.py
    - tests/proxy/test_client.py
    - tests/proxy/test_node_selector.py
    - tests/api/__init__.py
    - tests/api/test_errors.py
  modified:
    - pyproject.toml
    - uv.lock
    - inference_proxy/config/settings.py
    - inference_proxy/config/dependencies.py

key-decisions:
  - "ProxyClient receives pre-built httpx.AsyncClient via constructor injection -- lifecycle managed by lifespan, not the wrapper"
  - "select_node is a pure function returning first healthy node -- Phase 4 replaces the strategy without modifying callers"
  - "Error mapper returns (status_code, ErrorResponse) tuples -- callers decide how to convert to HTTP responses"

patterns-established:
  - "ProxyClient wrapper: sole consumer of httpx for proxy operations (DIP), exposes forward() and client property"
  - "Pure function error mapping: map_proxy_error converts exceptions to OpenAI error tuples"
  - "Pure function node selection: select_node(registry) -> Node | None, filterable and replaceable"

requirements-completed: [PROXY-05]

# Metrics
duration: 3min
completed: 2026-06-11
---

# Phase 3 Plan 01: Proxy Infrastructure Summary

**ProxyClient httpx wrapper, node selector, and OpenAI-compatible error mapping with full unit test coverage (14 tests)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-11T14:38:18Z
- **Completed:** 2026-06-11T14:41:29Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- ProxyClient wrapper around httpx.AsyncClient with forward() for non-streaming and client property for SSE streaming
- Pure function select_node() filtering to healthy nodes from the registry
- Comprehensive error mapping (ConnectError->502, TimeoutException->504, HTTPStatusError->upstream status, generic->500) plus no_nodes_error()->503
- ProxySettings with LLM-tuned defaults (120s read timeout, 100 max connections)
- get_proxy_client DI function following established app.state pattern
- 14 new unit tests with zero regressions (115 total)

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies and create ProxySettings, ProxyClient, node_selector, and error mapper** - `3e35b54` (feat)
2. **Task 2: Unit tests for ProxyClient, node_selector, and error mapper** - `4d7f23c` (test)

## Files Created/Modified
- `inference_proxy/proxy/__init__.py` - Package marker for proxy module
- `inference_proxy/proxy/client.py` - ProxyClient wrapper around httpx.AsyncClient
- `inference_proxy/proxy/node_selector.py` - select_node() pure function for first healthy node
- `inference_proxy/api/errors.py` - map_proxy_error() and no_nodes_error() error mapping
- `inference_proxy/config/settings.py` - Added ProxySettings with timeout and connection limit defaults
- `inference_proxy/config/dependencies.py` - Added get_proxy_client DI function
- `pyproject.toml` - Added httpx and httpx-sse dependencies
- `uv.lock` - Updated lock file
- `tests/proxy/__init__.py` - Test package marker
- `tests/proxy/test_client.py` - 4 tests for ProxyClient (forward + property)
- `tests/proxy/test_node_selector.py` - 5 tests for select_node edge cases
- `tests/api/__init__.py` - Test package marker
- `tests/api/test_errors.py` - 5 tests for error mapping (4 exception types + no_nodes)

## Decisions Made
- ProxyClient receives pre-built httpx.AsyncClient via constructor injection -- lifecycle managed by lifespan, not by the wrapper class (follows DIP, keeps resource management in one place)
- select_node is a pure function returning first healthy node -- Phase 4 will replace the strategy without modifying callers (OCP)
- Error mapper returns (status_code, ErrorResponse) tuples rather than raising exceptions -- callers decide how to convert to HTTP responses (SRP)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All proxy infrastructure building blocks are ready for Plan 02 API routes
- Plan 02 will consume ProxyClient, select_node, map_proxy_error, and get_proxy_client via dependency injection
- Lifespan modifications needed in Plan 02 to create httpx.AsyncClient and store ProxyClient in app.state

## Self-Check: PASSED

- All 10 created files exist on disk
- Both task commits (3e35b54, 4d7f23c) found in git log
- Full test suite: 115 passed, 0 failed

---
*Phase: 03-request-proxying-and-streaming*
*Completed: 2026-06-11*
