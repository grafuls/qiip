---
phase: 12
slug: provisioning-robustness
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-02
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | PROV-06, PROV-07 | — | N/A | unit | `uv run pytest tests/provisioning/test_state.py tests/models/test_node.py -x -q` | ✅ | ⬜ pending |
| 12-01-02 | 01 | 1 | PROV-07 | — | N/A | unit | `uv run pytest tests/resilience/test_health_checker.py -x -q` | ✅ | ⬜ pending |
| 12-02-01 | 02 | 2 | PROV-05 | — | N/A | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestPreflight -x -q` | ✅ | ⬜ pending |
| 12-02-02 | 02 | 2 | PROV-06, PROV-07 | — | N/A | unit | `uv run pytest tests/provisioning/test_provisioner.py -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. Plan 01 creates `tests/provisioning/test_state.py` as part of Task 1. Preflight tests are added to existing `tests/provisioning/test_provisioner.py` in Plan 02 Task 1. No separate Wave 0 needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSH TCP probe to real host | PROV-05 | Requires network access to lab host | `ssh -o ConnectTimeout=5 <host>` returns 0 |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-02
