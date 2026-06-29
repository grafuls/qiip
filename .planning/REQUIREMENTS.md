# Requirements: QUADS LLM Inference Proxy

**Defined:** 2026-06-29
**Core Value:** Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## v1.1 Requirements

Requirements for milestone v1.1 Web UI. Each maps to roadmap phases.

### Dashboard

- [ ] **DASH-01**: Operator can view a single-page dashboard showing node fleet and request counts
- [ ] **DASH-02**: Dashboard auto-refreshes via JS polling at a configurable interval
- [ ] **DASH-03**: Dashboard is served from the same FastAPI app (no separate server)

### Node Fleet

- [ ] **NODE-01**: Operator can see all nodes in a table with node_id, endpoint, model, status, active connections, and circuit breaker state
- [ ] **NODE-02**: Node table visually distinguishes healthy, unhealthy, and draining nodes

### Metrics

- [ ] **METR-01**: Gateway tracks total request count, per-model count, and per-node count in memory
- [ ] **METR-02**: Operator can see request counts on the dashboard, broken down by node
- [ ] **METR-03**: Admin API `/admin/nodes` extended with active_connections and circuit_breaker_state fields

### Templates

- [ ] **TMPL-01**: Dashboard uses Jinja2 templates rendered by FastAPI
- [ ] **TMPL-02**: Dashboard has basic CSS styling (readable, functional — no design system needed)

## Future Requirements

### Enhanced Metrics

- **METR-04**: Latency stats (average, p95) per request
- **METR-05**: Error rate percentage per node and model

### Dashboard Enhancements

- **DASH-04**: Historical trend charts for traffic and errors over time
- **DASH-05**: Live activity feed showing requests flowing through the proxy

## Out of Scope

| Feature | Reason |
|---------|--------|
| Separate SPA / JS build step | Jinja2 + vanilla JS keeps things simple, no Node.js toolchain |
| Persistent metrics storage | In-memory counters only; Prometheus/Grafana is a future concern |
| User authentication on dashboard | Internal network only, same as v1.0 |
| Node management via UI | Read-only dashboard; node management is out of scope for v1.1 |
| WebSocket/SSE live updates | Polling is sufficient for an ops dashboard |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DASH-01 | Phase 8 | Pending |
| DASH-02 | Phase 9 | Pending |
| DASH-03 | Phase 8 | Pending |
| NODE-01 | Phase 8 | Pending |
| NODE-02 | Phase 8 | Pending |
| METR-01 | Phase 7 | Pending |
| METR-02 | Phase 9 | Pending |
| METR-03 | Phase 7 | Pending |
| TMPL-01 | Phase 8 | Pending |
| TMPL-02 | Phase 8 | Pending |

**Coverage:**
- v1.1 requirements: 10 total
- Mapped to phases: 10
- Unmapped: 0

---
*Requirements defined: 2026-06-29*
*Last updated: 2026-06-29 after roadmap creation*
