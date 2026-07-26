---
phase: 28-model-selection
reviewed: 2026-07-26T18:30:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - inference_proxy/models/admin.py
  - inference_proxy/provisioning/provisioner.py
  - inference_proxy/api/admin.py
  - tests/models/test_admin.py
  - tests/provisioning/test_provisioner.py
  - tests/api/test_admin.py
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: issues_found
---

# Phase 28: Code Review Report

**Reviewed:** 2026-07-26T18:30:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the model selection feature that adds an optional `model` parameter to the setup/provisioning flow. The core integration is sound: `SetupRequest` accepts `model`, the API endpoint passes it through to the provisioner, and `_run_start_vllm` injects it as a `VLLM_MODEL` env var with proper `shlex.quote()` escaping. One correctness bug (missing input validation allows whitespace-only model names to reach remote shell commands), plus code quality and test robustness issues.

## Critical Issues

### CR-01: Whitespace-only model name passes validation and produces broken shell command

**File:** `inference_proxy/models/admin.py:67`
**Issue:** The `SetupRequest.model` field accepts whitespace-only strings (e.g., `"   "`) because it only validates `max_length=256` with no content check. A whitespace-only string is truthy in Python, so `_run_start_vllm` will set `VLLM_MODEL='   '` on the remote host, causing `vllm serve '   '` to fail with a confusing model-not-found error. The provisioning will fail at the `_run_start_vllm` step after setup.sh has already run (wasting minutes of work), producing an unhelpful error message. More critically, the empty-but-present env var overrides the auto-detected model in `start-vllm.sh` line 102 (`MODEL="${VLLM_MODEL:-$MODEL}"`), silently replacing a valid selection with whitespace.
**Fix:**
```python
model: str | None = Field(default=None, max_length=256)

@field_validator("model")
@classmethod
def validate_model(cls, v: str | None) -> str | None:
    if v is not None:
        v = v.strip()
        if not v:
            return None
    return v
```

## Warnings

### WR-01: Tests use deprecated `asyncio.get_event_loop().run_until_complete()`

**File:** `tests/api/test_admin.py:296` and `tests/api/test_admin.py:311`
**Issue:** `asyncio.get_event_loop()` is deprecated in Python 3.12+ when no event loop is running (the target runtime per CLAUDE.md). These synchronous tests call it to manually run a coroutine extracted from a mock. In Python 3.14+ this will raise `RuntimeError`. This makes the tests fragile on the declared target runtime.
**Fix:** Use `asyncio.run()` instead, or restructure as async tests with `@pytest.mark.asyncio`:
```python
import asyncio
asyncio.run(coro)
```

### WR-02: `_run_setup` logs FAIL markers at error level but does not halt setup

**File:** `inference_proxy/provisioning/provisioner.py:343-345`
**Issue:** When a `[STEP:stepname:FAIL]` marker appears in setup.sh stdout, `_run_setup` logs it as an error and continues reading output from the stream. The method relies on `SSHClient.run_streaming` raising `RemoteCommandError` from a non-zero exit code to actually fail the provisioning. If `setup.sh` emits a FAIL marker but still exits 0 (which is possible with `set +e` in a subshell or a trapped error), provisioning continues with a silently broken node. This is a correctness concern because the FAIL marker is the authoritative signal from the script.
**Fix:** Consider raising `ProvisioningError` when a FAIL marker is encountered, or at minimum, track FAIL markers and check them after the stream is consumed:
```python
failed_steps: list[str] = []
# ... inside the loop:
if status == "FAIL":
    failed_steps.append(step_name)
# ... after the loop:
if failed_steps:
    raise ProvisioningError(
        f"setup.sh reported failures: {', '.join(failed_steps)}"
    )
```

### WR-03: `import re` separated from other stdlib imports by blank line

**File:** `inference_proxy/models/admin.py:12`
**Issue:** `import re` is separated by a blank line from the `datetime`/`enum` imports (lines 9-10), creating a visual split in the stdlib import group. Ruff isort rules expect all stdlib imports in a single contiguous block. This will trigger `I001` (import block not sorted) when ruff is configured with isort rules.
**Fix:** Move `import re` to join the other stdlib imports:
```python
from datetime import datetime
from enum import Enum
import re
```
Or remove the blank line between lines 10 and 11.

## Info

### IN-01: Inconsistent hostname validation across admin endpoints

**File:** `inference_proxy/api/admin.py:216` vs `inference_proxy/api/admin.py:253-254`
**Issue:** `teardown_node` (line 216) uses `canonical_hostname()` only, while `get_power_state` (line 253), `execute_power_action` (line 270), `stream_provisioning_logs` (line 192), and `get_recommendations` (line 289) use `_validated_hostname()` which includes format validation. The teardown endpoint is safe because it checks registry membership (line 217), but the inconsistency creates confusion about which endpoints validate input and which don't.
**Fix:** Apply `_validated_hostname()` consistently to all hostname path parameters:
```python
node_id = _validated_hostname(node_id)
```

---

_Reviewed: 2026-07-26T18:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
