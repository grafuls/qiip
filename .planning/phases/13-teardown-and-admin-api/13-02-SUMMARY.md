---
phase: 13-teardown-and-admin-api
plan: 02
status: complete
started: 2026-07-07
completed: 2026-07-07
---

## Summary

Wired NodeProvisioner into the application lifespan, added Pydantic request/response models, and created three admin API endpoints: POST /admin/nodes/setup (202, background provision), GET /admin/provisioning/tasks (reads etcd), DELETE /admin/nodes/{id} (202 with force option, 404 for unknown).

## Self-Check: PASSED

- All 332 tests pass (7 new admin endpoint tests)
- Existing admin tests unchanged and passing

## Key Changes

### key-files.modified

- `inference_proxy/models/admin.py` — SetupRequest, SetupResponse, TeardownResponse, TaskStatusResponse
- `inference_proxy/config/dependencies.py` — get_provisioner DI provider
- `inference_proxy/main.py` — NodeProvisioner wired in lifespan
- `inference_proxy/api/admin.py` — 3 new endpoints
- `tests/api/test_admin.py` — 7 new tests
- `tests/conftest.py` — mock_provisioner fixture

## Deviations

None.

## Issues

None.
