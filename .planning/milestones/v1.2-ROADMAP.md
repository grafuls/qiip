# Roadmap: QUADS LLM Inference Proxy

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-06-25)
- ✅ **v1.1 Web UI** — Phases 7-9 (shipped 2026-07-01)
- **v1.2 Node Setup** — Phases 10-14 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-6) — SHIPPED 2026-06-25</summary>

- [x] Phase 1: Foundation (3/3 plans) — completed 2026-06-11
- [x] Phase 2: Service Discovery (2/2 plans) — completed 2026-06-11
- [x] Phase 3: Request Proxying and Streaming (2/2 plans) — completed 2026-06-12
- [x] Phase 4: Intelligent Routing (2/2 plans) — completed 2026-06-24
- [x] Phase 5: Resilience (2/2 plans) — completed 2026-06-25
- [x] Phase 6: Observability and Admin (2/2 plans) — completed 2026-06-25

</details>

<details>
<summary>v1.1 Web UI (Phases 7-9) — SHIPPED 2026-07-01</summary>

- [x] Phase 7: Request Metrics and Admin API (2/2 plans) — completed 2026-06-29
- [x] Phase 8: Dashboard and Node Fleet (2/2 plans) — completed 2026-07-01
- [x] Phase 9: Live Metrics and Auto-Refresh (1/1 plan) — completed 2026-07-01

</details>

### v1.2 Node Setup

- [x] **Phase 10: Script Hardening** - Harden setup and start scripts for safe automated execution (completed 2026-07-01)
- [x] **Phase 11: SSH Provisioning** - Gateway can SSH into a host and run the full setup sequence (completed 2026-07-02)
- [x] **Phase 12: Provisioning Robustness** - Pre-flight checks, state machine tracking, and health checker coordination (completed 2026-07-02)
- [x] **Phase 13: Teardown and Admin API** - Operators can provision and teardown nodes via REST API (completed 2026-07-07)
- [ ] **Phase 14: Dashboard Operations** - Dashboard UI for triggering setup/teardown and monitoring progress

## Phase Details

### Phase 10: Script Hardening

**Goal**: Setup and start scripts fail safely and can be re-run without leaving servers in broken states
**Depends on**: Nothing (v1.2 starting point)
**Requirements**: SCRIPT-01, SCRIPT-02, SCRIPT-03, SCRIPT-04
**Success Criteria** (what must be TRUE):

  1. Running setup.sh on a host that already completed setup skips all completed steps and succeeds
  2. setup.sh aborts immediately on any step failure with a non-zero exit code and clear error message
  3. NFS mount step completes or times out within a bounded period (never hangs indefinitely)
  4. start-vllm.sh replaces an existing container with the same name instead of failing on name collision

**Plans**: 2 plans
Plans:

- [x] 10-01-PLAN.md — Harden setup.sh (fail-fast, idempotency, NFS timeout, step markers)
- [x] 10-02-PLAN.md — Restructure container boundary (entrypoint.sh + host launcher + Containerfile)

### Phase 11: SSH Provisioning

**Goal**: Gateway can connect to a remote host over SSH and execute the full provisioning sequence end-to-end
**Depends on**: Phase 10
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04
**Success Criteria** (what must be TRUE):

  1. Gateway connects to a remote host via SSH using pre-configured keys (no password prompts)
  2. Gateway runs setup.sh on a remote host and captures its output and exit code
  3. Gateway builds and starts a vLLM container on the remote host with GPU auto-detection
  4. After vLLM starts, gateway polls the remote /health endpoint and registers the node in etcd once healthy

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 11-01-PLAN.md — SSHClient wrapper, settings, EtcdClient.put() with tests

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 11-02-PLAN.md — NodeProvisioner orchestrating full provisioning sequence

### Phase 12: Provisioning Robustness

**Goal**: Setup operations validate preconditions, report step-by-step progress, and coordinate with the health checker
**Depends on**: Phase 11
**Requirements**: PROV-05, PROV-06, PROV-07
**Success Criteria** (what must be TRUE):

  1. Before setup begins, the gateway verifies SSH is reachable, at least one GPU is present, and sufficient disk space exists
  2. Each setup operation tracks its current step and overall state (PENDING through COMPLETE or FAILED)
  3. A node in PROVISIONING state is not marked unhealthy by the health checker or selected by the router

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 12-01-PLAN.md — Foundation types (ProvisioningStep, ProvisioningState, NodeStatus.PROVISIONING) and health checker guard

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 12-02-PLAN.md — Pre-flight validation, state machine tracking, and PROVISIONING registration in provisioner

### Phase 13: Teardown and Admin API

**Goal**: Operators can provision and decommission nodes through REST API endpoints
**Depends on**: Phase 12
**Requirements**: TEAR-01, TEAR-02, API-01, API-02, API-03
**Success Criteria** (what must be TRUE):

  1. POST /admin/nodes/setup with a hostname returns 202 and a task ID; setup proceeds in the background
  2. GET /admin/provisioning/tasks returns status of all active and completed setup/teardown operations
  3. DELETE /admin/nodes/{id} drains connections, stops the container via SSH, and deregisters from etcd
  4. DELETE /admin/nodes/{id}?force=true skips connection drain and immediately stops and deregisters

**Plans**: 2 plans
Plans:

**Wave 1**

- [x] 13-01-PLAN.md — Teardown implementation (types, EtcdClient, NodeProvisioner.teardown)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 13-02-PLAN.md — Admin API endpoints (setup, tasks, teardown REST)

### Phase 14: Dashboard Operations

**Goal**: Operators can trigger and monitor setup/teardown from the web dashboard
**Depends on**: Phase 13
**Requirements**: DASH-01, DASH-02, DASH-03
**Success Criteria** (what must be TRUE):

  1. Dashboard has a form where operator enters a hostname and triggers node setup
  2. Each node row in the fleet table has a teardown button that triggers removal
  3. Dashboard displays setup/teardown progress with per-step status updates via polling

**Plans**: 1 plan
Plans:

- [x] 14-01-PLAN.md — Setup form, teardown buttons, and provisioning tasks panel

**UI hint**: yes

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-06-11 |
| 2. Service Discovery | v1.0 | 2/2 | Complete | 2026-06-11 |
| 3. Request Proxying and Streaming | v1.0 | 2/2 | Complete | 2026-06-12 |
| 4. Intelligent Routing | v1.0 | 2/2 | Complete | 2026-06-24 |
| 5. Resilience | v1.0 | 2/2 | Complete | 2026-06-25 |
| 6. Observability and Admin | v1.0 | 2/2 | Complete | 2026-06-25 |
| 7. Request Metrics and Admin API | v1.1 | 2/2 | Complete | 2026-06-29 |
| 8. Dashboard and Node Fleet | v1.1 | 2/2 | Complete | 2026-07-01 |
| 9. Live Metrics and Auto-Refresh | v1.1 | 1/1 | Complete | 2026-07-01 |
| 10. Script Hardening | v1.2 | 2/2 | Complete    | 2026-07-01 |
| 11. SSH Provisioning | v1.2 | 2/2 | Complete    | 2026-07-02 |
| 12. Provisioning Robustness | v1.2 | 2/2 | Complete    | 2026-07-02 |
| 13. Teardown and Admin API | v1.2 | 2/2 | Complete    | 2026-07-07 |
| 14. Dashboard Operations | v1.2 | 1/1 | Complete    | 2026-07-08 |
