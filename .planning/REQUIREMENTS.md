# Requirements: QUADS LLM Inference Proxy

**Defined:** 2026-07-29
**Core Value:** Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## v1.9 Requirements

Requirements for v1.9 Model Selection in Node Setup. Adds a model selector to the node detail page so operators choose which downloaded model to deploy when setting up a node.

### Model Selection

- [ ] **MDL-01**: Node detail page shows a model selector dropdown populated from GET /admin/models/catalog (downloaded models on NFS)
- [ ] **MDL-02**: Setup action on node detail page sends the selected model in the SetupRequest.model field
- [ ] **MDL-03**: Setup button on node detail page is disabled when no models are downloaded (catalog is empty)

## Future Requirements

None identified for this milestone.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Dashboard fleet view model selector | User decided: fleet Setup button keeps current behavior |
| Manual setup form model selector | Not requested — node detail page only |
| Model upload/push to NFS | Separate from model selection |
| Model deletion from NFS | Not requested for v1.9 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MDL-01 | Phase 35 | Pending |
| MDL-02 | Phase 35 | Pending |
| MDL-03 | Phase 35 | Pending |

**Coverage:**
- v1.9 requirements: 3 total
- Mapped to phases: 3
- Unmapped: 0

---
*Requirements defined: 2026-07-29*
