# Roadmap: QUADS LLM Inference Proxy

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-06-25)
- ✅ **v1.1 Web UI** — Phases 7-9 (shipped 2026-07-01)
- ✅ **v1.2 Node Setup** — Phases 10-14 (shipped 2026-07-08)
- ✅ **v1.3 QUADS Integration** — Phases 15-18 (shipped 2026-07-20)
- 🚧 **v1.4 Chatbot Playground** — Phases 19-20 (in progress)

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

### v1.4 Chatbot Playground (In Progress)

**Milestone Goal:** Add a chat page where users can converse with any healthy inference endpoint through the existing proxy.

- [ ] **Phase 19: Chat Page and Streaming** - Core chat UI with message input, SSE streaming responses, and model selection
- [ ] **Phase 20: Chat Configuration** - System prompt setting and dark/light mode consistency

## Phase Details

### Phase 19: Chat Page and Streaming

**Goal**: Users can have a conversation with any healthy inference model through the browser
**Depends on**: Phase 18 (existing dashboard, proxy endpoints)
**Requirements**: CHAT-01, CHAT-02, CHAT-03
**Success Criteria** (what must be TRUE):

  1. User can navigate to the chat page from the dashboard
  2. User can type a message and receive a response from a healthy inference endpoint
  3. User can see tokens appear incrementally as the model generates its response (real-time streaming)
  4. User can select which model to chat with from available healthy models
  5. Conversation history is visible in the chat area and persists within the browser session

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 19-01-PLAN.md — Chat page structure, server wiring, template, CSS, and tests

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 19-02-PLAN.md — Chat streaming interaction (chat.js: SSE, model selector, markdown, auto-scroll)

**UI hint**: yes

### Phase 20: Chat Configuration

**Goal**: Users can customize chat behavior and appearance
**Depends on**: Phase 19
**Requirements**: CFG-01, CFG-02
**Success Criteria** (what must be TRUE):

  1. User can set a system prompt that is included with every request to the model
  2. Chat page follows the same dark/light mode toggle as the existing dashboard
  3. System prompt persists across messages within the same session

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
| 15. QUADS Client and Models | v1.3 | 1/1 | Complete | 2026-07-16 |
| 16. Background Polling | v1.3 | 1/1 | Complete | 2026-07-16 |
| 17. Unified Node List and Admin API | v1.3 | 1/1 | Complete | 2026-07-16 |
| 18. Dashboard UI Update | v1.3 | 2/2 | Complete | 2026-07-17 |
| 19. Chat Page and Streaming | v1.4 | 1/2 | In Progress|  |
| 20. Chat Configuration | v1.4 | 0/? | Not started | - |
