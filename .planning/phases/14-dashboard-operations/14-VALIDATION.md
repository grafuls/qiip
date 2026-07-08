---
phase: 14
slug: dashboard-operations
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-08
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-asyncio |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/api/test_dashboard.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/api/test_dashboard.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | 01 | 1 | DASH-01 | integration | `uv run pytest tests/api/test_dashboard.py -x -q` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | DASH-02 | integration | `uv run pytest tests/api/test_dashboard.py -x -q` | ❌ W0 | ⬜ pending |
| TBD | 02 | 1 | DASH-03 | integration | `uv run pytest tests/api/test_dashboard.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/api/test_dashboard.py` — extend existing dashboard tests for setup form, teardown button, tasks panel
