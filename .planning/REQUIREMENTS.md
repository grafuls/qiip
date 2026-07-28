# Requirements: QUADS LLM Inference Proxy

**Defined:** 2026-07-28
**Core Value:** Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## v1.7 Requirements

Requirements for v1.7 HuggingFace Integration. Each maps to roadmap phases.

### Configuration

- [x] **CFG-01**: Operator can configure HuggingFace API token via environment variable for gated model access
- [x] **CFG-02**: Operator can configure the NFS cache directory path where models are stored

### Catalog

- [x] **CAT-01**: Gateway scans NFS cache directory and returns a list of downloaded models with repo IDs
- [x] **CAT-02**: Admin API exposes GET /admin/models/catalog returning all models currently on NFS

### Downloads

- [ ] **DL-01**: Operator can trigger a model download from HuggingFace Hub to NFS via POST /admin/models/download
- [ ] **DL-02**: Gateway tracks download status (downloading/complete/failed) per model in memory
- [ ] **DL-03**: Admin API exposes GET /admin/models/downloads returning current download statuses
- [ ] **DL-04**: Downloads use the configured HF token to access gated models (Llama, Mistral, etc.)

### Dashboard

- [ ] **DASH-01**: Node detail recommendations table shows a download button per recommended model
- [ ] **DASH-02**: Recommendations table shows "already downloaded" badge when a model exists on NFS
- [ ] **DASH-03**: Download status (downloading/complete/failed) is visible in the recommendations table

## Future Requirements

Deferred to future milestone. Tracked but not in current roadmap.

### Filtering & Caching (from v1.6)

- **FILT-01**: Use-case filtering query parameter (coding/chat/reasoning) adjusts scoring weights
- **FILT-02**: Minimum fit level filter (perfect/good/marginal)
- **FILT-03**: Result limit control via query parameter
- **CACHE-01**: Cached recommendations per-host with staleness indicator
- **FLEET-01**: Fleet-wide model compatibility matrix across all nodes

### Download Enhancements

- **DLE-01**: Token validation on startup (warn if invalid/missing)
- **DLE-02**: Model size and file count in catalog entries
- **DLE-03**: Pre-flight auth check for gated models before queuing download
- **DLE-04**: Size estimate displayed before triggering download
- **DLE-05**: Download resumption tracking across gateway restarts

## Out of Scope

| Feature | Reason |
|---------|--------|
| Granular download progress (percentage/bytes) | Added complexity; simple status sufficient for v1.7 |
| Model deletion from NFS via UI | Risky operation; manual NFS management for now |
| Fleet-wide model availability matrix | Requires cached catalog across all nodes |
| Custom model sources (non-HuggingFace) | HuggingFace only for v1.7 |
| Auto-deploy best model without confirmation | Operators must validate model choice |
| Custom scoring engine replacing llmfit | llmfit implements 157+ models — reimplementing is months of work |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CFG-01 | Phase 30 | Complete |
| CFG-02 | Phase 30 | Complete |
| CAT-01 | Phase 30 | Complete |
| CAT-02 | Phase 30 | Complete |
| DL-01 | Phase 31 | Pending |
| DL-02 | Phase 31 | Pending |
| DL-03 | Phase 31 | Pending |
| DL-04 | Phase 31 | Pending |
| DASH-01 | Phase 32 | Pending |
| DASH-02 | Phase 32 | Pending |
| DASH-03 | Phase 32 | Pending |

**Coverage:**
- v1.7 requirements: 11 total
- Mapped to phases: 11
- Unmapped: 0

---
*Requirements defined: 2026-07-28*
*Last updated: 2026-07-28 after roadmap creation*
