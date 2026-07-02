---
phase: 11-ssh-provisioning
reviewed: 2026-07-02T00:15:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - inference_proxy/config/settings.py
  - inference_proxy/discovery/etcd_client.py
  - inference_proxy/provisioning/__init__.py
  - inference_proxy/provisioning/provisioner.py
  - inference_proxy/provisioning/ssh_client.py
  - tests/config/test_settings.py
  - tests/discovery/test_etcd_client.py
  - tests/provisioning/__init__.py
  - tests/provisioning/test_provisioner.py
  - tests/provisioning/test_ssh_client.py
findings:
  critical: 3
  warning: 3
  info: 1
  total: 7
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-07-02T00:15:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

The SSH provisioning phase adds an `SSHClient` wrapper (asyncssh), a `NodeProvisioner` orchestrator, and corresponding settings/tests. The structure is clean and follows project conventions (DIP, pydantic-settings nesting, structlog). However, there are three bugs that will cause runtime failures or incorrect behavior, plus three robustness gaps that degrade reliability.

## Critical Issues

### CR-01: SSH key path with tilde is never expanded -- FileNotFoundError at runtime

**File:** `inference_proxy/config/settings.py:101` and `inference_proxy/provisioning/ssh_client.py:74`
**Issue:** `SSHSettings.key_path` defaults to `Path("~/.ssh/id_rsa")`. `Path()` does NOT expand `~` -- the string stays literal `~/.ssh/id_rsa`. When passed to asyncssh via `str(self._key_path)` at ssh_client.py:74, asyncssh only calls `expanduser()` on its *own* default key paths, not on user-supplied `client_keys` strings. This means the default configuration will fail with a `FileNotFoundError` (or `KeyImportError`) every time because no file exists at the literal path `~/.ssh/id_rsa`.
**Fix:**
Expand the path in `SSHClient.__init__` where it's consumed:
```python
# ssh_client.py, line 54
self._key_path = settings.key_path.expanduser()
```
Or add a Pydantic validator on `SSHSettings.key_path` to expand on construction:
```python
@field_validator("key_path")
@classmethod
def expand_home(cls, v: Path) -> Path:
    return v.expanduser()
```

### CR-02: `asyncio.get_event_loop()` is deprecated in async context -- DeprecationWarning now, removal in future Python

**File:** `inference_proxy/provisioning/provisioner.py:112` and `inference_proxy/provisioning/provisioner.py:125`
**Issue:** `asyncio.get_event_loop()` is called from within an `async def` method. Since Python 3.10+, calling `get_event_loop()` when there is a running loop emits a `DeprecationWarning`, and its behavior is documented as unreliable in async contexts. The project targets Python 3.12+ per CLAUDE.md. The correct API is `asyncio.get_running_loop()`, which is guaranteed to return the currently running loop from an async context.
**Fix:**
```python
# provisioner.py:112
deadline = asyncio.get_running_loop().time() + self._settings.health_poll_timeout

# provisioner.py:125
if asyncio.get_running_loop().time() >= deadline:
```

### CR-03: Unhandled httpx exceptions in `_poll_health` crash provisioning without proper error wrapping

**File:** `inference_proxy/provisioning/provisioner.py:122-123`
**Issue:** Only `httpx.ConnectError` and `httpx.TimeoutException` are caught. During health polling of a starting server, responses like partial reads, connection resets, or protocol errors raise `httpx.ReadError`, `httpx.RemoteProtocolError`, `httpx.CloseError`, etc. -- none of which are subclasses of the two caught types. These exceptions propagate up to `provision()` (line 67) which only catches `RemoteCommandError` and `SSHConnectionError`, so they escape `ProvisioningError` wrapping entirely and surface as raw httpx exceptions to the caller.
**Fix:**
Catch the common base class `httpx.HTTPError` instead, or at minimum `httpx.TransportError` which covers all network/protocol errors during the request:
```python
except httpx.TransportError as exc:
    logger.debug("health_poll_retry", hostname=hostname, error=str(exc))
```

## Warnings

### WR-01: `_run_setup` silently continues after FAIL step markers

**File:** `inference_proxy/provisioning/provisioner.py:82-84`
**Issue:** When setup.sh emits `[STEP:X:FAIL]`, the code logs `step_failed` at error level but continues execution. If setup.sh exits 0 despite a step failure (which is plausible for scripts that continue past non-critical steps), provisioning proceeds to `_run_start_vllm` on a host with incomplete setup. The test at test_provisioner.py:111-113 documents this as intentional ("should not raise on FAIL markers") but the rationale ("RemoteCommandError is what signals actual failure") assumes setup.sh always exits non-zero on any FAIL -- an assumption not enforced by this code.
**Fix:**
Either raise `ProvisioningError` on FAIL markers, or document the contract explicitly. If setup.sh is guaranteed to exit non-zero on FAIL, add a comment. If not:
```python
if status == "FAIL":
    raise ProvisioningError(
        f"Setup step '{step_name}' failed on {hostname}"
    )
```

### WR-02: Dead variable `last_step` in `_run_setup`

**File:** `inference_proxy/provisioning/provisioner.py:73,81`
**Issue:** The variable `last_step` is assigned on line 73 and updated on line 81, but is never read. This is dead code that suggests either incomplete implementation (e.g., it was meant to be included in error messages) or leftover from a refactor.
**Fix:**
Remove the variable, or use it in error context:
```python
# Remove lines 73 and 81, or use last_step in the FAIL branch:
if status == "FAIL":
    logger.error("step_failed", step=step_name, hostname=hostname)
    # If keeping: last_step was presumably for error context
```

### WR-03: `_poll_health` timeout has a sleep-after-deadline gap

**File:** `inference_proxy/provisioning/provisioner.py:125-129`
**Issue:** The deadline check happens *after* the `except` block catches a connection error. If the deadline has already passed but the code enters the `except` block, it will correctly check and raise. However, when `health_poll_timeout=0` is set (as in test_provisioner.py:180), the first poll attempt happens *before* the deadline check, meaning one request is always made even with timeout=0. More importantly, if `health_poll_interval` is non-zero and a slow request takes longer than the remaining time budget, the method can overshoot the deadline by up to `health_poll_interval + request_latency` seconds. For a 600s default this is unlikely to matter, but the pattern is brittle.
**Fix:**
Check the deadline before sleeping, and consider checking before each request attempt:
```python
while True:
    if asyncio.get_running_loop().time() >= deadline:
        raise ProvisioningError(...)
    try:
        response = await client.get(url)
        ...
```

## Info

### IN-01: `known_hosts=None` disables SSH host key verification

**File:** `inference_proxy/provisioning/ssh_client.py:75`
**Issue:** Passing `known_hosts=None` to `asyncssh.connect` disables all host key verification, making connections vulnerable to MITM attacks. The comment documents this as intentional for lab servers that are reimaged frequently, and CLAUDE.md confirms "Internal network only, no external-facing endpoints in v1." Acceptable for the stated deployment context, but should be revisited if the network boundary changes.
**Fix:** No fix needed for v1. Add a setting to re-enable host key checking for production:
```python
known_hosts=None if settings.skip_host_key_check else ()  # () = use defaults
```

---

_Reviewed: 2026-07-02T00:15:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
