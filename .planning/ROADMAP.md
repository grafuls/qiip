# Roadmap: QUADS LLM Inference Proxy

## Milestones

- SHIPPED **v1.0 MVP** -- Phases 1-6 (shipped 2026-06-25)
- IN PROGRESS **v1.1 Web UI** -- Phases 7-9

## Phases

<details>
<summary>v1.0 MVP (Phases 1-6) -- SHIPPED 2026-06-25</summary>

- [x] **Phase 1: Foundation** - Project scaffolding, config, data models, and test infrastructure (3/3 plans) -- completed 2026-06-11
- [x] **Phase 2: Service Discovery** - etcd-based node registry with watch-based live updates (2/2 plans) -- completed 2026-06-11
- [x] **Phase 3: Request Proxying and Streaming** - OpenAI-compatible proxy with SSE streaming to vLLM nodes (2/2 plans) -- completed 2026-06-12
- [x] **Phase 4: Intelligent Routing** - Least-connections load balancing with model-aware filtering (2/2 plans) -- completed 2026-06-24
- [x] **Phase 5: Resilience** - Health checks, retry with failover, circuit breaker, graceful shutdown (2/2 plans) -- completed 2026-06-25
- [x] **Phase 6: Observability and Admin** - Structured logging and admin API for operational visibility (2/2 plans) -- completed 2026-06-25

</details>

### v1.1 Web UI

- [ ] **Phase 7: Request Metrics and Admin API** - In-memory request counters and enriched admin endpoint for node data
- [ ] **Phase 8: Dashboard and Node Fleet** - Jinja2-rendered operations dashboard with node fleet table and styling
- [ ] **Phase 9: Live Metrics and Auto-Refresh** - Request metrics display and JS polling for automatic dashboard updates

## Phase Details

### Phase 7: Request Metrics and Admin API

**Goal**: Operators can query enriched node data and the gateway tracks request volume
**Depends on**: Phase 6 (admin API exists)
**Requirements**: METR-01, METR-03
**Success Criteria** (what must be TRUE):

  1. Gateway increments request counters per-node and per-model on every proxied request
  2. GET /admin/nodes returns active_connections and circuit_breaker_state for each node
  3. Counter data is accessible programmatically (exists in a form the dashboard can consume)

**Plans**: 2 plans
Plans:
**Wave 1**

- [x] 07-01-PLAN.md — RequestMetrics class, CircuitBreaker.state property, admin model enrichment

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 07-02-PLAN.md — DI wiring, counter increments in routes, enriched admin endpoints, tests

### Phase 8: Dashboard and Node Fleet

**Goal**: Operators can view the node fleet status at a glance on a single web page
**Depends on**: Phase 7 (enriched node data available)
**Requirements**: DASH-01, DASH-03, NODE-01, NODE-02, TMPL-01, TMPL-02
**Success Criteria** (what must be TRUE):

  1. Navigating to the dashboard URL shows a single page with a node fleet table
  2. Node table displays node_id, endpoint, model, status, active connections, and circuit breaker state for every registered node
  3. Healthy, unhealthy, and draining nodes are visually distinguishable (color, icon, or badge)
  4. Dashboard is served by the existing FastAPI app with no separate server process
  5. Page has readable CSS styling (not unstyled HTML)

**Plans**: 2 plans
Plans:

- [ ] 07-01-PLAN.md — RequestMetrics class, CircuitBreaker.state property, admin model enrichment
- [ ] 07-02-PLAN.md — DI wiring, counter increments in routes, enriched admin endpoints, tests

**UI hint**: yes

### Phase 9: Live Metrics and Auto-Refresh

**Goal**: Dashboard shows request volume and stays current without manual refresh
**Depends on**: Phase 8 (dashboard page exists)
**Requirements**: METR-02, DASH-02
**Success Criteria** (what must be TRUE):

  1. Dashboard displays request counts broken down by node
  2. Dashboard content updates automatically at a configurable polling interval without full page reload
  3. Operator can see counts change in real time as requests flow through the proxy

**Plans**: 2 plans
Plans:

- [ ] 07-01-PLAN.md — RequestMetrics class, CircuitBreaker.state property, admin model enrichment
- [ ] 07-02-PLAN.md — DI wiring, counter increments in routes, enriched admin endpoints, tests

**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 7 -> 8 -> 9

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-06-11 |
| 2. Service Discovery | v1.0 | 2/2 | Complete | 2026-06-11 |
| 3. Request Proxying and Streaming | v1.0 | 2/2 | Complete | 2026-06-12 |
| 4. Intelligent Routing | v1.0 | 2/2 | Complete | 2026-06-24 |
| 5. Resilience | v1.0 | 2/2 | Complete | 2026-06-25 |
| 6. Observability and Admin | v1.0 | 2/2 | Complete | 2026-06-25 |
| 7. Request Metrics and Admin API | v1.1 | 1/2 | In Progress|  |
| 8. Dashboard and Node Fleet | v1.1 | 0/0 | Not started | - |
| 9. Live Metrics and Auto-Refresh | v1.1 | 0/0 | Not started | - |
