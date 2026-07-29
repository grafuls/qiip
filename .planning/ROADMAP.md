# Roadmap: QUADS LLM Inference Proxy

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-06-25)
- ✅ **v1.1 Web UI** — Phases 7-9 (shipped 2026-07-01)
- ✅ **v1.2 Node Setup** — Phases 10-14 (shipped 2026-07-08)
- ✅ **v1.3 QUADS Integration** — Phases 15-18 (shipped 2026-07-20)
- ✅ **v1.4 Chatbot Playground** — Phases 19-20 (shipped 2026-07-21)
- ✅ **v1.5 Node Setup Enhancements** — Phases 21-24 (shipped 2026-07-22)
- ✅ **v1.6 LLMFit for Best Fit Models** — Phases 25-29 (shipped 2026-07-26)
- 🚧 **v1.7 HuggingFace Integration** — Phases 30-32 (in progress)

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

### v1.7 HuggingFace Integration (In Progress)

**Milestone Goal:** Download models from HuggingFace Hub to NFS storage, integrated with llmfit recommendations in the dashboard.

- [x] **Phase 30: Foundation & Model Catalog** - HuggingFace settings, NFS model catalog service, and catalog API endpoint (completed 2026-07-28)
- [x] **Phase 31: Download Service & API** - Background model downloads with dedicated thread pool, status tracking, and admin endpoints (completed 2026-07-28)
- [x] **Phase 32: Dashboard Download Integration** - Download buttons, "already downloaded" badges, and status display in recommendations table (completed 2026-07-29)

## Phase Details

### Phase 30: Foundation & Model Catalog

**Goal**: Gateway can discover which models are already downloaded on NFS storage
**Depends on**: Nothing (first phase of v1.7)
**Requirements**: CFG-01, CFG-02, CAT-01, CAT-02
**Success Criteria** (what must be TRUE):

  1. Operator can configure HuggingFace API token and NFS cache directory path via environment variables
  2. Gateway scans the NFS cache directory and returns a list of downloaded model repo IDs
  3. GET /admin/models/catalog returns all models currently available on NFS with their repo IDs

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 30-01-PLAN.md — HuggingFace settings, catalog service, and unit tests

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 30-02-PLAN.md — Admin endpoint wiring, lifespan startup, integration tests

### Phase 31: Download Service & API

**Goal**: Operators can download models from HuggingFace Hub to NFS and monitor download status
**Depends on**: Phase 30
**Requirements**: DL-01, DL-02, DL-03, DL-04
**Success Criteria** (what must be TRUE):

  1. POST /admin/models/download triggers a background download of a specified model from HuggingFace Hub to NFS
  2. Downloads use the configured HF token to access gated models (Llama, Mistral, etc.)
  3. Gateway tracks per-model download status (downloading/complete/failed) in memory
  4. GET /admin/models/downloads returns current download statuses for all active and recently completed downloads
  5. Concurrent downloads do not block the event loop or starve other background services

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 31-01-PLAN.md — DownloadService, Pydantic models, and unit tests

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 31-02-PLAN.md — DI provider, admin endpoints, lifespan wiring, integration tests

### Phase 32: Dashboard Download Integration

**Goal**: Operators can trigger and monitor model downloads directly from the recommendations table
**Depends on**: Phase 31
**Requirements**: DASH-01, DASH-02, DASH-03
**Success Criteria** (what must be TRUE):

  1. Node detail recommendations table shows a "Download" button for each recommended model
  2. Recommendations table shows an "Already downloaded" badge when a recommended model exists on NFS
  3. Download status (downloading/complete/failed) is visible in the recommendations table and updates without page refresh

**Plans**: 1 plan
Plans:

- [x] 32-01-PLAN.md — Download column, catalog cross-reference, download trigger, status polling

**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 30 -> 31 -> 32

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
| 30. Foundation & Model Catalog | v1.7 | 2/2 | Complete    | 2026-07-28 |
| 31. Download Service & API | v1.7 | 2/2 | Complete    | 2026-07-28 |
| 32. Dashboard Download Integration | v1.7 | 1/1 | Complete   | 2026-07-29 |
