---
phase: 23-auto-power-on-in-provisioner
plan: 01
subsystem: provisioning
tags: [redfish, power-on, ssh-wait, provisioner, state-machine]
dependency_graph:
  requires: [phase-21-redfish-client]
  provides: [auto-power-on-provisioning]
  affects: [provisioning-sequence, dashboard-steps]
tech_stack:
  added: []
  patterns: [best-effort-catch-continue, deadline-retry-loop, optional-dependency-injection]
key_files:
  created: []
  modified:
    - inference_proxy/provisioning/state.py
    - inference_proxy/config/settings.py
    - inference_proxy/provisioning/provisioner.py
    - inference_proxy/main.py
    - tests/provisioning/test_provisioner.py
    - tests/provisioning/test_state.py
decisions:
  - "Moved redfish client init before provisioner construction in main.py lifespan (redfish_client needed at construction time)"
metrics:
  duration: "352s"
  completed: "2026-07-22"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 6
  tests_added: 7
  tests_total: 498
---

# Phase 23 Plan 01: Auto Power-On in Provisioner Summary

Best-effort Redfish power-on inserted into provisioning sequence with POWERING_ON dashboard step, SSH wait loop, and backward-compatible skip when Redfish unconfigured.

## What Was Done

### Task 1: POWERING_ON step, boot settings, provisioner methods, main.py wiring (3ae95c3)

- Added `POWERING_ON = "powering_on"` to `ProvisioningStep` enum between PENDING and PREFLIGHT
- Added `boot_wait_timeout: int = 300` and `boot_wait_interval: int = 10` to `ProvisioningSettings`
- Added `redfish_client: RedfishClient | None = None` parameter to `NodeProvisioner.__init__()`
- Added `_power_on_if_needed()`: checks None guard, writes POWERING_ON state, calls `power_action("On")` best-effort, then `_wait_for_ssh()`
- Added `_wait_for_ssh()`: deadline-based TCP probe loop on port 22, mirrors `_poll_health()` pattern
- Wired `_power_on_if_needed()` into `provision()` between PENDING and PREFLIGHT state writes
- Passed `app.state.redfish_client` to NodeProvisioner in main.py lifespan
- Reordered main.py lifespan: redfish client init moved before provisioner construction (provisioner needs it at construction time)

### Task 2: Tests for power-on and SSH wait logic (108f36f)

- `TestPowerOnIfNeeded`: 4 tests covering None skip, power_action call, RedfishError catch, state ordering
- `TestWaitForSsh`: 3 tests covering first success, retry until success, timeout without raise
- Updated `_make_provisioner` helper to accept `redfish_client` parameter
- Fixed `test_member_count` in `test_state.py` (18 -> 19 for new POWERING_ON member)
- All 498 tests pass, 0 regressions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reordered main.py lifespan initialization**
- **Found during:** Task 1
- **Issue:** Plan stated `app.state.redfish_client` is set before provisioner construction, but in actual code the provisioner was constructed at line 164 while redfish setup happened at line 203. Passing `redfish_client` would have been `None` always.
- **Fix:** Moved redfish client init block before provisioner construction, and provisioner before QUADS block (ScheduleEnforcer depends on provisioner).
- **Files modified:** inference_proxy/main.py
- **Commit:** 3ae95c3

**2. [Rule 1 - Bug] Fixed test_member_count assertion**
- **Found during:** Task 2
- **Issue:** `test_state.py::test_member_count` asserted 18 enum members, but POWERING_ON addition made it 19.
- **Fix:** Updated assertion from 18 to 19.
- **Files modified:** tests/provisioning/test_state.py
- **Commit:** 108f36f

## Verification Results

| Check | Result |
|-------|--------|
| POWERING_ON enum member exists and ordered after PENDING | PASS |
| boot_wait_timeout=300, boot_wait_interval=10 defaults | PASS |
| NodeProvisioner.__init__ accepts redfish_client kwarg | PASS |
| main.py imports cleanly | PASS |
| Provisioner test suite (42 tests) | PASS |
| Full test suite (498 tests) | PASS |
