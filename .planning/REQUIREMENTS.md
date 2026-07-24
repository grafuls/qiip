# Requirements: QUADS LLM Inference Proxy

**Defined:** 2026-07-24
**Core Value:** Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## v1.6 Requirements

Requirements for v1.6 LLMFit for Best Fit Models. Each maps to roadmap phases.

### Installation

- [ ] **INST-01**: llmfit binary is installed on target servers during provisioning via prebuilt binary download
- [ ] **INST-02**: llmfit installation is a non-fatal provisioning step (failure doesn't block setup)

### Execution

- [ ] **EXEC-01**: Gateway can run `llmfit recommend --json` on a remote host via SSH and parse the JSON output
- [ ] **EXEC-02**: SSH command execution has timeout protection to prevent hangs
- [ ] **EXEC-03**: Pydantic models validate llmfit JSON output (system hardware info + ranked model list)

### API

- [ ] **API-01**: Admin API endpoint `GET /admin/nodes/{hostname}/recommendations` returns ranked model recommendations
- [ ] **API-02**: Endpoint returns detected hardware info (GPU VRAM, GPU name, backend) alongside recommendations
- [ ] **API-03**: llmfit failures return structured error response (not 500)

### Model Selection

- [ ] **SEL-01**: SetupRequest accepts optional model field for operator-selected model
- [ ] **SEL-02**: Provisioner passes `VLLM_MODEL` env var to `start-vllm.sh` when model is specified

### Dashboard

- [ ] **DASH-01**: Node detail page shows a recommendations card with ranked model table (name, score, fit level, estimated tok/s, memory)
- [ ] **DASH-02**: Recommendations card includes hardware summary (detected GPU, VRAM, backend)

## Future Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Filtering & Caching

- **FILT-01**: Use-case filtering query parameter (coding/chat/reasoning) adjusts scoring weights
- **FILT-02**: Minimum fit level filter (perfect/good/marginal)
- **FILT-03**: Result limit control via query parameter
- **CACHE-01**: Cached recommendations per-host with staleness indicator
- **FLEET-01**: Fleet-wide model compatibility matrix across all nodes

## Out of Scope

| Feature | Reason |
|---------|--------|
| Auto-deploy best model without confirmation | Operators must validate model choice against team needs, licensing, org policy |
| Custom scoring engine replacing llmfit | llmfit implements 157+ models, dynamic quantization, MoE support — reimplementing is months of work |
| Persistent recommendation history database | Adds storage dependency for ephemeral data — hardware is constant per server |
| llmfit REST API server on each node | Process management burden; on-demand SSH is simpler |
| Model downloading/pulling from gateway | Models live on NFS shared storage; weight management is separate |
| Non-vLLM runtime support | Gateway exclusively manages vLLM nodes |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INST-01 | TBD | Pending |
| INST-02 | TBD | Pending |
| EXEC-01 | TBD | Pending |
| EXEC-02 | TBD | Pending |
| EXEC-03 | TBD | Pending |
| API-01 | TBD | Pending |
| API-02 | TBD | Pending |
| API-03 | TBD | Pending |
| SEL-01 | TBD | Pending |
| SEL-02 | TBD | Pending |
| DASH-01 | TBD | Pending |
| DASH-02 | TBD | Pending |

**Coverage:**
- v1.6 requirements: 12 total
- Mapped to phases: 0
- Unmapped: 12 ⚠️

---
*Requirements defined: 2026-07-24*
*Last updated: 2026-07-24 after initial definition*
