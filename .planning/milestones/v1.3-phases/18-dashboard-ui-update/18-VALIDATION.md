---
phase: 18
slug: dashboard-ui-update
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-17
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | DASH-01 | — | N/A | integration | `uv run pytest tests/ -x -q` | TBD | ⬜ pending |
| TBD | TBD | TBD | DASH-02 | — | N/A | integration | `uv run pytest tests/ -x -q` | TBD | ⬜ pending |
| TBD | TBD | TBD | DASH-03 | — | N/A | integration | `uv run pytest tests/ -x -q` | TBD | ⬜ pending |
| TBD | TBD | TBD | DASH-04 | — | N/A | integration | `uv run pytest tests/ -x -q` | TBD | ⬜ pending |
| TBD | TBD | TBD | DASH-05 | — | N/A | integration | `uv run pytest tests/ -x -q` | TBD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual layout of node table columns | DASH-01 | Visual rendering verification | Load dashboard, verify column order: Node ID → GPU Vendor → GPU Model → Endpoint → Model → State → Active Connections → Circuit Breaker → Requests → Actions |
| Action button color coding | DASH-02 | CSS visual verification | Trigger each state, verify button colors match UI-SPEC |
| QUADS status badge display | DASH-04 | Visual + polling verification | Check badge shows connected/stale/unavailable with cache age |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
