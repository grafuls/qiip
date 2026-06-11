---
phase: 03-request-proxying-and-streaming
plan: 02
subsystem: api
tags: [fastapi, httpx, httpx-sse, sse, openai-api, proxy, streaming, routes]

# Dependency graph
requires:
  - phase: 03-request-proxying-and-streaming
    provides: ProxyClient wrapper, select_node(), map_proxy_error(), no_nodes_error(), ProxySettings, get_proxy_client DI
  - phase: 01-foundation
    provides: Pydantic OpenAI models, Node/NodeStatus models, NodeRegistry, Settings, create_app factory
  - phase: 02-service-discovery
    provides: NodeRegistry with add/remove/get/get_all, EtcdClient, watcher
provides:
  - FastAPI APIRouter with POST /v1/chat/completions, POST /v1/completions, GET /v1/models
  - SSE streaming proxy using httpx-sse consumption and FastAPI format_sse_event emission
  - Lifespan httpx.AsyncClient lifecycle with ProxySettings-driven timeouts and limits
  - Enhanced /health endpoint with nodes_registered count
  - Integration test suite covering all 8 phase requirements (PROXY-01 through PROXY-05, STRM-01 through STRM-03)
affects: [04-routing, 05-resilience]

# Tech tracking
tech-stack:
  added: []
  patterns: [format_sse_event for manual SSE pass-through, response_model=None for union return types, httpx_mock IteratorStream for SSE test mocking]

key-files:
  created:
    - inference_proxy/api/routes.py
    - tests/api/test_routes.py
  modified:
    - inference_proxy/main.py
    - tests/conftest.py
    - tests/test_app.py

key-decisions:
  - "Use format_sse_event() for SSE pass-through instead of ServerSentEvent objects -- manual EventSourceResponse construction requires bytes/strings, not Pydantic models"
  - "Set response_model=None on endpoints returning JSONResponse | EventSourceResponse -- FastAPI cannot generate response models from response class unions"
  - "Close httpx client before signaling watch thread stop -- ensures clean async resource shutdown before synchronous thread join"

patterns-established:
  - "Manual SSE pass-through: consume upstream SSE with httpx-sse aconnect_sse, re-emit with format_sse_event(data_str=sse.data) to avoid double JSON encoding"
  - "Integration test pattern: register nodes in test_registry, mock upstream httpx responses with httpx_mock, assert on client response"
  - "Streaming test pattern: use IteratorStream with SSE-formatted byte chunks for pytest-httpx streaming mocks"

requirements-completed: [PROXY-01, PROXY-02, PROXY-03, PROXY-04, STRM-01, STRM-02, STRM-03]

# Metrics
duration: 5min
completed: 2026-06-11
---

# Phase 3 Plan 02: API Routes and Integration Tests Summary

**OpenAI-compatible API router with chat/text completion proxying (streaming + non-streaming), model listing, enhanced health, and 15 integration tests covering all 8 phase requirements**

## Performance

- **Duration:** 5 min
- **Started:** 2026-06-11T14:46:04Z
- **Completed:** 2026-06-11T14:51:17Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Complete API router with POST /v1/chat/completions, POST /v1/completions (streaming + non-streaming), and GET /v1/models
- SSE streaming proxy consuming upstream vLLM events via httpx-sse and re-emitting via format_sse_event for verbatim pass-through
- Lifespan creates httpx.AsyncClient with ProxySettings timeouts (120s read for LLM inference) and connection limits (100 max), stores ProxyClient in app.state
- Enhanced /health endpoint returns nodes_registered count from registry
- 15 new integration tests covering all requirements, 130 total tests passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: API routes and lifespan integration** - `e88275a` (feat)
2. **Task 2: Integration tests for all API routes and updated fixtures** - `90c7e08` (test)

## Files Created/Modified
- `inference_proxy/api/routes.py` - APIRouter with /v1/chat/completions, /v1/completions, /v1/models endpoints and _stream_completion helper
- `inference_proxy/main.py` - Lifespan creates httpx.AsyncClient + ProxyClient, enhanced /health with nodes_registered, includes router
- `tests/api/test_routes.py` - 14 integration tests across 7 test classes covering all phase requirements
- `tests/conftest.py` - Added proxy_client fixture and get_proxy_client dependency override
- `tests/test_app.py` - Updated health test assertions for nodes_registered, added test_health_with_nodes

## Decisions Made
- Used format_sse_event() instead of ServerSentEvent objects for SSE pass-through because manually constructed EventSourceResponse (a StreamingResponse) expects bytes/strings, not Pydantic models. The FastAPI routing layer only intercepts ServerSentEvent objects when the route handler itself is a generator with response_class=EventSourceResponse.
- Set response_model=None on chat/text completion endpoints because FastAPI cannot create a response model from JSONResponse | EventSourceResponse union type.
- httpx client aclose() runs before watch thread stop signal -- ensures clean async resource teardown before synchronous operations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Switched from ServerSentEvent to format_sse_event for SSE emission**
- **Found during:** Task 1 (verified during Task 2 testing)
- **Issue:** Plan specified using ServerSentEvent(raw_data=sse.data), but when EventSourceResponse is manually constructed (not via generator route pattern), it's a StreamingResponse that calls .encode() on yielded items. ServerSentEvent is a Pydantic model without .encode(), causing AttributeError.
- **Fix:** Import format_sse_event from fastapi.sse, yield format_sse_event(data_str=sse.data) which produces properly formatted bytes.
- **Files modified:** inference_proxy/api/routes.py
- **Verification:** All 3 streaming tests pass (SSE events received with correct content and [DONE] signal)
- **Committed in:** 90c7e08 (Task 2 commit)

**2. [Rule 1 - Bug] Added response_model=None to completion endpoints**
- **Found during:** Task 1 (route import verification)
- **Issue:** Return type annotation JSONResponse | EventSourceResponse caused FastAPI to try creating a response model from the union, raising FastAPIError.
- **Fix:** Added response_model=None to @router.post() decorators for chat_completions and text_completions.
- **Files modified:** inference_proxy/api/routes.py
- **Verification:** Routes import successfully, all tests pass
- **Committed in:** e88275a (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both auto-fixes necessary for correctness. The plan's recommended SSE pattern (ServerSentEvent with raw_data) works correctly when the route handler is a generator decorated with response_class=EventSourceResponse, but not when manually constructing and returning EventSourceResponse. The format_sse_event approach achieves the same goal (verbatim pass-through without double encoding). No scope creep.

## Issues Encountered

None beyond the auto-fixed deviations.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All OpenAI-compatible API endpoints are functional and tested
- Phase 4 (routing) can add intelligent node selection strategies without modifying route handlers -- only select_node() implementation changes
- Phase 5 (resilience) can add retry logic, circuit breakers around ProxyClient.forward() calls
- 130 tests provide a solid regression safety net for future changes

## Self-Check: PASSED

- inference_proxy/api/routes.py: FOUND
- tests/api/test_routes.py: FOUND
- Task 1 commit e88275a: FOUND
- Task 2 commit 90c7e08: FOUND
- Full test suite: 130 passed, 0 failed

---
*Phase: 03-request-proxying-and-streaming*
*Completed: 2026-06-11*
