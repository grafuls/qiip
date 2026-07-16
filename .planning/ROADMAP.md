# Roadmap: QUADS LLM Inference Proxy

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-06-25)
- ✅ **v1.1 Web UI** — Phases 7-9 (shipped 2026-07-01)
- ✅ **v1.2 Node Setup** — Phases 10-14 (shipped 2026-07-08)
- **v1.3 QUADS Integration** — Phases 15-18 (in progress)

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

<details>
<summary>v1.2 Node Setup (Phases 10-14) — SHIPPED 2026-07-08</summary>

- [x] Phase 10: Script Hardening (2/2 plans) — completed 2026-07-01
- [x] Phase 11: SSH Provisioning (2/2 plans) — completed 2026-07-02
- [x] Phase 12: Provisioning Robustness (2/2 plans) — completed 2026-07-02
- [x] Phase 13: Teardown and Admin API (2/2 plans) — completed 2026-07-07
- [x] Phase 14: Dashboard Operations (1/1 plan) — completed 2026-07-08

</details>

### v1.3 QUADS Integration (In Progress)

**Milestone Goal:** Integrate with the QUADS REST API to show all available GPU hosts in a unified node list with inline provisioning controls, replacing the separate setup form.

- [x] **Phase 15: QUADS Client and Models** - Connect to QUADS API, parse host data, normalize hostnames (completed 2026-07-16)
- [x] **Phase 16: Background Polling** - Periodic QUADS polling with in-memory caching and staleness tracking (completed 2026-07-16)
- [x] **Phase 17: Unified Node List and Admin API** - Merge QUADS hosts with etcd nodes, state-aware actions, dedup guard (completed 2026-07-16)
- [ ] **Phase 18: Dashboard UI Update** - Unified table with inline action buttons and QUADS status indicator

## Phase Details

### Phase 15: QUADS Client and Models
**Goal**: Gateway can discover GPU hosts from the QUADS REST API
**Depends on**: Phase 14 (existing gateway codebase)
**Requirements**: QUADS-01, QUADS-03, QUADS-04
**Success Criteria** (what must be TRUE):
  1. Gateway connects to a configured QUADS base URL and retrieves the host list
  2. Only hosts with GPU processors appear in the filtered result
  3. QUADS FQDNs and etcd short names resolve to the same canonical hostname
  4. QUADS connection settings (base URL, timeouts) are configurable via environment variables
**Plans**: 1 plan
Plans:
- [x] 15-01-PLAN.md -- QUADSHost model, QUADSClient, config, DI wiring

### Phase 16: Background Polling
**Goal**: Gateway maintains a fresh cached list of QUADS hosts without blocking request handling
**Depends on**: Phase 15
**Requirements**: QUADS-02
**Success Criteria** (what must be TRUE):
  1. QUADS host list refreshes automatically at a configurable interval
  2. Cached host data remains available when the QUADS API is unreachable
  3. Poller tracks staleness (last successful sync time, consecutive failures)
  4. Poller starts and stops cleanly with the gateway lifecycle
**Plans**: 1 plan
Plans:
- [x] 16-01-PLAN.md — QUADSPoller class, tests, lifespan wiring

### Phase 17: Unified Node List and Admin API
**Goal**: Operators see a single merged view of all systems with state-aware inline actions
**Depends on**: Phase 15, Phase 16
**Requirements**: NODES-01, NODES-02, NODES-03, NODES-04, NODES-05
**Success Criteria** (what must be TRUE):
  1. GET /admin/nodes returns a unified list merging QUADS available hosts with etcd-registered nodes by hostname
  2. Each node in the response includes its computed state (available, provisioned, healthy, unhealthy) and available actions
  3. Setup request for an already-pending host returns 409 Conflict
  4. Setup request re-validates host availability against live QUADS data, not the polling cache
  5. Inline actions trigger the correct operations: Setup for available, Teardown for healthy, Teardown+Retry for unhealthy
**Plans**: 1 plan
Plans:
- [x] 17-01-PLAN.md — UnifiedNodeService, extended AdminNodeResponse, dedup guard, QUADS re-validation

### Phase 18: Dashboard UI Update
**Goal**: Dashboard displays the unified node list with inline provisioning controls
**Depends on**: Phase 17
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-04, DASH-05
**Success Criteria** (what must be TRUE):
  1. Dashboard shows a single table with all nodes across all states (available, provisioned, healthy, unhealthy)
  2. Each node row shows inline action buttons matching its current state
  3. Standalone setup form is removed; a collapsed manual hostname input is available as fallback
  4. QUADS connection status indicator shows connected/stale/unavailable with cache age
  5. GPU hardware info (vendor, model) is visible per host in the node list
**Plans**: TBD
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
| 10. Script Hardening | v1.2 | 2/2 | Complete | 2026-07-01 |
| 11. SSH Provisioning | v1.2 | 2/2 | Complete | 2026-07-02 |
| 12. Provisioning Robustness | v1.2 | 2/2 | Complete | 2026-07-02 |
| 13. Teardown and Admin API | v1.2 | 2/2 | Complete | 2026-07-07 |
| 14. Dashboard Operations | v1.2 | 1/1 | Complete | 2026-07-08 |
| 15. QUADS Client and Models | v1.3 | 1/1 | Complete    | 2026-07-16 |
| 16. Background Polling | v1.3 | 1/1 | Complete    | 2026-07-16 |
| 17. Unified Node List and Admin API | v1.3 | 1/1 | Complete    | 2026-07-16 |
| 18. Dashboard UI Update | v1.3 | 0/? | Not started | - |
