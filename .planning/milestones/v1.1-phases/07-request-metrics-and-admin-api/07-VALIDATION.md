---
phase: 07
slug: request-metrics-and-admin-api
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-29
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-asyncio |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | METR-01 | — | N/A | unit | `uv run pytest tests/routing/test_request_metrics.py -x -q` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | METR-03 | — | N/A | unit | `uv run pytest tests/resilience/test_circuit_breaker.py -x -q` | ✅ | ⬜ pending |
| 07-02-01 | 02 | 2 | METR-01 | — | N/A | unit | `uv run pytest tests/api/test_routes.py -x -q` | ✅ | ⬜ pending |
| 07-02-02 | 02 | 2 | METR-03 | — | N/A | unit | `uv run pytest tests/api/test_admin.py -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Plan 01 Task 1 (TDD) creates tests/routing/test_request_metrics.py as part of its red-green cycle — no separate Wave 0 needed.*

*Existing infrastructure covers admin API and route handler testing.*

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
