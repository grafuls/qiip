---
phase: 23-auto-power-on-in-provisioner
verified: 2026-07-22T08:48:00Z
status: passed
score: 10/10 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 23: Auto-Power-On in Provisioner Verification Report

**Phase Goal:** Provisioning works even when target servers are powered off
**Verified:** 2026-07-22T08:48:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                           | Status     | Evidence                                                                                                                                    |
| --- | ----------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Setup operation automatically powers on a node that is off before starting SSH provisioning    | ✓ VERIFIED | `_power_on_if_needed()` method exists at line 128, calls `power_action(hostname, "On")` at line 140, invoked in provision() at line 238    |
| 2   | Dashboard shows POWERING_ON step while the server boots                                        | ✓ VERIFIED | `ProvisioningStep.POWERING_ON` enum member exists at line 23, state written to etcd at line 138 via `_update_state()`                      |
| 3   | Provisioning waits for SSH availability after power-on before proceeding to preflight          | ✓ VERIFIED | `_wait_for_ssh()` method exists at line 147, TCP probe loop on port 22 with deadline pattern, called from `_power_on_if_needed()` line 145 |
| 4   | D-01: Provisioning skips power-on when RedfishClient is None — backward-compatible             | ✓ VERIFIED | Line 134-136: `if self._redfish_client is None: logger.info("redfish_not_configured", ...); return` — no state write when None            |
| 5   | D-02: Logs skip at INFO: redfish_not_configured, skipping power check                          | ✓ VERIFIED | Line 135: `logger.info("redfish_not_configured", msg="skipping power check")`                                                              |
| 6   | D-03: Dedicated SSH wait loop (TCP probe retries) separate from preflight                      | ✓ VERIFIED | `_wait_for_ssh()` is a separate method (line 147), uses `asyncio.open_connection(hostname, 22)` at line 157-159                            |
| 7   | D-04: Single POWERING_ON dashboard step covers Redfish action + SSH wait                       | ✓ VERIFIED | State written once at line 138 before power_action, method includes both power action and SSH wait in same call                            |
| 8   | D-05: boot_wait_timeout defaults to 300s, configurable via ProvisioningSettings                | ✓ VERIFIED | `settings.py` line 118: `boot_wait_timeout: int = 300`; line 119: `boot_wait_interval: int = 10`                                           |
| 9   | D-06: Best-effort power-on — RedfishError caught and logged, provisioning continues            | ✓ VERIFIED | Lines 142-143: `except RedfishError as exc: logger.warning("power_on_failed", ...)` — no re-raise, continues to `_wait_for_ssh()`         |
| 10  | D-07: POWERING_ON state written before power action, visible on failure path                   | ✓ VERIFIED | Line 138 writes state before try block at line 139; test_powering_on_state_written_before_action validates ordering                        |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact                                        | Expected                                                 | Status     | Details                                                                                            |
| ----------------------------------------------- | -------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------- |
| `inference_proxy/provisioning/state.py`         | POWERING_ON enum member                                  | ✓ VERIFIED | Line 23: `POWERING_ON = "powering_on"` positioned after PENDING                                    |
| `inference_proxy/config/settings.py`            | boot_wait_timeout and boot_wait_interval settings        | ✓ VERIFIED | Lines 118-119: `boot_wait_timeout: int = 300`, `boot_wait_interval: int = 10`                      |
| `inference_proxy/provisioning/provisioner.py`   | _power_on_if_needed and _wait_for_ssh methods            | ✓ VERIFIED | `_power_on_if_needed()` at line 128, `_wait_for_ssh()` at line 147                                |
| `inference_proxy/main.py`                       | redfish_client passed to NodeProvisioner constructor     | ✓ VERIFIED | Line 199: `redfish_client=app.state.redfish_client` kwarg in NodeProvisioner constructor          |
| `tests/provisioning/test_provisioner.py`        | TestPowerOnIfNeeded and TestWaitForSsh test classes      | ✓ VERIFIED | `TestPowerOnIfNeeded` at line 918 (4 tests), `TestWaitForSsh` at line 1010 (3 tests)              |

### Key Link Verification

| From                                      | To                                    | Via                                              | Status     | Details                                                                 |
| ----------------------------------------- | ------------------------------------- | ------------------------------------------------ | ---------- | ----------------------------------------------------------------------- |
| `inference_proxy/provisioning/provisioner.py` | `inference_proxy/redfish/client.py`   | RedfishClient.power_action call in _power_on_if_needed | ✓ WIRED    | Line 140: `state = await self._redfish_client.power_action(hostname, "On")` |
| `inference_proxy/main.py`                 | `inference_proxy/provisioning/provisioner.py` | redfish_client kwarg in NodeProvisioner constructor | ✓ WIRED    | Line 199: `redfish_client=app.state.redfish_client`                    |
| `inference_proxy/provisioning/provisioner.py` | `inference_proxy/provisioning/state.py`     | ProvisioningStep.POWERING_ON used in _update_state | ✓ WIRED    | Line 138: `await self._update_state(hostname, ProvisioningStep.POWERING_ON)` |

