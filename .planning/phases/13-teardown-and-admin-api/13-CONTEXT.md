# Phase 13: Teardown and Admin API - Context

**Gathered:** 2026-07-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Operators can provision and decommission nodes through REST API endpoints. Teardown drains active connections, SSH-stops the remote vLLM container, and deregisters the node from etcd. Force teardown skips connection drain. Admin API exposes POST /admin/nodes/setup (async with task ID), GET /admin/provisioning/tasks (all operation status), and DELETE /admin/nodes/{id} (graceful or forced teardown). No dashboard UI (Phase 14).

</domain>

<decisions>
## Implementation Decisions

### Container Stop Sequence
- **D-01:** Teardown stops the remote container via SSH: `podman stop vllm-{model} && podman rm vllm-{model}`. Container name derived from `Node.model` field, matching Phase 10 D-03 naming convention.
- **D-02:** Leave container images on the remote host after teardown. Images stay cached for faster re-provisioning. Disk cleanup is a separate operational concern.
- **D-03:** Force teardown uses `podman rm --force vllm-{model}` — single command, kills and removes immediately.

### Teardown Code Location
- **D-04:** Add `teardown()` method to `NodeProvisioner`. Same class owns both setup and teardown lifecycle. Reuses existing SSHClient and EtcdClient injection. Mirrors `provision()` method pattern.

### Task Tracking
- **D-05:** Reuse etcd `ProvisioningState` under `/provisioning/{hostname}` for task tracking. Task ID = hostname. Extend `ProvisioningStep` enum with teardown steps (DRAINING, STOPPING_CONTAINER, DEREGISTERING, TEARDOWN_COMPLETE). No separate task tracking layer.
- **D-06:** POST /admin/nodes/setup returns 202 with `{"task_id": hostname}`. GET /admin/provisioning/tasks reads all `/provisioning/*` keys from etcd.
- **D-07:** Completed/failed task state stays in etcd until the same host is provisioned or torn down again. Next operation overwrites. No TTL, no manual cleanup needed.

### Drain Timeout
- **D-08:** Graceful teardown sets node to DRAINING, then waits up to 30 seconds (configurable via settings) for active connections to reach 0.
- **D-09:** When drain timeout expires and connections remain, proceed to force-stop (`podman stop + rm`). In-flight requests get connection errors. Clients can retry on another node (retry logic already exists in routes.py).
- **D-10:** `drain_timeout` added to `ProvisioningSettings` with default 30 seconds.

### etcd Cleanup
- **D-11:** Teardown deletes the node key from etcd (`/nodes/{hostname}`) — watcher propagates removal to NodeRegistry.
- **D-12:** Teardown overwrites `/provisioning/{hostname}` with TEARDOWN_COMPLETE terminal state. Keeps audit trail of what happened. Next `provision()` call overwrites it.

### Claude's Discretion
- Admin API request/response Pydantic models (naming, fields beyond what requirements specify)
- Error response format for setup/teardown failures (follow existing OpenAI-compatible error pattern)
- Background task execution mechanism (asyncio.create_task or similar — no Celery per CLAUDE.md)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provisioning Code (Phase 11-12 output — what gets extended)
- `inference_proxy/provisioning/provisioner.py` — NodeProvisioner with provision(), preflight(), _run_setup(), _run_start_vllm(), _poll_health(), _register_node(), _update_state()
- `inference_proxy/provisioning/state.py` — ProvisioningStep enum (extend with teardown steps), ProvisioningState model
- `inference_proxy/provisioning/ssh_client.py` — SSHClient wrapper (sole asyncssh consumer)

### Admin API (extend existing)
- `inference_proxy/api/admin.py` — admin_router with GET /admin/nodes, GET /admin/metrics. Add setup/teardown endpoints here.
- `inference_proxy/models/admin.py` — AdminNodeResponse, AdminMetricsResponse. Add setup/teardown request/response models.
- `inference_proxy/config/dependencies.py` — DI providers. Add get_provisioner() for admin routes.

### Drain and Node Lifecycle
- `inference_proxy/api/routes.py` — _maybe_remove_drained(), _scan_drained_nodes() handle DRAINING auto-removal
- `inference_proxy/models/node.py` — NodeStatus enum (HEALTHY, UNHEALTHY, DRAINING, PROVISIONING, UNKNOWN)
- `inference_proxy/routing/connection_tracker.py` — ConnectionTracker with get(), increment(), decrement(), remove()
- `inference_proxy/discovery/registry.py` — NodeRegistry with add(), remove(), get(), get_all()

### etcd Integration
- `inference_proxy/discovery/etcd_client.py` — EtcdClient with get_prefix(), watch_prefix(), put()
- `inference_proxy/discovery/serializer.py` — node_to_etcd(), node_from_etcd() serialization

### Application Wiring
- `inference_proxy/main.py` — Lifespan setup, app.state, provisioner needs to be created and stored here
- `inference_proxy/config/settings.py` — ProvisioningSettings (extend with drain_timeout)

### Project Context
- `.planning/ROADMAP.md` — Phase 13 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — TEAR-01, TEAR-02, API-01, API-02, API-03 requirement definitions
- `.planning/phases/12-provisioning-robustness/12-CONTEXT.md` — Phase 12 decisions (state machine, health checker coordination)
- `.planning/phases/11-ssh-provisioning/11-CONTEXT.md` — Phase 11 decisions (SSH config, provisioner design)
- `.planning/phases/10-script-hardening/10-CONTEXT.md` — Phase 10 decisions (container naming, step markers)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NodeProvisioner` — existing provisioner to extend with teardown() method
- `ProvisioningState` / `ProvisioningStep` — existing state tracking to extend with teardown steps
- `_maybe_remove_drained()` / `_scan_drained_nodes()` — existing drain removal logic in routes.py
- `admin_router` — existing admin API router to extend with setup/teardown endpoints
- `ConnectionTracker.get()` — check active connections during drain wait
- `EtcdClient.put()` / `get_prefix()` — read/write provisioning state

### Established Patterns
- Package-per-domain: teardown logic stays in `provisioning/` package
- DIP: NodeProvisioner depends on SSHClient and EtcdClient abstractions
- Frozen Pydantic models for domain objects
- `asyncio.to_thread()` for sync etcd3gw calls
- `asyncio.create_task()` for background work (no Celery)
- Write to etcd, let watcher propagate — never mutate NodeRegistry directly

### Integration Points
- `admin_router` — add POST /admin/nodes/setup, GET /admin/provisioning/tasks, DELETE /admin/nodes/{id}
- `ProvisioningStep` enum — extend with DRAINING, STOPPING_CONTAINER, DEREGISTERING, TEARDOWN_COMPLETE
- `ProvisioningSettings` — add `drain_timeout` (default 30s)
- `main.py` lifespan — create NodeProvisioner, store in app.state
- `dependencies.py` — add `get_provisioner()` DI provider

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 13-Teardown and Admin API*
*Context gathered: 2026-07-07*
