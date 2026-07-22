---
phase: 22
slug: power-management-endpoints
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-22
---

# Phase 22 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 22-01-01 | 01 | 1 | PWR-01 | — | N/A | unit | `uv run pytest tests/test_power.py -k test_power_on` | ❌ W0 | ⬜ pending |
| 22-01-02 | 01 | 1 | PWR-02 | — | N/A | unit | `uv run pytest tests/test_power.py -k test_power_off` | ❌ W0 | ⬜ pending |
| 22-01-03 | 01 | 1 | PWR-03 | — | N/A | unit | `uv run pytest tests/test_power.py -k test_restart` | ❌ W0 | ⬜ pending |
| 22-01-04 | 01 | 1 | PWR-04 | — | N/A | unit | `uv run pytest tests/test_power.py -k test_get_power_state` | ❌ W0 | ⬜ pending |
| 22-01-05 | 01 | 1 | PWR-01 | — | 503 when unconfigured | unit | `uv run pytest tests/test_power.py -k test_redfish_not_configured` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_power.py` — stubs for PWR-01, PWR-02, PWR-03, PWR-04

*Existing infrastructure covers shared fixtures and conftest.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
