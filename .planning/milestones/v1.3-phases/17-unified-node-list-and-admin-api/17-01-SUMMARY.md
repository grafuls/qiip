---
phase: 17-unified-node-list-and-admin-api
plan: 01
subsystem: admin-api
tags: [unified-nodes, admin, quads-merge, dedup-guard]
dependency_graph:
  requires: [quads-poller, node-registry, circuit-breaker-registry, connection-tracker]
  provides: [unified-node-service, admin-unified-list, setup-dedup-guard, setup-quads-revalidation]
  affects: [admin-api, dependencies]
tech_stack:
  added: []
  patterns: [service-layer, di-provider, state-to-actions-mapping]
key_files:
  created:
    - inference_proxy/services/__init__.py
    - inference_proxy/services/unified_nodes.py
    - tests/services/__init__.py
    - tests/services/test_unified_nodes.py
  modified:
    - inference_proxy/models/admin.py
    - inference_proxy/api/admin.py
    - inference_proxy/config/dependencies.py
    - tests/api/test_admin.py
    - tests/conftest.py
decisions:
  - "State-to-actions mapping via module-level dict _STATE_ACTIONS for O/C compliance"
  - "pending_hosts as module-level set in api/admin.py per D-08"
  - "Existing status field kept for backward compat; new state field carries unified computed state"
metrics:
  duration: 400s
  completed: 2026-07-16T16:08:44Z
  tasks_completed: 2
  tasks_total: 2
  test_count: 43
  test_pass: 43
  total_tests_suite: 399
---

# Phase 17 Plan 01: Unified Node List and Admin API Summary

UnifiedNodeService merges QUADS GPU hosts with etcd-registered nodes by hostname, computing state and actions per node for the admin dashboard API.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | UnifiedNodeService, extended AdminNodeResponse, unit tests | `33c6b8d` (RED), `59a7779` (GREEN) | unified_nodes.py, admin.py (model), test_unified_nodes.py |
| 2 | Wire endpoints — unified GET, dedup guard, QUADS re-validation | `7902379` (RED), `4e7ca7d` (GREEN) | admin.py (api), dependencies.py, test_admin.py, conftest.py |

## What Was Built

- **UnifiedNodeService** (`inference_proxy/services/unified_nodes.py`): Merges QUADS `hosts` with etcd `registry.get_all()` by hostname. Etcd status wins (D-05). Nodes in etcd but absent from QUADS are excluded (D-03). Graceful degradation when poller is None.
- **State-to-actions mapping** (D-07): available->[setup], healthy->[teardown], unhealthy->[teardown,retry], provisioning->[cancel], draining->[force_teardown].
- **AdminNodeResponse extended** with `state`, `actions`, `gpu_vendor`, `gpu_model`, `gpu_count` fields. Existing `status` field kept for backward compatibility.
- **GET /admin/nodes** now uses `UnifiedNodeService` via DI instead of direct registry iteration.
- **POST /admin/nodes/setup** dedup guard: 409 when hostname already in `pending_hosts` set (D-08). Set cleared on task completion/failure via finally block.
- **POST /admin/nodes/setup** QUADS re-validation: calls `QUADSClient.get_available()` live, returns 503 on `QUADSConnectionError`, 400 if hostname not available (D-10/D-11).
- **get_unified_node_service** DI provider in `config/dependencies.py`.

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

All four commits follow RED/GREEN sequence:
1. `33c6b8d` test(17-01) - RED for Task 1 (14 failing tests)
2. `59a7779` feat(17-01) - GREEN for Task 1 (14 passing)
3. `7902379` test(17-01) - RED for Task 2 (new endpoint tests failing)
4. `4e7ca7d` feat(17-01) - GREEN for Task 2 (29 admin tests + 399 total passing)

## Verification

- `uv run pytest tests/services/test_unified_nodes.py -v` — 14/14 pass
- `uv run pytest tests/api/test_admin.py -v` — 29/29 pass
- `uv run pytest tests/ -x` — 399/399 pass, no regressions
- `grep -c "pending_hosts" inference_proxy/api/admin.py` — 4 occurrences
- `grep -c "get_unified_node_service" inference_proxy/config/dependencies.py` — 1
- `grep -c "UnifiedNodeService" inference_proxy/services/unified_nodes.py` — 1