### Data-Flow Trace (Level 4)

| Artifact                          | Data Variable    | Source                                       | Produces Real Data | Status     |
| --------------------------------- | ---------------- | -------------------------------------------- | ------------------ | ---------- |
| `_power_on_if_needed()`           | `state`          | `RedfishClient.power_action(hostname, "On")` | Yes                | ✓ FLOWING  |
| `_wait_for_ssh()`                 | `writer`         | `asyncio.open_connection(hostname, 22)`      | Yes                | ✓ FLOWING  |
| `NodeProvisioner.__init__()`      | `redfish_client` | `app.state.redfish_client` (from main.py)    | Yes                | ✓ FLOWING  |

### Behavioral Spot-Checks

| Behavior                                    | Command                                                                                                  | Result | Status    |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------ | --------- |
| POWERING_ON enum member exists and ordered  | `uv run python -c "from inference_proxy.provisioning.state import ProvisioningStep; ..."`               | PASS   | ✓ PASS    |
| boot_wait_timeout and interval defaults set | `uv run python -c "from inference_proxy.config.settings import ProvisioningSettings; s = ProvisioningSettings(); assert s.boot_wait_timeout == 300; assert s.boot_wait_interval == 10"` | PASS   | ✓ PASS    |
| NodeProvisioner accepts redfish_client kwarg| `uv run python -c "import inspect; from inference_proxy.provisioning.provisioner import NodeProvisioner; sig = inspect.signature(NodeProvisioner.__init__); assert 'redfish_client' in sig.parameters"` | PASS   | ✓ PASS    |
| TestPowerOnIfNeeded tests pass              | `uv run pytest tests/provisioning/test_provisioner.py::TestPowerOnIfNeeded -x`                          | 4 passed | ✓ PASS    |
| TestWaitForSsh tests pass                   | `uv run pytest tests/provisioning/test_provisioner.py::TestWaitForSsh -x`                               | 3 passed | ✓ PASS    |
| Full provisioner test suite                 | `uv run pytest tests/provisioning/test_provisioner.py -x`                                               | 42 passed | ✓ PASS    |
| Full test suite (no regressions)            | `uv run pytest tests/ -x`                                                                                | 498 passed | ✓ PASS    |

### Probe Execution

No probes defined for this phase.

### Requirements Coverage

| Requirement | Source Plan | Description                                                                      | Status     | Evidence                                                                                                                                                                                                                   |
| ----------- | ----------- | -------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PWR-05      | 23-01-PLAN  | Provisioning automatically powers on a node before SSH setup if the node is off | ✓ SATISFIED | `_power_on_if_needed()` method inserts power-on + SSH wait between PENDING and PREFLIGHT steps (line 238 in provision()), POWERING_ON state visible in etcd, tests verify all behaviors, full test suite passes with 0 regressions |

### Anti-Patterns Found

No anti-patterns or debt markers found.

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | - | - | - | - |

**Debt marker check:** No `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, or `PLACEHOLDER` markers in modified files.

### Human Verification Required

None. All behaviors are programmatically verifiable through the test suite.

### Summary

**All 10 must-haves VERIFIED.** Phase 23 successfully integrates automatic Redfish power-on into the provisioning sequence:

**Key achievements:**
- POWERING_ON enum member added between PENDING and PREFLIGHT, ensuring correct dashboard step ordering
- Backward-compatible: skips power-on when RedfishClient is None (D-01, D-02)
- Best-effort power action: catches RedfishError and continues (D-06)
- Dedicated SSH wait loop with deadline pattern (D-03, D-05)
- Single POWERING_ON dashboard step covers entire boot sequence (D-04)
- State written before power action, visible on failure path (D-07)
- Boot wait timeout configurable via ProvisioningSettings (300s default)
- Redfish client wired into provisioner via constructor injection in main.py
- Comprehensive test coverage: 7 new tests (4 power-on, 3 SSH wait)
- Zero test regressions: 498 tests pass

**Requirements satisfied:** PWR-05 fully implemented and tested.

**Commits verified:**
- `3ae95c3` — feat(23-01): add auto power-on to provisioning sequence (4 files, 83+ lines)
- `108f36f` — test(23-01): add power-on and SSH wait tests (2 files, 163+ lines)

**No gaps.** Ready to proceed.

---

_Verified: 2026-07-22T08:48:00Z_
_Verifier: Claude (gsd-verifier)_
