---
phase: 9
slug: live-metrics-and-auto-refresh
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-01
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 1.4 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/api/test_dashboard.py tests/config/test_settings.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/api/test_dashboard.py tests/config/test_settings.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | METR-02 | — | N/A | unit | `uv run pytest tests/api/test_dashboard.py -x -k requests` | Extends existing | ⬜ pending |
| 09-01-02 | 01 | 1 | DASH-02 | — | N/A | unit | `uv run pytest tests/config/test_settings.py -x -k dashboard` | New test | ⬜ pending |
| 09-01-03 | 01 | 1 | DASH-02 | — | N/A | unit | `uv run pytest tests/api/test_dashboard.py -x -k poll` | New test | ⬜ pending |
| 09-01-04 | 01 | 1 | METR-02 | — | N/A | unit | `uv run pytest tests/api/test_admin.py -x -k metrics` | Exists (passes) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Polling updates visible in browser | DASH-02 | Visual verification of live updates | Open dashboard, start traffic, observe counts incrementing every 10s |
| Last-updated timestamp refreshes | DASH-02 | Visual verification of timestamp | Watch "Last updated" time change on each poll cycle |
| Poll failure warning appears | DASH-02 | Requires simulated network failure | Stop server, observe warning; restart, observe recovery |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
