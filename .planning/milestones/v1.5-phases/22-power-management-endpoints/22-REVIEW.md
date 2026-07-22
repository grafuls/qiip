---
phase: 22-power-management-endpoints
reviewed: 2026-07-22T18:30:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - inference_proxy/models/admin.py
  - inference_proxy/api/admin.py
  - tests/api/test_admin.py
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: issues_found
---

# Phase 22: Code Review Report

**Reviewed:** 2026-07-22T18:30:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed power management endpoints (GET/POST `/admin/nodes/{hostname}/power`), supporting models (`PowerAction`, `PowerActionRequest`, `PowerStateResponse`), and their tests. The new power endpoints follow the existing pattern (dependency injection, `RedfishError` mapping to 502, hostname normalization) and have reasonable test coverage for the happy path and error cases.

One correctness bug found in the pre-existing `teardown_node` endpoint: it does not normalize hostnames, unlike every other endpoint that accepts a hostname. Two resilience/robustness warnings and one input validation gap on the new power endpoints.

## Critical Issues

### CR-01: Teardown endpoint missing hostname normalization

**File:** `inference_proxy/api/admin.py:141-152`
**Issue:** `teardown_node` uses `node_id` directly from the URL path parameter without calling `canonical_hostname()`. Every other endpoint that accepts a hostname normalizes it: `setup_node` (line 84), `get_power_state` (line 185), `execute_power_action` (line 202). `NodeRegistry.get()` performs an exact dictionary lookup, so `DELETE /admin/nodes/GPU01` returns 404 when the node was registered as `"gpu01"`. The un-normalized `node_id` is also passed to `provisioner.teardown()`, which uses it as an SSH hostname.
**Fix:**
```python
@admin_router.delete("/nodes/{node_id}", status_code=202)
async def teardown_node(
    node_id: str,
    force: bool = False,
    registry: NodeRegistry = Depends(get_registry),
    provisioner: NodeProvisioner = Depends(get_provisioner),
) -> TeardownResponse:
    """Trigger teardown of a node (runs in background)."""
    node_id = canonical_hostname(node_id)
    if registry.get(node_id) is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    provisioner.fire_background(provisioner.teardown(node_id, force=force))
    return TeardownResponse(task_id=node_id)
```

## Warnings

### WR-01: list_provisioning_tasks crashes entirely on one bad etcd entry

**File:** `inference_proxy/api/admin.py:135-137`
**Issue:** `json.loads(value_bytes)` and `TaskStatusResponse(**data)` are called without per-entry error handling. If any single etcd entry contains malformed JSON or missing required fields (e.g., `started_at`), the entire `/admin/provisioning/tasks` endpoint returns a 500 error, hiding all valid tasks. This is a resilience problem for an operational dashboard endpoint.
**Fix:**
```python
for value_bytes, _metadata in results:
    try:
        data = json.loads(value_bytes)
        tasks.append(TaskStatusResponse(**data))
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("task_parse_failed", raw=value_bytes[:200], error=str(exc))
```

### WR-02: Module-level pending_hosts set is per-process

**File:** `inference_proxy/api/admin.py:51`
**Issue:** `pending_hosts: set[str] = set()` is a module-level variable. With multi-worker deployments (`uvicorn --workers N`, N > 1), each worker gets its own copy. The dedup guard (D-08) silently fails because duplicate setup requests can land on different workers. The code comment references "D-08" as though this is a complete solution.
**Fix:** If multi-worker deployment is planned, move the dedup guard to etcd (e.g., a compare-and-swap key per hostname). If single-worker is the deployment model, add a comment documenting that constraint:
```python
# ponytail: single-worker-only dedup guard; move to etcd CAS if workers > 1
pending_hosts: set[str] = set()
```

### WR-03: Power endpoints accept unvalidated hostname path parameters

**File:** `inference_proxy/api/admin.py:178-207`
**Issue:** The `hostname` path parameter on `get_power_state` and `execute_power_action` is normalized via `canonical_hostname()` but never validated for format. The `SetupRequest` model validates hostnames (alphanumeric, 1-253 chars) via `validate_hostname`, but the power endpoints accept any string that fits in a URL path segment. An arbitrary hostname like `internal-service.corp` gets forwarded to `RedfishClient._resolve_bmc_host()` and used to construct an HTTPS request URL, creating a potential SSRF vector against the BMC network. While mitigated by the internal-only network constraint, the inconsistency with `SetupRequest` validation is a gap.
**Fix:** Extract hostname validation into a shared dependency or utility, and apply it to path parameters:
```python
def _validated_hostname(hostname: str) -> str:
    """Normalize and validate a hostname path parameter."""
    hostname = canonical_hostname(hostname)
    if not hostname or len(hostname) > 253:
        raise HTTPException(status_code=400, detail="Invalid hostname")
    if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?", hostname):
        raise HTTPException(status_code=400, detail="Hostname contains invalid characters")
    return hostname
```

## Info

### IN-01: Unused import in test file

**File:** `tests/api/test_admin.py:17`
**Issue:** `patch` is imported from `unittest.mock` but never used anywhere in the file.
**Fix:** Remove `patch` from the import:
```python
from unittest.mock import AsyncMock, MagicMock
```

---

_Reviewed: 2026-07-22T18:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
