---
phase: 18-dashboard-ui-update
type: code-review
depth: standard
status: issues_found
created: 2026-07-17
files_reviewed: 7
files_reviewed_list:
  - inference_proxy/api/admin.py
  - inference_proxy/models/admin.py
  - inference_proxy/static/css/dashboard.css
  - inference_proxy/static/js/dashboard.js
  - inference_proxy/templates/dashboard.html
  - tests/api/test_admin.py
  - tests/api/test_dashboard.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
---

# Phase 18: Code Review Report

**Reviewed:** 2026-07-17T14:30:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the QUADS status endpoint, unified node table with inline actions, manual setup toggle, and dropdown menus. The frontend work is solid -- DOM-based rendering avoids XSS via consistent use of `textContent`, and the data-driven `ACTION_CONFIG` pattern is clean. The backend models and QUADS status endpoint are well-structured with proper Pydantic frozen models.

Two categories of real defects: a TOCTOU race in the dedup guard that renders it bypassable under concurrent requests, and missing input validation on the hostname trust boundary that propagates unsanitized strings into etcd keys and downstream SSH operations.

## Critical Issues

### CR-01: TOCTOU Race in Setup Dedup Guard

**File:** `inference_proxy/api/admin.py:83-103`
**Issue:** The dedup guard checks `hostname in pending_hosts` (line 83) and adds to the set on line 103, but there are `await` points between them (line 92: `await quads_client.get_available()`). In Python's async single-threaded model, another coroutine handling a duplicate request can interleave between the check and the add. Both coroutines see the hostname as absent and both proceed to fire background provisioning tasks for the same host, defeating the guard entirely.

Reproduction scenario:
1. Request A for hostname `gpu01` passes check on line 83 (not in set)
2. Request A hits `await quads_client.get_available()` on line 92, yields control
3. Request B for hostname `gpu01` passes check on line 83 (still not in set, A hasn't added yet)
4. Both A and B add to set and both call `fire_background`, launching duplicate provisioning

**Fix:** Move `pending_hosts.add(hostname)` before the `await` boundary and clean up on validation failure:
```python
hostname = canonical_hostname(body.hostname)

if hostname in pending_hosts:
    raise HTTPException(
        status_code=409,
        detail=f"Setup already in progress for '{hostname}'",
    )

# Add immediately, before any await, to close the TOCTOU window
pending_hosts.add(hostname)

try:
    if quads_client is not None:
        try:
            available = await quads_client.get_available()
        except QUADSConnectionError as exc:
            raise HTTPException(
                status_code=503, detail="QUADS unavailable"
            ) from exc
        if hostname not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Host '{hostname}' is not available in QUADS",
            )
except Exception:
    pending_hosts.discard(hostname)
    raise
```

## Warnings

### WR-01: No Input Validation on SetupRequest Hostname

**File:** `inference_proxy/models/admin.py:52-58`
**Issue:** `SetupRequest.hostname` is a bare `str` with no format validation. The value propagates to etcd keys (`/provisioning/{hostname}`), HTTP URLs (`http://{hostname}:port/health`), and is used as the SSH connection target. While `canonical_hostname()` lowercases and strips, it does not reject values containing path separators, shell metacharacters, whitespace in the middle, or excessive length. An operator could accidentally (or a compromised client could intentionally) submit values like `../../etc` or `gpu01\ninjected-key` that corrupt etcd key structure.

The project constraint notes internal-only network, which lowers exploitability, but defense-in-depth requires validation at the trust boundary.

**Fix:** Add a Pydantic field validator:
```python
import re
from pydantic import field_validator

class SetupRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    hostname: str

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 253:
            raise ValueError("hostname must be 1-253 characters")
        if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?", v):
            raise ValueError("hostname contains invalid characters")
        return v
```

### WR-02: Endpoint Accesses Private Provisioner Attribute

**File:** `inference_proxy/api/admin.py:124-126`
**Issue:** `list_provisioning_tasks` reaches through to `provisioner._etcd_client.get_prefix("/provisioning/")`, accessing a private attribute. This couples the admin API to the internal structure of `NodeProvisioner` and breaks if the provisioner changes its etcd client field name or storage format. This is an encapsulation violation (DIP from CLAUDE.md conventions).

**Fix:** Add a public method to `NodeProvisioner`:
```python
# In provisioner.py
async def list_tasks(self) -> list[dict]:
    results = await asyncio.to_thread(
        self._etcd_client.get_prefix, "/provisioning/"
    )
    return [json.loads(v) for v, _meta in results]
```
Then in the endpoint: `tasks_raw = await provisioner.list_tasks()`.

### WR-03: Action Button Disabled Permanently on Click Until Next Poll

**File:** `inference_proxy/static/js/dashboard.js:193-198`
**Issue:** `createActionButton` sets `btn.disabled = true` on click but never re-enables it. `handleAction` is async but is called without `await`, so the promise result (including errors) is fire-and-forget from the button's perspective. If the action fails or succeeds, the button stays disabled until the entire node table is rebuilt on the next poll interval (up to 10 seconds by default). During this window, the user sees a dead button with no feedback about whether to wait or retry.

**Fix:** Await the action and re-enable:
```javascript
btn.addEventListener("click", async function () {
  btn.disabled = true;
  try {
    await handleAction(action, nodeId);
  } finally {
    btn.disabled = false;
  }
});
```

## Info

### IN-01: innerHTML Used Inconsistently

**File:** `inference_proxy/static/js/dashboard.js:25`
**Issue:** `renderTasks` uses `tbody.innerHTML = '<tr>...'` for the empty-state message, while all other DOM construction uses `document.createElement`. Not a security issue (hardcoded string, no user data), but inconsistent with the pattern used throughout the rest of the file.

**Fix:** Use `document.createElement` for consistency, or leave as-is (low impact).

### IN-02: relativeTime Produces Negative Values on Clock Skew

**File:** `inference_proxy/static/js/dashboard.js:162-167`
**Issue:** If the server's `last_sync` timestamp is in the future relative to the browser clock (clock skew, NTP drift), `diffMs` is negative and `relativeTime` returns strings like `-5m ago`. Not a crash, but confusing display.

**Fix:** Clamp to zero:
```javascript
const mins = Math.max(0, Math.floor(diffMs / 60000));
```

---

_Reviewed: 2026-07-17T14:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
