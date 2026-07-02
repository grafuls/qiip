---
phase: 12-provisioning-robustness
reviewed: 2026-07-02T18:45:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - inference_proxy/config/settings.py
  - inference_proxy/models/node.py
  - inference_proxy/provisioning/provisioner.py
  - inference_proxy/provisioning/state.py
  - inference_proxy/resilience/health_checker.py
  - tests/models/test_node.py
  - tests/provisioning/test_provisioner.py
  - tests/provisioning/test_state.py
  - tests/resilience/test_health_checker.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-07-02T18:45:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the provisioning robustness additions: `NodeProvisioner` orchestrator, `ProvisioningState`/`ProvisioningStep` types, `ProvisioningSettings` config, health checker updates for PROVISIONING skip, and their tests.

The data models (`state.py`, `node.py`, `settings.py`) are clean. The health checker has a status-clobbering bug on DRAINING nodes. The provisioner has a concurrency hazard on instance state and a double-wrapping pattern in error propagation.

## Critical Issues

### CR-01: Health probe success clobbers DRAINING status back to HEALTHY

**File:** `inference_proxy/resilience/health_checker.py:194-196`
**Issue:** `_handle_probe_success` transitions any non-HEALTHY node to HEALTHY on a single successful probe. This includes DRAINING nodes. When an operator drains a node (via `registry.drain()`), the next health check cycle will overwrite its status back to HEALTHY, defeating the drain mechanism entirely. The code checks `if current_status != NodeStatus.HEALTHY` but should exclude DRAINING (and PROVISIONING, which is separately skipped in `_probe_all_nodes` but would hit this path if the skip were removed).

**Fix:**
```python
def _handle_probe_success(
    *,
    node_id: str,
    current_status: NodeStatus,
    registry: NodeRegistry,
    circuit_breaker_registry: CircuitBreakerRegistry,
    consecutive_failures: dict[str, int],
    node: Node,
) -> None:
    """Handle a successful health probe for a node."""
    consecutive_failures[node_id] = 0
    if current_status == NodeStatus.UNHEALTHY or current_status == NodeStatus.UNKNOWN:
        updated_node = node.model_copy(update={"status": NodeStatus.HEALTHY})
        registry.add(updated_node)
        circuit_breaker_registry.reset(node_id)
        logger.info(
            "node recovered to healthy",
            node_id=node_id,
            previous_status=str(current_status),
        )
    else:
        logger.debug("health probe succeeded", node_id=node_id)
```

### CR-02: Provisioner instance state `_provision_started_at` is not safe for concurrent provisioning

**File:** `inference_proxy/provisioning/provisioner.py:69,165,84`
**Issue:** `_provision_started_at` is stored as instance state (`self._provision_started_at`). If `provision()` is called concurrently for two different hosts on the same `NodeProvisioner` instance, the second call overwrites this field at line 165, causing subsequent `_update_state` calls for the first host to use the wrong `started_at` timestamp. This produces incorrect provisioning state records in etcd.

**Fix:** Pass `started_at` as a local variable through the call chain instead of storing on `self`:

```python
async def provision(self, hostname: str) -> None:
    started_at = datetime.now(timezone.utc)
    logger.info("provisioning_start", hostname=hostname)

    await self._update_state(hostname, ProvisioningStep.PENDING, started_at=started_at)
    # ... pass started_at to all _update_state calls ...

async def _update_state(
    self,
    hostname: str,
    step: ProvisioningStep,
    *,
    started_at: datetime,
    failed_step: str | None = None,
    error: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    state = ProvisioningState(
        hostname=hostname,
        current_step=step,
        started_at=started_at,
        updated_at=now,
        failed_step=failed_step,
        error=error,
    )
    # ...
```

## Warnings

### WR-01: ProvisioningError double-wraps itself in provision() error handler

**File:** `inference_proxy/provisioning/provisioner.py:204,209`
**Issue:** The `except` clause on line 204 catches `ProvisioningError` (raised by `_poll_health` and potentially `_run_start_vllm`), then line 209 wraps it in a new `ProvisioningError(str(exc)) from exc`. This creates a redundant chain: `ProvisioningError -> ProvisioningError` with identical messages. Callers catching `ProvisioningError` see a double-wrapped exception with a confusing `__cause__` chain. `RemoteCommandError` and `SSHConnectionError` should be wrapped; `ProvisioningError` should be re-raised directly.

**Fix:**
```python
        except ProvisioningError:
            await self._update_state(
                hostname, ProvisioningStep.FAILED,
                failed_step="provisioning", error=str(exc),
            )
            raise
        except (RemoteCommandError, SSHConnectionError) as exc:
            await self._update_state(
                hostname, ProvisioningStep.FAILED,
                failed_step=type(exc).__name__, error=str(exc),
            )
            raise ProvisioningError(str(exc)) from exc
```

### WR-02: `_update_state` swallows all exceptions without logging the exception itself

**File:** `inference_proxy/provisioning/provisioner.py:93-94`
**Issue:** The `except Exception` block logs a warning with hostname and step, but does not include `exc_info=True` or the exception message. When etcd writes fail during provisioning, operators have no way to diagnose why from the logs -- they only see "state_write_failed" with no details. For a best-effort path, silent swallowing is correct behavior, but the log message should include the exception.

**Fix:**
```python
        except Exception:
            logger.warning(
                "state_write_failed",
                hostname=hostname,
                step=step,
                exc_info=True,
            )
```

### WR-03: `_handle_probe_failure` only transitions HEALTHY -> UNHEALTHY, silently ignores UNKNOWN nodes

**File:** `inference_proxy/resilience/health_checker.py:226`
**Issue:** A node with `status=UNKNOWN` (the default status for newly created nodes) that fails `failure_threshold` probes is never marked UNHEALTHY because line 226 checks `current_status == NodeStatus.HEALTHY`. An UNKNOWN node that is unreachable stays UNKNOWN forever, never transitions to UNHEALTHY, and may still be selected by routing if the router does not explicitly exclude UNKNOWN status.

**Fix:**
```python
    if count >= failure_threshold and current_status in (
        NodeStatus.HEALTHY, NodeStatus.UNKNOWN
    ):
```

## Info

### IN-01: `Path.expanduser()` evaluated at class definition time in SSHSettings default

**File:** `inference_proxy/config/settings.py:101`
**Issue:** `Path("~/.ssh/id_rsa").expanduser()` is evaluated when the module is first imported, binding to the `HOME` environment variable at import time. If `HOME` is modified after import (e.g., in test fixtures), the default will not reflect the change. For pydantic-settings this is typically overridden via env vars in production, but can cause confusion in tests.

**Fix:** Use a `field_validator` or `default_factory` to defer evaluation:
```python
key_path: Path = Field(default_factory=lambda: Path("~/.ssh/id_rsa").expanduser())
```

---

_Reviewed: 2026-07-02T18:45:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
