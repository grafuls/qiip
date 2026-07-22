---
phase: 21-redfish-client-configuration
plan: 02
subsystem: redfish
tags: [redfish, bmc, lifespan, dependency-injection, configuration]
dependency_graph:
  requires: [RedfishClient, RedfishSettings]
  provides: [get_redfish_client]
  affects: [inference_proxy/main.py, inference_proxy/config/dependencies.py, tests/conftest.py]
tech_stack:
  added: []
  patterns: [constructor-injection, conditional-lifespan-block, DI-provider]
key_files:
  created: []
  modified:
    - inference_proxy/config/dependencies.py
    - inference_proxy/main.py
    - tests/conftest.py
decisions:
  - Redfish lifespan block mirrors QUADS conditional pattern (enabled when bmc_username set)
  - Dedicated httpx.AsyncClient for Redfish (not shared with proxy or QUADS clients)
metrics:
  duration: 268s
  completed: 2026-07-22T05:31:31Z
  tasks_completed: 1
  tasks_total: 1
  tests_added: 0
  files_created: 0
  files_modified: 3
---

# Phase 21 Plan 02: Wire RedfishClient into Lifespan and DI Summary

Dedicated httpx.AsyncClient with BasicAuth and verify=False created in lifespan when bmc_username is configured, exposed via get_redfish_client DI provider, cleaned up on shutdown. Test conftest defaults redfish_client to None.

## Task Results

| Task | Name | Commit(s) | Status |
|------|------|-----------|--------|
| 1 | Wire Redfish client into lifespan, DI, and test fixtures | eb883b7 | Done |

## Verification Results

```
uv run pytest --tb=short -q
479 passed in 66.52s
```

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

All 3 modified files exist. Commit hash eb883b7 verified in git log.
