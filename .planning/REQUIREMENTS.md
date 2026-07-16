# Requirements: QUADS LLM Inference Proxy

**Defined:** 2026-07-15
**Core Value:** Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## v1.3 Requirements

Requirements for QUADS Integration milestone. Each maps to roadmap phases.

### QUADS Client & Discovery

- [x] **QUADS-01**: Gateway can connect to a configurable QUADS REST API and retrieve the list of all hosts
- [x] **QUADS-02**: Gateway polls QUADS periodically in the background with configurable interval and in-memory caching
- [x] **QUADS-03**: Gateway filters QUADS hosts to only those with GPU processors (processor_type=GPU)
- [x] **QUADS-04**: Gateway normalizes hostnames to a canonical format for matching QUADS FQDNs with etcd short names

### Unified Node List

- [ ] **NODES-01**: Admin API returns a unified node list merging QUADS available hosts with etcd-registered nodes by hostname
- [ ] **NODES-02**: Each node in the unified list shows its state (available, provisioned, healthy, unhealthy) with available actions
- [ ] **NODES-03**: User can trigger Setup on an available node, Teardown on a healthy node, and Teardown+Retry on an unhealthy node via inline actions
- [ ] **NODES-04**: Gateway prevents duplicate setup requests for the same host with a pending_hosts guard (409 on duplicate)
- [ ] **NODES-05**: Gateway re-validates host availability against QUADS at setup time, not from the polling cache

### Dashboard UI

- [ ] **DASH-01**: Dashboard displays a single unified table showing all nodes across all states (available, provisioned, healthy, unhealthy)
- [ ] **DASH-02**: Dashboard shows inline action buttons per node based on current state
- [ ] **DASH-03**: Standalone setup form is removed, replaced by inline controls with a collapsed manual hostname fallback
- [ ] **DASH-04**: Dashboard shows QUADS connection status indicator (connected/stale/unavailable) with cache age
- [ ] **DASH-05**: Dashboard shows GPU hardware info (vendor, model) per host inline in the node list

## Future Requirements

Deferred to future release. Tracked but not in current roadmap.

### Extended QUADS Integration

- **QUADS-F01**: Cloud/assignment tooltip showing which team owns a non-available host
- **QUADS-F02**: Current schedule details per host from /api/v3/schedules/current
- **QUADS-F03**: Write operations to QUADS API (reserve/release hosts)

### Advanced UI

- **DASH-F01**: Per-host detail page with full hardware specs and provisioning history
- **DASH-F02**: Filter and search across unified node list
- **DASH-F03**: Sort by state, hostname, GPU model, or connection count

### Automation

- **AUTO-F01**: Auto-provisioning of available GPU hosts based on demand
- **AUTO-F02**: Auto-teardown of idle provisioned nodes after configurable timeout

## Out of Scope

| Feature | Reason |
|---------|--------|
| QUADS write operations | Gateway is a consumer, not a QUADS admin |
| Auto-provisioning | Dangerous scope creep — operators should decide which hosts to provision |
| Real-time QUADS sync | QUADS has no push/webhook mechanism; polling suffices |
| QUADS v2 (MongoDB) support | Pin to v3 API; v2 response format differs significantly |
| Authentication for QUADS API | GET endpoints are unauthenticated; write endpoints not used |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| QUADS-01 | Phase 15 | Complete |
| QUADS-02 | Phase 16 | Complete |
| QUADS-03 | Phase 15 | Complete |
| QUADS-04 | Phase 15 | Complete |
| NODES-01 | Phase 17 | Pending |
| NODES-02 | Phase 17 | Pending |
| NODES-03 | Phase 17 | Pending |
| NODES-04 | Phase 17 | Pending |
| NODES-05 | Phase 17 | Pending |
| DASH-01 | Phase 18 | Pending |
| DASH-02 | Phase 18 | Pending |
| DASH-03 | Phase 18 | Pending |
| DASH-04 | Phase 18 | Pending |
| DASH-05 | Phase 18 | Pending |

**Coverage:**
- v1.3 requirements: 14 total
- Mapped to phases: 14
- Unmapped: 0

---
*Requirements defined: 2026-07-15*
*Last updated: 2026-07-15 after roadmap creation*
