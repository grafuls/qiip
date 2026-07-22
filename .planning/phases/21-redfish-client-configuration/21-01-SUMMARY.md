---
phase: 21-redfish-client-configuration
plan: 01
subsystem: redfish
tags: [redfish, bmc, power-management, configuration, client]
dependency_graph:
  requires: []
  provides: [RedfishClient, RedfishError, RedfishSettings, extract_error_message, REDFISH_ERROR_MAP]
  affects: [inference_proxy/config/settings.py]
tech_stack:
  added: []
  patterns: [constructor-injection, check-before-act, post-action-polling, error-mapping]
key_files:
  created:
    - inference_proxy/redfish/__init__.py
    - inference_proxy/redfish/errors.py
    - inference_proxy/redfish/client.py
    - tests/redfish/__init__.py
    - tests/redfish/test_client.py
  modified:
    - inference_proxy/config/settings.py
    - tests/config/test_settings.py
decisions:
  - RedfishClient mirrors QUADSClient pattern with constructor-injected httpx.AsyncClient
  - REDFISH_ERROR_MAP uses static dict with 8 entries covering common Base registry MessageIds
  - check-before-act skips POST when already in desired state (D-03)
  - post-action polling uses asyncio.sleep loop with deadline (D-04)
metrics:
  duration: 246s
  completed: 2026-07-22T04:54:46Z
  tasks_completed: 2
  tasks_total: 2
  tests_added: 27
  files_created: 5
  files_modified: 2
---

# Phase 21 Plan 01: RedfishSettings, RedfishError, and RedfishClient Summary

RedfishClient with constructor-injected httpx.AsyncClient for BMC power state queries and power actions, check-before-act idempotency (D-03), post-action polling (D-04), and human-readable error mapping via REDFISH_ERROR_MAP (DIAG-03). SecretStr masks bmc_password.

## Task Results

| Task | Name | Commit(s) | Status |
|------|------|-----------|--------|
| 1 | RedfishSettings, RedfishError, and error mapping | 8c82e2b (RED), bcb244e (GREEN) | Done |
| 2 | RedfishClient with power state, power actions, and tests | 563c03d (RED), f36690f (GREEN) | Done |

## Verification Results

```
uv run pytest tests/redfish/ tests/config/test_settings.py -x -q
54 passed in 0.31s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TestResolveBmcHost using deprecated asyncio.get_event_loop()**
- **Found during:** Task 2
- **Issue:** Sync test tried to manually create an event loop via `asyncio.get_event_loop().run_until_complete()`, which raises RuntimeError in Python 3.12
- **Fix:** Changed to `async def` test method, consistent with all other tests (pytest-asyncio auto mode handles it)
- **Files modified:** tests/redfish/test_client.py
- **Commit:** f36690f

**2. [Rule 1 - Bug] Fixed TestPowerActionTimeout registering too many mock responses**
- **Found during:** Task 2
- **Issue:** Registered 20 poll responses but timeout fires before consuming them all; pytest-httpx asserts all registered responses are consumed
- **Fix:** Used `@pytest.mark.httpx_mock(can_send_already_matched_responses=True)` and let the first GET response be re-sent for polling
- **Files modified:** tests/redfish/test_client.py
- **Commit:** f36690f

## TDD Gate Compliance

Task 1:
- RED: 8c82e2b (test commit) -- tests fail with ImportError: cannot import name 'RedfishSettings'
- GREEN: bcb244e (feat commit) -- 41 settings tests pass

Task 2:
- RED: 563c03d (test commit) -- tests fail with ModuleNotFoundError: No module named 'inference_proxy.redfish.client'
- GREEN: f36690f (feat commit) -- 13 client tests pass, 54 total pass

## Self-Check: PASSED

All 5 created files exist. All 2 modified files exist. All 4 commit hashes verified in git log.
