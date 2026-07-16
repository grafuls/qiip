---
phase: 17
status: issues_found
depth: standard
files_reviewed: 7
files_reviewed_list:
  - inference_proxy/services/unified_nodes.py
  - inference_proxy/models/admin.py
  - inference_proxy/api/admin.py
  - inference_proxy/config/dependencies.py
  - tests/services/test_unified_nodes.py
  - tests/api/test_admin.py
  - tests/conftest.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
reviewed_at: 2026-07-16
---

# Phase 17: Code Review Report

**Reviewed:** 2026-07-16
**Depth:** standard
**Files Reviewed:** 7 (4 source, 3 test)
**Status:** issues_found

## Summary

Phase 17 introduces a clean `UnifiedNodeService` that merges QUADS hosts with etcd nodes, extends the admin response model, and adds a dedup guard and live QUADS re-validation to the setup endpoint. The service design is solid and well-tested for the happy path. However, there is a hostname normalization bug that causes two distinct failures: the QUADS re-validation comparison uses raw user input against canonicalized hostnames (false 400 rejections), and node IDs registered via the provisioner will fail to join with QUADS hostnames in the unified list when casing or trailing-dot differences exist. A secondary cluster of issues around error handling and encapsulation in the admin router should be addressed.

## Critical Issues

### CR-01: QUADS re-validation compares raw hostname against canonicalized list

**File:** `inference_proxy/api/admin.py:90`
**Issue:** `body.hostname` is raw user input. `quads_client.get_available()` returns hostnames normalized via `canonical_hostname()` (lowercase, stripped, trailing-dot removed). The check `hostname not in available` will falsely reject a valid host when the user submits `"GPU01.example.com."` but the available list contains `"gpu01.example.com"`. This also means the non-normalized hostname propagates to the provisioner and into etcd as the `node_id`, creating a merge-key mismatch with QUADS data in the unified list (CR-02).

**Fix:**
```python
from inference_proxy.quads.client import canonical_hostname

hostname = canonical_hostname(body.hostname)
```
Apply this at line 73, immediately after extracting from the request body, so all downstream consumers (dedup guard, re-validation, provisioner) use the canonical form.

### CR-02: Unified merge key mismatch between etcd node_id and QUADS hostname

**File:** `inference_proxy/services/unified_nodes.py:46,55,61`
**Issue:** The merge logic joins etcd nodes and QUADS hosts by matching `node.node_id` against `host.hostname`. QUADS hostnames are canonicalized by the QUADS client, but etcd `node_id` values come from whatever the provisioner received (raw user input via `setup_node`). When casing or formatting differs, `etcd_map.get(hostname)` on line 61 returns `None`, and the node either appears as "available" (if in the available set) or is silently dropped -- even though it is actively provisioned in etcd.

This is the downstream consequence of CR-01. If CR-01 is fixed (normalize at the admin API entry point), this issue is resolved for the provisioner path. However, nodes registered by other means (direct etcd writes, watch thread) could still mismatch.

**Fix:** The primary fix is CR-01 (normalize at entry). As defense-in-depth, normalize the merge key in `get_unified_nodes`:
```python
etcd_map = {n.node_id.strip().lower().rstrip("."): n for n in self._registry.get_all()}
```
Or import and use `canonical_hostname` for both sides of the join.

## Warnings

### WR-01: pending_hosts leaks if fire_background raises

**File:** `inference_proxy/api/admin.py:96-104`
**Issue:** `pending_hosts.add(hostname)` executes before `provisioner.fire_background(...)`. If `fire_background` raises (e.g., no running event loop in edge cases, or a future refactor breaks it), the hostname remains in `pending_hosts` permanently, blocking all future setup attempts for that host. The cleanup coroutine never runs.

**Fix:**
```python
pending_hosts.add(hostname)
try:
    provisioner.fire_background(_provision_and_cleanup())
except Exception:
    pending_hosts.discard(hostname)
    raise
```

### WR-02: list_provisioning_tasks accesses private _etcd_client and has no error handling

**File:** `inference_proxy/api/admin.py:113-119`
**Issue:** Two problems in one endpoint:
1. `provisioner._etcd_client` accesses a private attribute, coupling the endpoint to the provisioner's internal structure. If the provisioner is refactored, this endpoint silently breaks.
2. `json.loads(value_bytes)` and `TaskStatusResponse(**data)` have no error handling. Malformed JSON in etcd or unexpected fields will surface as an unhandled 500 to the client.

**Fix:** Add a `list_tasks()` method to `NodeProvisioner` that encapsulates the etcd query and error handling:
```python
# In NodeProvisioner
async def list_tasks(self) -> list[dict]:
    results = await asyncio.to_thread(self._etcd_client.get_prefix, "/provisioning/")
    tasks = []
    for value_bytes, _metadata in results:
        try:
            tasks.append(json.loads(value_bytes))
        except (json.JSONDecodeError, ValueError):
            logger.warning("malformed_task_entry", raw=value_bytes)
    return tasks
```

### WR-03: _STATE_ACTIONS silently returns empty actions for unmapped states

**File:** `inference_proxy/services/unified_nodes.py:20-26,85`
**Issue:** `_STATE_ACTIONS` maps five states but `NodeStatus` has five enum values (healthy, unhealthy, draining, provisioning, unknown). The "unknown" state silently gets `[]` via the `dict.get` default. If a new `NodeStatus` value is added in the future, it will also silently have no actions with no warning. This fragility is compounded by the lack of a test for `NodeStatus.UNKNOWN`.

**Fix:** Either add `"unknown": []` explicitly to `_STATE_ACTIONS` to document the intent, or log a warning when a state is not found:
```python
actions = _STATE_ACTIONS.get(state)
if actions is None:
    logger.warning("unmapped_node_state", state=state, node_id=node.node_id)
    actions = []
```

## Info

### IN-01: get_quads_poller dependency is defined but unused by any endpoint

**File:** `inference_proxy/config/dependencies.py:100-105`
**Issue:** `get_quads_poller` is defined and overridden in `conftest.py`, but no endpoint handler depends on it. The `get_unified_node_service` factory accesses `request.app.state.quads_poller` directly instead. This is dead code in the dependency layer.

**Fix:** Either remove `get_quads_poller` or refactor `get_unified_node_service` to use it as a sub-dependency for consistency with the other DI providers.

## Coverage Assessment

Test coverage is solid for the happy path and core merge logic (14 unit tests for UnifiedNodeService, 29 integration tests for admin API). Specific gaps:

- **No test for hostname case-sensitivity mismatch** -- all tests use lowercase hostnames, so CR-01/CR-02 are not caught by the test suite.
- **No test for `NodeStatus.UNKNOWN`** -- the state/actions mapping is tested for healthy, unhealthy, provisioning, and draining, but not unknown.
- **No test for malformed etcd data in `list_provisioning_tasks`** -- only valid JSON is tested.
- **Coroutine leak in mocked `fire_background`** -- when `fire_background` is a `MagicMock`, the coroutine passed to it is never awaited, generating `RuntimeWarning: coroutine was never awaited`. This does not affect test correctness but produces noisy warnings.

---

_Reviewed: 2026-07-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
