# Phase 13: Teardown and Admin API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-07
**Phase:** 13-teardown-and-admin-api
**Areas discussed:** Container stop sequence, Task tracking for async ops, Drain timeout behavior, etcd cleanup scope

---

## Container Stop Sequence

### How to stop the remote container

| Option | Description | Selected |
|--------|-------------|----------|
| podman stop + rm by name | SSH in, run `podman stop vllm-{model} && podman rm vllm-{model}`. Clean removal. | ✓ |
| podman stop only | Leave stopped container on disk for debugging. | |
| podman rm --force | Single command, kills and removes. No graceful SIGTERM wait. | |

**User's choice:** podman stop + rm by name

### Image cleanup after teardown

| Option | Description | Selected |
|--------|-------------|----------|
| Leave images | Images stay cached for faster re-provisioning. | ✓ |
| Remove images too | Full cleanup via `podman rmi`. | |

**User's choice:** Leave images (recommended)

### Code location for teardown logic

| Option | Description | Selected |
|--------|-------------|----------|
| Add teardown() to NodeProvisioner | Same class owns setup and teardown lifecycle. | ✓ |
| Separate NodeTeardown class | Dedicated class, cleaner SRP. | |

**User's choice:** Add teardown() to NodeProvisioner

---

## Task Tracking for Async Ops

### Task storage mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse etcd ProvisioningState | Task ID = hostname. Extend with task_type field. No new layer. | ✓ |
| In-memory dict + etcd | UUID task IDs. More indirection. | |
| In-memory only | Simple but lost on restart. | |

**User's choice:** Reuse etcd ProvisioningState

### Completed task retention

| Option | Description | Selected |
|--------|-------------|----------|
| Keep until next operation | State stays until same host is provisioned/torn down again. | ✓ |
| TTL-based cleanup | Auto-expires via etcd lease. | |
| Keep forever | Full history, no cleanup. | |

**User's choice:** Keep until next operation (recommended, timeout)

---

## Drain Timeout Behavior

### Drain timeout duration

| Option | Description | Selected |
|--------|-------------|----------|
| 30 second timeout | Configurable via settings. | ✓ |
| No timeout, rely on force flag | Waits indefinitely, operator uses force=true. | |
| 60 second timeout | Longer grace for large model requests. | |

**User's choice:** 30 second timeout

### Drain expiry behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Force-stop, let requests fail | Proceed with podman stop + rm. Clients retry. | ✓ |
| Log warning, continue waiting | Never force-stop during graceful teardown. | |

**User's choice:** Force-stop, let requests fail (recommended, timeout)

---

## etcd Cleanup Scope

### Provisioning state cleanup

| Option | Description | Selected |
|--------|-------------|----------|
| Overwrite with TEARDOWN_COMPLETE | Update ProvisioningState to terminal state. Audit trail. | ✓ |
| Delete provisioning key | Remove entirely. Clean slate. | |
| Leave as-is | Only remove /nodes/. | |

**User's choice:** Overwrite with TEARDOWN_COMPLETE (recommended, timeout)

---

## Claude's Discretion

- Admin API request/response Pydantic models
- Error response format for setup/teardown failures
- Background task execution mechanism

## Deferred Ideas

None — discussion stayed within phase scope.
