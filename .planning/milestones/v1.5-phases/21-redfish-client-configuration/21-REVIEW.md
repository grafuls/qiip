---
phase: 21-redfish-client-configuration
reviewed: 2026-07-22T12:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - inference_proxy/config/dependencies.py
  - inference_proxy/config/settings.py
  - inference_proxy/main.py
  - inference_proxy/redfish/client.py
  - inference_proxy/redfish/errors.py
  - inference_proxy/redfish/__init__.py
  - tests/config/test_settings.py
  - tests/conftest.py
  - tests/redfish/__init__.py
  - tests/redfish/test_client.py
findings:
  critical: 3
  warning: 3
  info: 0
  total: 6
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-07-22T12:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

The Redfish client implementation follows the established QUADSClient pattern well: constructor-injected httpx client, typed errors, and clean async methods. However, the check-before-act logic has a critical logic bug that silently prevents restart actions from executing. A second blocker exists in the startup path where a missing password causes an AttributeError crash. A third issue leaves unhandled KeyErrors leaking from malformed BMC responses.

## Critical Issues

### CR-01: GracefulRestart and ForceRestart never execute on running systems

**File:** `inference_proxy/redfish/client.py:84-88`
**Issue:** The check-before-act guard compares current power state to the target state and skips the action if they match. For `GracefulRestart` and `ForceRestart`, the target state is `"On"` (line 27-28). A running system is already `"On"`, so `current == target` is always `True` and the restart is silently skipped. The restart POST is never issued. This renders both restart actions completely non-functional on running systems -- which is the only scenario where a restart makes sense.

Trace:
1. `power_action("host", "GracefulRestart")` enters
2. `target = _ACTION_TARGET_STATE["GracefulRestart"]` -> `"On"`
3. `current = await self.get_power_state("host")` -> `"On"` (system is running)
4. `if current == target:` -> `"On" == "On"` -> `True`
5. Returns immediately with `"On"` -- no restart issued

**Fix:** Restart actions should bypass the check-before-act guard. Only power-on and power-off benefit from idempotency checking:
```python
_SKIP_CHECK_ACTIONS = {"GracefulRestart", "ForceRestart"}

async def power_action(self, hostname: str, action: str, *, timeout: float | None = None) -> str:
    if action not in _ACTION_TARGET_STATE:
        raise RedfishError(f"Unsupported action: {action}")
    target = _ACTION_TARGET_STATE[action]
    if action not in _SKIP_CHECK_ACTIONS:
        current = await self.get_power_state(hostname)
        if current == target:
            logger.info("redfish_power_action_skipped", hostname=hostname, action=action, state=current)
            return current
    await self._post_reset(hostname, action)
    return await self._poll_power_state(hostname, target, timeout or self._poll_timeout)
```

### CR-02: AttributeError crash when bmc_username is set without bmc_password

**File:** `inference_proxy/main.py:207`
**Issue:** The startup guard checks `bmc_username is not None` (line 203) but does not verify `bmc_password` is also set. When an operator sets `INFERENCE_PROXY_REDFISH__BMC_USERNAME=admin` without setting `INFERENCE_PROXY_REDFISH__BMC_PASSWORD`, line 207 calls `.get_secret_value()` on `None`, raising `AttributeError: 'NoneType' object has no attribute 'get_secret_value'`. The `# type: ignore[union-attr]` comment confirms the type checker flagged this, but the warning was silenced instead of fixed.

**Fix:** Add a `model_validator` to `RedfishSettings` so invalid configuration is caught at settings load time rather than at startup:
```python
from pydantic import model_validator

class RedfishSettings(BaseModel):
    # ... existing fields ...

    @model_validator(mode="after")
    def password_required_when_username_set(self) -> RedfishSettings:
        if self.bmc_username is not None and self.bmc_password is None:
            raise ValueError("bmc_password is required when bmc_username is set")
        return self
```
Then remove the `# type: ignore[union-attr]` from `main.py:207`.

### CR-03: Unhandled KeyError when BMC response lacks PowerState field

**File:** `inference_proxy/redfish/client.py:75`
**Issue:** `resp.json()["PowerState"]` raises a raw `KeyError` if the BMC returns valid JSON without a `PowerState` field (e.g., wrong system ID resolving to a non-ComputerSystem resource, or a firmware version returning a different schema). Callers expect `RedfishError` for all BMC failures. A bare `KeyError` propagating up will bypass the structured error handling.

**Fix:**
```python
data = resp.json()
try:
    return data["PowerState"]
except KeyError:
    raise RedfishError(f"BMC response missing PowerState field: {str(data)[:200]}")
```

## Warnings

### WR-01: Deprecated asyncio.get_event_loop() -- inconsistent with codebase

**File:** `inference_proxy/redfish/client.py:107`
**Issue:** `asyncio.get_event_loop()` is deprecated since Python 3.10 and emits `DeprecationWarning` in newer Python versions. The rest of the codebase (`provisioner.py:285,298,331,335`) correctly uses `asyncio.get_running_loop()`. This is an inconsistency within the same project and will break if Python removes the deprecated API.

**Fix:**
```python
loop = asyncio.get_running_loop()
```

### WR-02: str.format() in _resolve_bmc_host vulnerable to format string injection

**File:** `inference_proxy/redfish/client.py:59`
**Issue:** `self._bmc_host_template.format(hostname=hostname)` will raise `KeyError` or `ValueError` if `hostname` contains `{` or `}` characters. Hostnames originate from the node registry (loaded from etcd), which is an external data source. A malformed hostname like `server{0}` would cause an unhandled exception. While unlikely with real hostnames, this is a trust boundary.

**Fix:** Use string replacement instead of format:
```python
def _resolve_bmc_host(self, hostname: str) -> str:
    return self._bmc_host_template.replace("{hostname}", hostname)
```

### WR-03: No validation that bmc_host_template contains {hostname} placeholder

**File:** `inference_proxy/config/settings.py:146`
**Issue:** If an operator sets `INFERENCE_PROXY_REDFISH__BMC_HOST_TEMPLATE` to a value without `{hostname}` (e.g., `"bmc-static.lab"`), all BMC operations resolve to the same host regardless of which node is targeted. This is a silent misconfiguration that could send power-off commands to the wrong machine.

**Fix:** Add a field validator:
```python
@field_validator("bmc_host_template")
@classmethod
def template_must_contain_hostname(cls, v: str) -> str:
    if "{hostname}" not in v:
        raise ValueError("bmc_host_template must contain '{hostname}' placeholder")
    return v
```

---

_Reviewed: 2026-07-22T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
