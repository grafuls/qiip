# Project Research Summary

**Project:** QUADS LLM Inference Proxy -- v1.2 Node Provisioning
**Domain:** SSH-based GPU node setup/teardown for LLM inference gateway
**Researched:** 2026-07-01
**Confidence:** HIGH

## Executive Summary

v1.2 adds operator-triggered SSH-based provisioning to the existing inference gateway. The gateway already owns node registration (etcd), health checking, and the dashboard -- embedding provisioning inside the same FastAPI process avoids IPC and duplicate etcd clients. The only new runtime dependency is asyncssh (native asyncio SSH), which fits the existing async-first architecture without adding thread-wrapping overhead. The provisioning workload is light (handful of nodes per day on an internal lab network), so a separate service or task queue is unnecessary.

The recommended approach is: asyncio background tasks managed by a ProvisioningManager that tracks per-host state machines, prevents concurrent operations on the same host, and exposes status via admin API endpoints the dashboard polls. Setup runs the existing `setup.sh` and container launch scripts remotely over SSH, then the gateway polls vLLM's `/health` endpoint and registers the node in etcd (letting the existing watcher propagate it to the registry). Teardown drains connections, stops the container via SSH, and deregisters from etcd.

The primary risks are: (1) the existing `setup.sh` is not idempotent and has no error handling -- a partial failure leaves servers in unrecoverable states; (2) SSH disconnections during long operations (driver install: 3-5 min) orphan processes on remote hosts; (3) race conditions between the new provisioner, the existing health checker, and the etcd watcher can mark freshly provisioned nodes as unhealthy before vLLM finishes loading. All three are mitigable: harden the setup script with `set -e` and prerequisite checks, use `nohup` + PID files for long commands, and add a `PROVISIONING` node status that the health checker skips.

## Key Findings

### Recommended Stack

One new dependency. Everything else reuses the existing stack.

**New:**
- **asyncssh >=2.24.0**: Async SSH client -- native asyncio, connection reuse, streaming output, typed (`py.typed`). 18M monthly PyPI downloads. Dual-licensed EPL-2.0/GPL-2.0+ (no concern for internal-only use).

**Reused from existing stack (no additions):**
- **httpx**: Health polling (`GET http://host:8000/health`) post-setup
- **etcd3gw**: Node registration/deregistration (same `put()`/`delete()` pattern)
- **pydantic-settings**: `ProvisioningSettings` sub-model for SSH key path, timeouts
- **structlog**: Structured logging of SSH operations
- **anyio**: Task groups for concurrent provisioning (transitive dep, already available)

**What NOT to add:**
- paramiko (sync-only, would be second thread-wrapped subsystem)
- fabric (CLI tool, wrong paradigm)
- ansible-runner (200MB dependency for `ssh host 'bash setup.sh'`)
- Celery/dramatiq/arq (no task queue needed for handful of daily ops)
- subprocess + system ssh (no structured error handling, no connection reuse)

### Expected Features

**Must have (table stakes):**
- SSH connection via asyncssh with key auth
- Remote execution of setup.sh (upload + run)
- Remote container build (`podman build`) + start (`podman run -d`)
- Health poll from gateway until node responds on `:8000/health`
- etcd registration using existing serializer
- Setup state machine (PENDING through COMPLETE/FAILED)
- Admin API: `POST /admin/nodes/setup`, `GET /admin/provisioning/tasks/{id}`, `DELETE /admin/nodes/{id}`
- Error capture and reporting per step
- Dashboard buttons for setup/teardown

**Should have (high value, low risk -- include in v1.2):**
- Pre-flight validation (SSH reachable, GPU present via `lspci`, disk space)
- Connection draining before teardown (reuse existing `registry.drain()`)
- Step-by-step progress in dashboard (poll status endpoint)
- Setup log capture (last N lines of SSH output)

