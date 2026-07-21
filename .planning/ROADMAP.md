# Roadmap: QUADS LLM Inference Proxy

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-06-25)
- ✅ **v1.1 Web UI** — Phases 7-9 (shipped 2026-07-01)
- ✅ **v1.2 Node Setup** — Phases 10-14 (shipped 2026-07-08)
- ✅ **v1.3 QUADS Integration** — Phases 15-18 (shipped 2026-07-20)
- ✅ **v1.4 Chatbot Playground** — Phases 19-20 (shipped 2026-07-21)
- 🚧 **v1.5 Node Setup Enhancements** — Phases 21-24 (in progress)

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

<details>
<summary>v1.3 QUADS Integration (Phases 15-18) — SHIPPED 2026-07-20</summary>

- [x] Phase 15: QUADS Client and Models (1/1 plan) — completed 2026-07-16
- [x] Phase 16: Background Polling (1/1 plan) — completed 2026-07-16
- [x] Phase 17: Unified Node List and Admin API (1/1 plan) — completed 2026-07-16
- [x] Phase 18: Dashboard UI Update (2/2 plans) — completed 2026-07-17

</details>

<details>
<summary>v1.4 Chatbot Playground (Phases 19-20) — SHIPPED 2026-07-21</summary>

- [x] Phase 19: Chat Page and Streaming (2/2 plans) — completed 2026-07-21
- [x] Phase 20: Chat Configuration (1/1 plan) — completed 2026-07-21

</details>

### 🚧 v1.5 Node Setup Enhancements (In Progress)

**Milestone Goal:** Add Redfish-based power management and improve provisioning failure diagnostics

- [ ] **Phase 21: Redfish Client & Configuration** - BMC communication foundation with credential safety and human-readable error mapping
- [ ] **Phase 22: Power Management Endpoints** - Admin API for manual power on/off/restart/status operations
- [ ] **Phase 23: Auto-Power-On in Provisioner** - Automatic power-on before SSH provisioning for offline servers
- [ ] **Phase 24: Provisioning Error Diagnostics** - Step-level error capture with inline dashboard display

## Phase Details

### Phase 21: Redfish Client & Configuration

**Goal**: The gateway can communicate with server BMCs via Redfish API with secure credential handling and human-readable errors
**Depends on**: Nothing (foundation for v1.5)
**Requirements**: DIAG-03
**Success Criteria** (what must be TRUE):

  1. RedfishClient can query power state from a BMC and return On/Off/PoweringOn/PoweringOff
  2. RedfishClient can issue power actions (On, ForceOff, GracefulRestart, ForceRestart) to a BMC
  3. Redfish error responses are translated to human-readable messages (not raw JSON)
  4. BMC credentials are never exposed in logs, error messages, or API responses

**Plans:** 2 plans
Plans:
**Wave 1**

- [ ] 21-01-PLAN.md — Redfish client module (settings, errors, client, tests)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 21-02-PLAN.md — Lifespan wiring (DI, main.py, conftest)

### Phase 22: Power Management Endpoints

**Goal**: Operators can manage server power from the admin API
**Depends on**: Phase 21
**Requirements**: PWR-01, PWR-02, PWR-03, PWR-04
**Success Criteria** (what must be TRUE):

  1. Admin can power on a node via POST to the admin power endpoint
  2. Admin can power off a node via POST to the admin power endpoint
  3. Admin can restart a node via POST to the admin power endpoint
  4. Admin can query current power state of a node via GET from the admin API
  5. Power endpoints return 503 when Redfish is not configured

**Plans**: TBD

### Phase 23: Auto-Power-On in Provisioner

**Goal**: Provisioning works even when target servers are powered off
**Depends on**: Phase 21
**Requirements**: PWR-05
**Success Criteria** (what must be TRUE):

  1. Setup operation automatically powers on a node that is off before starting SSH provisioning
  2. Dashboard shows POWERING_ON step while the server boots
  3. Provisioning waits for SSH availability after power-on before proceeding to preflight

**Plans**: TBD
**UI hint**: yes

### Phase 24: Provisioning Error Diagnostics

**Goal**: Operators can see why provisioning failed without checking logs
**Depends on**: Nothing (independent of Redfish phases)
**Requirements**: DIAG-01, DIAG-02
**Success Criteria** (what must be TRUE):

  1. Failed provisioning captures the specific step name where failure occurred
  2. Failed provisioning captures error details (stderr/exception message)
  3. Dashboard displays failure details inline for failed nodes instead of just a status badge

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 21 → 22 → 23 → 24
(Phase 24 is independent of 21-23 but ordered last per research rationale)

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
| 15. QUADS Client and Models | v1.3 | 1/1 | Complete | 2026-07-16 |
| 16. Background Polling | v1.3 | 1/1 | Complete | 2026-07-16 |
| 17. Unified Node List and Admin API | v1.3 | 1/1 | Complete | 2026-07-16 |
| 18. Dashboard UI Update | v1.3 | 2/2 | Complete | 2026-07-17 |
| 19. Chat Page and Streaming | v1.4 | 2/2 | Complete | 2026-07-21 |
| 20. Chat Configuration | v1.4 | 1/1 | Complete | 2026-07-21 |
| 21. Redfish Client & Configuration | v1.5 | 0/2 | In progress | - |
| 22. Power Management Endpoints | v1.5 | 0/0 | Not started | - |
| 23. Auto-Power-On in Provisioner | v1.5 | 0/0 | Not started | - |
| 24. Provisioning Error Diagnostics | v1.5 | 0/0 | Not started | - |
