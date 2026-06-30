---
phase: 08
slug: dashboard-and-node-fleet
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-30
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
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

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | TMPL-01 | — | N/A | unit | `uv run pytest tests/api/test_dashboard.py -x -q` | ❌ W0 | ⬜ pending |
| 08-01-02 | 01 | 1 | DASH-01, DASH-03 | — | N/A | unit | `uv run pytest tests/api/test_dashboard.py -x -q` | ❌ W0 | ⬜ pending |
| 08-01-03 | 01 | 1 | NODE-01, NODE-02 | — | N/A | unit | `uv run pytest tests/api/test_dashboard.py -x -q` | ❌ W0 | ⬜ pending |
| 08-02-01 | 02 | 1 | TMPL-02 | — | N/A | unit | `uv run pytest tests/api/test_dashboard.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/api/test_dashboard.py` — stubs for DASH-01, DASH-03, NODE-01, NODE-02, TMPL-01, TMPL-02

*Existing infrastructure (conftest.py, test_app.py) covers shared fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual badge colors (green/red/yellow) render correctly | NODE-02 | CSS color rendering requires a browser | Open `/dashboard` in browser, verify badge colors match UI-SPEC |
| Simple.css CDN loads and styles page | DASH-03 | External CDN availability | Open `/dashboard` with network panel, verify simple.css loads |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
