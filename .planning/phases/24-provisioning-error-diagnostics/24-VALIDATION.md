---
phase: 24
slug: provisioning-error-diagnostics
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-22
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-asyncio |
| **Config file** | `pyproject.toml` |
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
| 24-01-01 | 01 | 1 | DIAG-01 | — | N/A | unit | `uv run pytest tests/provisioning/ -x -q` | ❌ W0 | ⬜ pending |
| 24-01-02 | 01 | 1 | DIAG-01 | — | N/A | unit | `uv run pytest tests/provisioning/ -x -q` | ❌ W0 | ⬜ pending |
| 24-01-03 | 01 | 1 | DIAG-02 | — | N/A | unit | `uv run pytest tests/api/ -x -q` | ❌ W0 | ⬜ pending |
| 24-01-04 | 01 | 2 | DIAG-02 | — | N/A | unit | `uv run pytest tests/ -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Test stubs for DIAG-01 (error capture) and DIAG-02 (dashboard display)

*Existing infrastructure covers test framework requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Expandable sub-row in dashboard | DIAG-02 | UI interaction (click-to-expand) | Open dashboard, trigger provisioning failure, verify badge + expandable row |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
