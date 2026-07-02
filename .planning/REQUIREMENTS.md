# Requirements: QUADS LLM Inference Proxy

**Defined:** 2026-07-01
**Core Value:** Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## v1.2 Requirements

Requirements for milestone v1.2 Node Setup. Each maps to roadmap phases.

### Script Hardening

- [x] **SCRIPT-01**: setup.sh exits on first error (set -e) and validates prerequisites before starting
- [x] **SCRIPT-02**: setup.sh steps are idempotent (re-running skips already-completed steps)
- [x] **SCRIPT-03**: NFS mount uses timeout options to prevent indefinite hangs
- [x] **SCRIPT-04**: start-vllm.sh runs vLLM container detached (podman run -d) with --replace for name collisions

### Provisioning

- [x] **PROV-01**: Gateway can SSH into a host via asyncssh using pre-configured keys
- [x] **PROV-02**: Gateway runs setup.sh remotely (NVIDIA drivers, NFS, container toolkit)
- [x] **PROV-03**: Gateway builds and starts vLLM container on remote host with GPU auto-detection
- [x] **PROV-04**: Gateway polls remote /health endpoint until vLLM is ready, then registers in etcd
- [ ] **PROV-05**: Pre-flight validation checks SSH reachable, GPU present, and disk space before setup
- [ ] **PROV-06**: Setup tracks per-step progress via a state machine (PENDING → steps → COMPLETE/FAILED)
- [ ] **PROV-07**: PROVISIONING node status prevents health checker from marking node unhealthy during setup

### Teardown

- [ ] **TEAR-01**: Operator can teardown a node: drain connections, SSH stop container, deregister from etcd
- [ ] **TEAR-02**: Force teardown option skips connection drain and immediately stops/deregisters

### Admin API

- [ ] **API-01**: POST /admin/nodes/setup accepts hostname, returns 202 with task ID
- [ ] **API-02**: GET /admin/provisioning/tasks returns status of all setup/teardown operations
- [ ] **API-03**: DELETE /admin/nodes/{id} triggers graceful or forced teardown

### Dashboard

- [ ] **DASH-01**: Dashboard has a setup form where operator enters hostname and triggers setup
- [ ] **DASH-02**: Each node row has a teardown button
- [ ] **DASH-03**: Dashboard displays setup/teardown progress with per-step status

## Future Requirements

### Enhanced Provisioning

- **PROV-08**: Parallel multi-node setup from a list of hostnames
- **PROV-09**: Setup profiles/presets for different GPU configurations
- **PROV-10**: Persistent setup history with audit trail

### Enhanced Dashboard

- **DASH-04**: WebSocket live log streaming during setup
- **DASH-05**: Node management page (restart, update model, view logs)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-scaling (auto-provision on load) | Explicitly deferred per PROJECT.md |
| Model override at setup time | GPU auto-detection sufficient for v1.2 |
| Container image caching/registry | Minor optimization, add when setup time matters |
| Multi-gateway coordination | Single-instance for v1.2; etcd locking when multi-instance needed |
| Ansible/Terraform integration | asyncssh is sufficient for direct SSH; no orchestration framework needed |
| Persistent metrics storage | In-memory counters only per v1.1 decision |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SCRIPT-01 | Phase 10 | Complete |
| SCRIPT-02 | Phase 10 | Complete |
| SCRIPT-03 | Phase 10 | Complete |
| SCRIPT-04 | Phase 10 | Complete |
| PROV-01 | Phase 11 | Complete |
| PROV-02 | Phase 11 | Complete |
| PROV-03 | Phase 11 | Complete |
| PROV-04 | Phase 11 | Complete |
| PROV-05 | Phase 12 | Pending |
| PROV-06 | Phase 12 | Pending |
| PROV-07 | Phase 12 | Pending |
| TEAR-01 | Phase 13 | Pending |
| TEAR-02 | Phase 13 | Pending |
| API-01 | Phase 13 | Pending |
| API-02 | Phase 13 | Pending |
| API-03 | Phase 13 | Pending |
| DASH-01 | Phase 14 | Pending |
| DASH-02 | Phase 14 | Pending |
| DASH-03 | Phase 14 | Pending |

**Coverage:**
- v1.2 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0

---
*Requirements defined: 2026-07-01*
*Last updated: 2026-07-01 after roadmap creation*
