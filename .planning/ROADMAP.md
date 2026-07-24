# Roadmap: QUADS LLM Inference Proxy

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-06-25)
- ✅ **v1.1 Web UI** — Phases 7-9 (shipped 2026-07-01)
- ✅ **v1.2 Node Setup** — Phases 10-14 (shipped 2026-07-08)
- ✅ **v1.3 QUADS Integration** — Phases 15-18 (shipped 2026-07-20)
- ✅ **v1.4 Chatbot Playground** — Phases 19-20 (shipped 2026-07-21)
- ✅ **v1.5 Node Setup Enhancements** — Phases 21-24 (shipped 2026-07-22)
- 🚧 **v1.6 LLMFit for Best Fit Models** — Phases 25-29 (in progress)

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

<details>
<summary>v1.5 Node Setup Enhancements (Phases 21-24) — SHIPPED 2026-07-22</summary>

- [x] Phase 21: Redfish Client & Configuration (2/2 plans) — completed 2026-07-22
- [x] Phase 22: Power Management Endpoints (1/1 plan) — completed 2026-07-22
- [x] Phase 23: Auto-Power-On in Provisioner (1/1 plan) — completed 2026-07-22
- [x] Phase 24: Provisioning Error Diagnostics (2/2 plans) — completed 2026-07-22

</details>

### v1.6 LLMFit for Best Fit Models (In Progress)

**Milestone Goal:** Integrate the llmfit CLI to recommend which LLM models best fit a server's hardware before deployment.

- [ ] **Phase 25: Core Models and Runner** - Pydantic models for llmfit JSON output and SSH-based runner service with timeout protection
- [ ] **Phase 26: llmfit Installation** - Install llmfit binary on target servers during provisioning as a non-fatal step
- [ ] **Phase 27: Admin API Endpoint** - Expose model recommendations via GET endpoint with structured error handling
- [ ] **Phase 28: Model Selection** - Wire operator-selected model into provisioning via VLLM_MODEL env var
- [ ] **Phase 29: Dashboard Recommendations** - Recommendations card on node detail page with ranked model table and hardware summary

## Phase Details

### Phase 25: Core Models and Runner
**Goal**: The gateway can execute llmfit on remote hosts and parse the results into typed models
**Depends on**: Nothing (first phase of v1.6)
**Requirements**: EXEC-01, EXEC-02, EXEC-03
**Success Criteria** (what must be TRUE):
  1. LLMFitRunner can SSH to a remote host, run `llmfit recommend --json`, and return parsed Pydantic models
  2. Pydantic models capture system hardware info (GPU name, VRAM, backend) and ranked model recommendations (name, score, fit level, estimated tok/s, memory)
  3. SSH execution times out after a configurable duration instead of hanging indefinitely
  4. Invalid or missing llmfit JSON output raises a typed error (not an unhandled exception)
**Plans**: 2 plans
Plans:
- [ ] 25-01-PLAN.md — Data contracts: Pydantic models, error hierarchy, SSHClient.run()
- [ ] 25-02-PLAN.md — Runner and tests: LLMFitRunner + full test suite

### Phase 26: llmfit Installation
**Goal**: New nodes have the llmfit binary available after provisioning
**Depends on**: Nothing (independent of Python-side work)
**Requirements**: INST-01, INST-02
**Success Criteria** (what must be TRUE):
  1. setup.sh downloads and installs the llmfit binary to /usr/local/bin on target servers
  2. llmfit installation failure does not block or fail the overall provisioning process
  3. Successful installation is logged; failure is logged as a warning with the reason
**Plans**: 2 plans
Plans:
- [ ] 25-01-PLAN.md � Data contracts: Pydantic models, error hierarchy, SSHClient.run()
- [ ] 25-02-PLAN.md � Runner and tests: LLMFitRunner + full test suite

### Phase 27: Admin API Endpoint
**Goal**: Operators can request model recommendations for any node via the admin API
**Depends on**: Phase 25
**Requirements**: API-01, API-02, API-03
**Success Criteria** (what must be TRUE):
  1. GET /admin/nodes/{hostname}/recommendations returns a ranked list of recommended models with scores, fit levels, and estimated performance
  2. Response includes detected hardware info (GPU name, VRAM, compute backend) for the queried host
  3. When llmfit fails (SSH error, timeout, parse error), the endpoint returns a structured error response with a descriptive message (not a raw 500)
**Plans**: 2 plans
Plans:
- [ ] 25-01-PLAN.md � Data contracts: Pydantic models, error hierarchy, SSHClient.run()
- [ ] 25-02-PLAN.md � Runner and tests: LLMFitRunner + full test suite

### Phase 28: Model Selection
**Goal**: Operators can specify which model to deploy when provisioning a node
**Depends on**: Nothing (independent of llmfit phases)
**Requirements**: SEL-01, SEL-02
**Success Criteria** (what must be TRUE):
  1. SetupRequest accepts an optional model field that operators can set when triggering provisioning
  2. When a model is specified, the provisioner passes it as the VLLM_MODEL environment variable to start-vllm.sh
**Plans**: 2 plans
Plans:
- [ ] 25-01-PLAN.md � Data contracts: Pydantic models, error hierarchy, SSHClient.run()
- [ ] 25-02-PLAN.md � Runner and tests: LLMFitRunner + full test suite

### Phase 29: Dashboard Recommendations
**Goal**: Operators can view model recommendations and hardware details for any node in the dashboard
**Depends on**: Phase 27
**Requirements**: DASH-01, DASH-02
**Success Criteria** (what must be TRUE):
  1. Node detail page displays a recommendations card with a ranked table showing model name, score, fit level, estimated tok/s, and memory usage
  2. Recommendations card shows a hardware summary with detected GPU name, VRAM, and compute backend
  3. Recommendations load on demand when the operator views a node's details
**Plans**: 2 plans
Plans:
- [ ] 25-01-PLAN.md � Data contracts: Pydantic models, error hierarchy, SSHClient.run()
- [ ] 25-02-PLAN.md � Runner and tests: LLMFitRunner + full test suite
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 25 -> 26 -> 27 -> 28 -> 29
(Phases 26 and 28 are independent but ordered for logical flow)

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
| 21. Redfish Client & Configuration | v1.5 | 2/2 | Complete | 2026-07-22 |
| 22. Power Management Endpoints | v1.5 | 1/1 | Complete | 2026-07-22 |
| 23. Auto-Power-On in Provisioner | v1.5 | 1/1 | Complete | 2026-07-22 |
| 24. Provisioning Error Diagnostics | v1.5 | 2/2 | Complete | 2026-07-22 |
| 25. Core Models and Runner | v1.6 | 0/2 | In progress | - |
| 26. llmfit Installation | v1.6 | 0/0 | Not started | - |
| 27. Admin API Endpoint | v1.6 | 0/0 | Not started | - |
| 28. Model Selection | v1.6 | 0/0 | Not started | - |
| 29. Dashboard Recommendations | v1.6 | 0/0 | Not started | - |
