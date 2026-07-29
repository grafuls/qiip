# Roadmap: QUADS LLM Inference Proxy

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-06-25)
- ✅ **v1.1 Web UI** — Phases 7-9 (shipped 2026-07-01)
- ✅ **v1.2 Node Setup** — Phases 10-14 (shipped 2026-07-08)
- ✅ **v1.3 QUADS Integration** — Phases 15-18 (shipped 2026-07-20)
- ✅ **v1.4 Chatbot Playground** — Phases 19-20 (shipped 2026-07-21)
- ✅ **v1.5 Node Setup Enhancements** — Phases 21-24 (shipped 2026-07-22)
- ✅ **v1.6 LLMFit for Best Fit Models** — Phases 25-29 (shipped 2026-07-26)
- ✅ **v1.7 HuggingFace Integration** — Phases 30-32 (shipped 2026-07-29)
- ✅ **v1.8 Nodes Power Control** — Phases 33-34 (shipped 2026-07-29)
- 🚧 **v1.9 Model Selection in Node Setup** — Phase 35 (in progress)

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

<details>
<summary>v1.6 LLMFit for Best Fit Models (Phases 25-29) — SHIPPED 2026-07-26</summary>

- [x] Phase 25: Core Models and Runner (2/2 plans) — completed 2026-07-25
- [x] Phase 26: llmfit Installation (1/1 plan) — completed 2026-07-26
- [x] Phase 27: Admin API Endpoint (2/2 plans) — completed 2026-07-26
- [x] Phase 28: Model Selection (1/1 plan) — completed 2026-07-26
- [x] Phase 29: Dashboard Recommendations (1/1 plan) — completed 2026-07-26

</details>

<details>
<summary>v1.7 HuggingFace Integration (Phases 30-32) — SHIPPED 2026-07-29</summary>

- [x] Phase 30: Foundation & Model Catalog (2/2 plans) — completed 2026-07-28
- [x] Phase 31: Download Service & API (2/2 plans) — completed 2026-07-28
- [x] Phase 32: Dashboard Download Integration (1/1 plan) — completed 2026-07-29

</details>

<details>
<summary>v1.8 Nodes Power Control (Phases 33-34) — SHIPPED 2026-07-29</summary>

- [x] Phase 33: Power State Display (1/1 plan) — completed 2026-07-29
- [x] Phase 34: Power Action Controls (1/1 plan) — completed 2026-07-29

</details>

### 🚧 v1.9 Model Selection in Node Setup

- [ ] **Phase 35: Model Selector on Node Detail Page** - Model dropdown from downloaded catalog, required for setup, sent in SetupRequest.model

## Phase Details

### Phase 35: Model Selector on Node Detail Page
**Goal**: Operators select a downloaded model from a dropdown on the node detail page before setting up a node
**Depends on**: Nothing (catalog API and SetupRequest.model exist)
**Requirements**: MDL-01, MDL-02, MDL-03
**Success Criteria** (what must be TRUE):
  1. Node detail page shows a model selector dropdown populated from GET /admin/models/catalog
  2. Setup action on node detail page sends the selected model in SetupRequest.model
  3. Setup button is disabled when no models are downloaded (catalog is empty)
**Plans**: 1 plan
Plans:
- [ ] 35-01-PLAN.md — Model selector card and catalog wiring
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 35

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
| 25. Core Models and Runner | v1.6 | 2/2 | Complete | 2026-07-25 |
| 26. llmfit Installation | v1.6 | 1/1 | Complete | 2026-07-26 |
| 27. Admin API Endpoint | v1.6 | 2/2 | Complete | 2026-07-26 |
| 28. Model Selection | v1.6 | 1/1 | Complete | 2026-07-26 |
| 29. Dashboard Recommendations | v1.6 | 1/1 | Complete | 2026-07-26 |
| 30. Foundation & Model Catalog | v1.7 | 2/2 | Complete | 2026-07-28 |
| 31. Download Service & API | v1.7 | 2/2 | Complete | 2026-07-28 |
| 32. Dashboard Download Integration | v1.7 | 1/1 | Complete | 2026-07-29 |
| 33. Power State Display | v1.8 | 1/1 | Complete | 2026-07-29 |
| 34. Power Action Controls | v1.8 | 1/1 | Complete | 2026-07-29 |
| 35. Model Selector on Node Detail Page | v1.9 | 0/? | Not started | - |
