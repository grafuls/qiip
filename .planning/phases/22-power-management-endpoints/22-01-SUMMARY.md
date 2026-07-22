---
phase: 22-power-management-endpoints
plan: 01
subsystem: admin-api
tags: [power-management, redfish, admin-api, endpoints]
dependency_graph:
  requires: [phase-21-redfish-client]
  provides: [power-endpoints, power-models]
  affects: [admin-api]
tech_stack:
  added: []
  patterns: [redfish-dependency-injection, canonical-hostname-normalization]
key_files:
  created: []
  modified:
    - inference_proxy/models/admin.py
    - inference_proxy/api/admin.py
    - tests/api/test_admin.py
decisions:
  - "PowerAction enum values match _ACTION_TARGET_STATE keys exactly (On, ForceOff, GracefulRestart, ForceRestart)"
  - "POST uses body.action.value to pass string to RedfishClient, not enum name"
metrics:
  duration_seconds: 208
  completed: "2026-07-22T06:35:52Z"
  tasks: 2
  files_modified: 3
  tests_added: 12
  tests_total: 491
---

# Phase 22 Plan 01: Power Management Endpoints Summary

GET and POST power endpoints on admin API using Phase 21 RedfishClient with Pydantic enum validation and hostname normalization.

## Task Completion

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add power models and route handlers | 8f39024 | inference_proxy/models/admin.py, inference_proxy/api/admin.py |
| 2 | Add power endpoint tests | 8aa4a3a | tests/api/test_admin.py |

## What Was Built

- **PowerAction(str, Enum):** On, ForceOff, GracefulRestart, ForceRestart -- values match RedfishClient._ACTION_TARGET_STATE keys exactly.
- **PowerActionRequest:** Frozen Pydantic model with `action: PowerAction` field. Invalid actions rejected with 422 by Pydantic.
- **PowerStateResponse:** Frozen Pydantic model with `hostname: str` and `power_state: str`.
- **GET /admin/nodes/{hostname}/power:** Queries BMC power state via RedfishClient. Returns 503 when Redfish unconfigured, 502 on RedfishError. Applies canonical_hostname normalization.
- **POST /admin/nodes/{hostname}/power:** Executes power action synchronously (blocks until poll completes). Same 503/502 guards and hostname normalization. Uses `body.action.value` for string dispatch.

## Verification

- `uv run pytest tests/api/test_admin.py -x -q` -- 48 passed
- `uv run pytest --tb=short` -- 491 passed (no regressions)
- `uv run mypy inference_proxy/api/admin.py inference_proxy/models/admin.py` -- no issues
- Import verification: PowerAction, PowerActionRequest, PowerStateResponse, get_power_state, execute_power_action all importable

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED
