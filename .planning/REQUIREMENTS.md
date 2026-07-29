# Requirements: QUADS LLM Inference Proxy

**Defined:** 2026-07-29
**Core Value:** Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## v1.8 Requirements

Requirements for v1.8 Nodes Power Control. Surfaces existing Redfish BMC power management on the node detail dashboard page.

### Power State Display

- [ ] **PWR-01**: Node detail page fetches and displays BMC power state (On/Off/Unknown) as a badge on page load
- [ ] **PWR-02**: Power state badge auto-refreshes after any power action completes

### Power Actions

- [ ] **PWR-03**: Node detail page shows Power On, Force Off, Graceful Restart, and Force Restart action buttons
- [ ] **PWR-04**: Destructive power actions (Force Off, Force Restart) require confirmation before executing
- [ ] **PWR-05**: Power action buttons are context-aware — disabled/hidden based on current power state (e.g. Power On hidden when already on)

## Future Requirements

None identified for this milestone.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Power state on fleet list view | Not needed per user — detail page only |
| Bulk power operations | Not requested for v1.8 |
| Scheduled power management | Future work |
| Power usage/consumption metrics | Out of scope for dashboard |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PWR-01 | — | Pending |
| PWR-02 | — | Pending |
| PWR-03 | — | Pending |
| PWR-04 | — | Pending |
| PWR-05 | — | Pending |

**Coverage:**
- v1.8 requirements: 5 total
- Mapped to phases: 0
- Unmapped: 5

---
*Requirements defined: 2026-07-29*
*Last updated: 2026-07-29 after initial definition*
