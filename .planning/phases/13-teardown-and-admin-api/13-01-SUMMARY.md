---
phase: 13-teardown-and-admin-api
plan: 01
subsystem: provisioning
tags: [teardown, drain, podman, ssh, etcd, lifecycle]

requires:
  - phase: 12-provisioning-robustness
    provides: NodeProvisioner with provision(), _update_state(), SSHClient injection
provides:
  - NodeProvisioner.teardown() with graceful and force modes
  - ProvisioningStep enum extended with teardown steps
  - EtcdClient.delete() and parameterized get_prefix()
  - drain_timeout setting on ProvisioningSettings
  - _derive_container_name() for podman container name derivation
  - fire_background() for GC-safe asyncio task management
affects: [13-02-admin-api, dashboard-teardown]

tech-stack:
  added: []
  patterns: [drain-wait-loop, module-level-helper, optional-DI-params]

key-files:
  created: []
  modified:
    - inference_proxy/provisioning/provisioner.py
    - inference_proxy/provisioning/state.py
    - inference_proxy/config/settings.py
    - inference_proxy/discovery/etcd_client.py
    - tests/provisioning/test_provisioner.py
    - tests/discovery/test_etcd_client.py
    - tests/provisioning/test_state.py

key-decisions:
  - "_derive_container_name as module-level function (pure utility, no class context needed)"
  - "Optional DI params (registry, connection_tracker) default None to preserve backward compat"

patterns-established:
  - "Drain-wait loop: poll ConnectionTracker.get() with deadline from settings.drain_timeout"
  - "fire_background: store asyncio.Task in set with done_callback discard to prevent GC"

requirements-completed: [TEAR-01, TEAR-02]

duration: 7min
completed: 2026-07-07
---

# Phase 13 Plan 01: Teardown Lifecycle Summary

**NodeProvisioner.teardown() with graceful drain-wait and force modes, etcd deregistration, and SSH podman stop/rm**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-07T14:03:02Z
- **Completed:** 2026-07-07T14:09:44Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Extended ProvisioningStep enum with DRAINING, STOPPING_CONTAINER, DEREGISTERING, TEARDOWN_COMPLETE
- Added drain_timeout (30s default) to ProvisioningSettings
- Added EtcdClient.delete() method and parameterized get_prefix() with optional custom prefix
- Implemented NodeProvisioner.teardown() with graceful drain-wait and force modes
- 12 new teardown tests across 6 test classes, all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend types, settings, and EtcdClient for teardown** - `d6b253e` (feat)
2. **Task 2: Implement NodeProvisioner.teardown() with tests** - `24ab0fc` (feat)

## Files Created/Modified
- `inference_proxy/provisioning/state.py` - 4 new teardown enum members
- `inference_proxy/config/settings.py` - drain_timeout: int = 30
- `inference_proxy/discovery/etcd_client.py` - delete() method, parameterized get_prefix()
- `inference_proxy/provisioning/provisioner.py` - teardown(), _drain_wait(), _derive_container_name(), fire_background(), extended __init__
- `tests/provisioning/test_provisioner.py` - 12 new teardown tests
- `tests/discovery/test_etcd_client.py` - delete and custom prefix tests
- `tests/provisioning/test_state.py` - Updated enum member count (13 -> 17) and values

## Decisions Made
- _derive_container_name as module-level function: pure utility deriving container name from model string, no class context needed
- Optional DI params (registry, connection_tracker) default to None: existing tests and callers unaffected; teardown logs warning and uses hostname fallback when registry is None

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated hardcoded enum member count in test_state.py**
- **Found during:** Task 1 (after extending ProvisioningStep)
- **Issue:** test_member_count asserted len(ProvisioningStep) == 13, now 17
- **Fix:** Updated assertion to 17 and added 4 new members to expected values dict
- **Files modified:** tests/provisioning/test_state.py
- **Verification:** uv run pytest tests/ -x passed (325 tests)
- **Committed in:** d6b253e (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary update to existing test that hardcoded enum size. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- teardown() ready to be exposed via admin API endpoints (Plan 02)
- fire_background() ready for asyncio.create_task wrapping in admin route handlers
- get_prefix(prefix) ready for reading /provisioning/* keys in task listing endpoint

## Self-Check: PASSED

- All 7 files verified present on disk
- Both commit hashes (d6b253e, 24ab0fc) verified in git log
- No stubs or TODOs found in modified files
- 325 tests pass (12 new)

---
*Phase: 13-teardown-and-admin-api*
*Completed: 2026-07-07*
