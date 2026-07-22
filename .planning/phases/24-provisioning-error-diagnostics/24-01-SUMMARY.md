---
phase: 24-provisioning-error-diagnostics
plan: 01
subsystem: provisioning-diagnostics
tags: [provisioning, error-handling, admin-api, node-status]
dependency_graph:
  requires: []
  provides: [NodeStatus.FAILED, AdminNodeResponse-error-fields, provisioner-step-tracking, unified-node-error-merge]
  affects: [inference_proxy/models/node.py, inference_proxy/models/admin.py, inference_proxy/provisioning/provisioner.py, inference_proxy/services/unified_nodes.py, inference_proxy/api/admin.py]
tech_stack:
  added: []
  patterns: [current_step-tracking, task_map-error-merge]
key_files:
  created: []
  modified:
    - inference_proxy/models/node.py
    - inference_proxy/models/admin.py
    - inference_proxy/provisioning/provisioner.py
    - inference_proxy/services/unified_nodes.py
    - inference_proxy/api/admin.py
    - tests/models/test_node.py
    - tests/models/test_admin.py
    - tests/provisioning/test_provisioner.py
    - tests/services/test_unified_nodes.py
decisions:
  - "Track current_step as local variable before each _update_state call in provision()"
  - "Write FAILED node to etcd in except block to avoid stuck PROVISIONING status"
  - "Build task_map from provisioning tasks in list_nodes endpoint to merge error data"
metrics:
  duration: 652s
  completed: 2026-07-22T10:34:53Z
  tasks_completed: 2
  tasks_total: 2
  test_count: 498
---

# Phase 24 Plan 01: Backend Error Capture and API Surface Summary

Fixed provisioner to capture actual step name on failure, added FAILED node status, and wired error data through the admin API.

## Task Summary

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Model changes, provisioner step tracking fix, and node FAILED update | 9b8f482 | node.py, admin.py, provisioner.py, test_node.py, test_admin.py, test_provisioner.py |
| 2 | Unified node service error merge and admin API wiring | fad34ce | unified_nodes.py, admin.py, test_unified_nodes.py |

## Changes Made

### Task 1: Model + Provisioner Fix
- Added `NodeStatus.FAILED = "failed"` enum member (D-01)
- Added `failed_step: str | None` and `error: str | None` to `AdminNodeResponse` (D-03, D-04)
- Replaced `failed_step=type(exc).__name__` with `failed_step=current_step` in provisioner except block (D-03)
- Added etcd node update to FAILED status in except block so nodes don't stay stuck as PROVISIONING (D-01)
- Updated test assertions to verify actual step name capture

### Task 2: Service + API Wiring
- Added `"failed": ["setup", "teardown"]` to `_STATE_ACTIONS` (D-02)
- Updated `get_unified_nodes` and `_from_etcd` to accept `task_map` parameter for error field population
- Updated `list_nodes` endpoint to build task_map from provisioning tasks and pass to service
- Added 3 tests: failed state actions, error fields from task_map, default None without task_map

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- Full test suite: 498 passed, 0 failed
- grep FAILED in node.py: 1 (present)
- grep failed_step in admin.py: 2 (field + TaskStatusResponse)
- grep current_step in provisioner.py: 7 (variable + assignments)
- grep "failed" in unified_nodes.py: 1 (STATE_ACTIONS entry)

## Self-Check: PASSED