**Defer:**
- Parallel multi-node setup (already async, just run multiple -- add when asked)
- Setup profiles/presets (auto-detection works, override when it doesn't)
- Persistent setup history (in-memory is fine, add SQLite when audit trail needed)
- Container image caching (minor optimization)
- Auto-scaling (explicitly deferred per PROJECT.md)
- WebSocket live log streaming (polling is good enough for an ops tool)

### Architecture Approach

Embed provisioning in the existing gateway process. New code lives in `inference_proxy/provisioning/` (3 new files: manager, provisioner, teardown) plus a models file. Five existing files get small modifications (settings, dependencies, admin routes, dashboard, main lifespan). The ProvisioningManager is created in lifespan, stored in `app.state`, injected via the existing DI pattern. Setup/teardown run as `asyncio.create_task()` background tasks -- not threads, not Celery, not `BackgroundTasks`.

**Major components:**
1. **ProvisioningManager** -- task registry, one-task-per-host enforcement, status tracking
2. **NodeProvisioner** -- SSH setup sequence (connect, run setup.sh, build container, start container, poll health, register in etcd)
3. **NodeTeardown** -- drain connections, stop container via SSH, deregister from etcd

**Key integration rule:** Write to etcd, let the watcher propagate. Never mutate NodeRegistry directly from the provisioner.

### Critical Pitfalls

1. **Event loop blocking** -- Long SSH operations (driver install, container build) must run as background asyncio tasks, not in request handlers. `POST /admin/nodes/setup` returns 202 immediately. Use asyncssh (native async), not paramiko.

2. **Partial setup state** -- `setup.sh` has no `set -e`, no idempotency, no error checking. A failure at step 5 of 10 leaves the server in an unrecoverable state. Must harden the script before automating it.

3. **Health checker race** -- The existing health checker will probe a newly registered node before vLLM finishes loading, marking it UNHEALTHY. Add a `PROVISIONING` status that the health checker and router skip.

4. **SSH disconnect orphans** -- If the connection drops mid-driver-install, the installer keeps running on the remote host. Use `nohup` + PID file pattern. Check for orphaned processes in pre-flight.

5. **Teardown partial failure** -- Container stop succeeds but etcd deregistration fails (or vice versa). Define teardown as a multi-step sequence with per-step error handling. Always deregister from etcd LAST.

## Implications for Roadmap

### Phase 1: Setup Script Hardening
**Rationale:** PITFALLS.md is emphatic -- building SSH automation on top of a non-idempotent, non-error-checked script is "building on sand." This must come first.
**Delivers:** Hardened `setup.sh` with `set -e`, prerequisite checks, idempotent steps, structured output markers, NFS timeout options, container name collision handling (`podman run --replace`).
**Addresses:** FEATURES: remote execution of setup.sh. PITFALLS: #2 (partial state), #7 (NFS hang), #8 (driver failure), #10 (container name collisions), #13 (exec blocks SSH -- switch to `podman run -d`).
**Avoids:** Automating a fragile script that fails in unrecoverable ways.

### Phase 2: Provisioning Core (SSH + State Machine)
**Rationale:** The core provisioning flow depends on hardened scripts. This phase builds the async SSH integration, task state machine, and ProvisioningManager.
**Delivers:** `ProvisioningManager`, `NodeProvisioner`, `NodeTeardown`, `ProvisioningSettings`, provisioning models (TaskStatus enum, ProvisioningTask).
**Uses:** asyncssh (new dep), existing etcd3gw, existing httpx for health polling.
**Implements:** Background task pattern (`asyncio.create_task`), per-host locking, status state machine.
**Avoids:** PITFALLS: #1 (event loop blocking), #4 (SSH disconnect orphans via nohup), #9 (concurrent ops via per-host lock).

### Phase 3: Admin API + Dashboard
**Rationale:** API endpoints and dashboard UI depend on the provisioning manager and models from Phase 2.
**Delivers:** `POST /admin/nodes/setup` (202 + task ID), `GET /admin/provisioning/tasks/{id}`, `DELETE /admin/nodes/{id}`, dashboard setup/teardown buttons, step-by-step progress display.
**Addresses:** FEATURES: admin API, dashboard integration, setup status tracking, error reporting.
**Avoids:** PITFALLS: #6 (key exposure -- use SecretStr in settings, never log key material).

### Phase 4: Integration + Hardening
**Rationale:** Wire provisioning into the existing node lifecycle. Handle the race conditions between provisioner, health checker, and etcd watcher.
**Delivers:** `PROVISIONING` node status, health checker skip logic, connection draining before teardown, pre-flight validation, teardown multi-step error handling, reconciliation of etcd state after partial failures.
**Addresses:** FEATURES: pre-flight validation, connection draining. PITFALLS: #3 (health checker race), #5 (teardown failure cleanup).

### Phase Ordering Rationale

- Scripts before SSH automation: you cannot safely automate what does not safely run manually.
- Core provisioning before API: the manager must exist before endpoints can call it.
- API before integration hardening: get the happy path working, then handle edge cases.
- Each phase is independently testable and deliverable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Script Hardening):** Needs investigation of actual kernel/driver version matrix on QUADS lab servers. The reboot-after-kernel-update requirement (PITFALLS #8) may mean setup is inherently two-phase (pre-reboot, post-reboot).
- **Phase 2 (Provisioning Core):** asyncssh API for `create_process` + streaming output needs a spike to validate the nohup+PID file pattern works cleanly with asyncssh's channel management.

Phases with standard patterns (skip research-phase):
- **Phase 3 (Admin API + Dashboard):** Follows existing FastAPI admin router and vanilla JS dashboard patterns already established in the codebase. No new patterns.
- **Phase 4 (Integration):** Adding an enum value and a conditional check to the health checker is well-understood. Connection draining already exists (`registry.drain()`).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | asyncssh is well-documented, 18M monthly downloads, verified API and typing support. Only new dep needed. |
| Features | HIGH | Feature set derived from existing `setup.sh`/`start-vllm.sh` scripts and actual codebase. Concrete, not speculative. |
| Architecture | HIGH | Embedding in existing gateway follows established patterns (lifespan, DI, app.state). Component boundaries clear. |
| Pitfalls | HIGH | Pitfalls verified against asyncssh issue tracker, NFS docs, NVIDIA driver forums, and the actual setup.sh source code. |

**Overall confidence:** HIGH

### Gaps to Address

- **Kernel update + reboot requirement:** PITFALLS #8 notes that `dnf update` may install a new kernel, requiring a reboot before driver install. The current `setup.sh` does not handle this. Determine during Phase 1 whether QUADS servers typically need kernel updates, and if so, design a two-phase setup (packages+reboot, then drivers+container).
- **NFS server reliability:** The NFS mount in `setup.sh` points to a specific server (`rdu-storage02.scalelab.redhat.com`). If this server is frequently unavailable, pre-flight checks alone are insufficient. Determine if an alternative cache strategy is needed.
- **asyncssh EPL-2.0 license:** Acceptable for internal use. Verify with legal if the project is ever open-sourced or distributed.

## Sources

### Primary (HIGH confidence)
- [asyncssh PyPI](https://pypi.org/project/asyncssh/) -- v2.24.0 (Jun 2026), API and version verification
- [asyncssh docs](https://asyncssh.readthedocs.io/) -- connection, process, streaming API
- [asyncssh GitHub](https://github.com/ronf/asyncssh) -- issue tracker for timeout and disconnect behavior
- Existing codebase: `auto-vllm-container/setup.sh`, `start-vllm.sh`, `Containerfile` -- the actual scripts being automated
- [NFS hard vs soft mounts](https://access.redhat.com/solutions/28211) -- mount hang behavior

### Secondary (MEDIUM confidence)
- [NVIDIA Container Toolkit troubleshooting](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/troubleshooting.html) -- GPU driver failure modes
- [Terraform remote-exec pitfalls](https://spacelift.io/blog/terraform-remote-exec) -- SSH provisioning idempotency patterns
- [asyncssh vs paramiko comparison](https://elegantnetwork.github.io/posts/comparing-ssh/) -- library selection rationale

---
*Research completed: 2026-07-01*
*Ready for roadmap: yes*
