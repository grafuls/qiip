---
phase: 06-observability-and-admin
plan: 02
subsystem: api/admin
tags: [admin, endpoint, node-status, pydantic]
dependency_graph:
  requires: [06-01]
  provides: [admin-node-endpoint]
  affects: [inference_proxy/main.py]
tech_stack:
  added: []
  patterns: [APIRouter with prefix, frozen Pydantic response model]
key_files:
  created:
    - inference_proxy/models/admin.py
    - inference_proxy/api/admin.py
    - tests/models/test_admin.py
    - tests/api/test_admin.py
  modified:
    - inference_proxy/main.py
decisions:
  - "Used str for status field (not NodeStatus enum) to serialize enum value in response"
  - "Placed admin response model in models/admin.py following models/node.py pattern"
  - "Included admin router in OpenAPI docs via tags=['admin'] for debugging visibility"
metrics:
  duration: 183s
  completed: "2026-06-25T12:40:43Z"
  tasks_completed: 1
  tasks_total: 1
  test_count: 7
  files_created: 4
  files_modified: 1
---

# Phase 06 Plan 02: Admin Node Endpoint Summary

Admin APIRouter at /admin/nodes returning a flat JSON list of all registered nodes with node_id, endpoint, model, and status fields using a frozen AdminNodeResponse Pydantic model.

## Completed Tasks

| # | Task | Commit | Type |
|---|------|--------|------|
| 1 | AdminNodeResponse model and admin endpoint with tests (RED) | c91e787 | test |
| 1 | AdminNodeResponse model and admin endpoint with tests (GREEN) | 13e47fb | feat |

## What Was Built

### AdminNodeResponse Model (`inference_proxy/models/admin.py`)
- Frozen Pydantic BaseModel with `ConfigDict(frozen=True)` following NodeCapabilities pattern
- Four string fields: node_id, endpoint, model, status
- Status is str (not NodeStatus enum) because the response serializes the enum's value
- Module docstring references D-07 and D-08

### Admin Router (`inference_proxy/api/admin.py`)
- `admin_router = APIRouter(prefix="/admin", tags=["admin"])` per D-05 and D-06
- Single endpoint `GET /nodes` returning `list[AdminNodeResponse]`
- Injects NodeRegistry via `Depends(get_registry)` from existing DI providers
- Calls `registry.get_all()` and maps each Node to AdminNodeResponse with `n.status.value`
- Returns flat list directly (FastAPI serializes as JSON array per D-08)
- All statuses (HEALTHY, UNHEALTHY, DRAINING) included in response

### Main App Wiring (`inference_proxy/main.py`)
- Import `admin_router` from `inference_proxy.api.admin`
- `application.include_router(admin_router)` after existing proxy routes

### Test Coverage
- `tests/models/test_admin.py`: 2 tests (creation with valid fields, frozen immutability)
- `tests/api/test_admin.py`: 5 tests across 3 test classes
  - `TestAdminNodesPopulated`: two nodes return 200, exactly four fields per node, mixed statuses all appear
  - `TestAdminNodesEmpty`: empty registry returns empty list
  - `TestAdminNodesResponseShape`: response is flat JSON array

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all functionality fully wired.

## Verification Results

- `uv run pytest tests/models/test_admin.py tests/api/test_admin.py -x --tb=short -q` -- 7 passed
- `uv run pytest tests/ -x --tb=short -q` -- 226 passed (219 existing + 7 new, no regressions)
- `uv run ruff check inference_proxy/models/admin.py inference_proxy/api/admin.py inference_proxy/main.py` -- only pre-existing B008 warning (FastAPI Depends pattern)

## TDD Gate Compliance

- RED gate: `test(06-02)` commit c91e787 -- 7 failing tests (ImportError: module not found)
- GREEN gate: `feat(06-02)` commit 13e47fb -- all 7 tests passing with implementation
- REFACTOR gate: skipped (code follows existing patterns, no cleanup needed)

## Self-Check: PASSED

- inference_proxy/models/admin.py: FOUND
- inference_proxy/api/admin.py: FOUND
- tests/models/test_admin.py: FOUND
- tests/api/test_admin.py: FOUND
- inference_proxy/main.py modified: FOUND
- Commit c91e787 (RED): FOUND
- Commit 13e47fb (GREEN): FOUND
