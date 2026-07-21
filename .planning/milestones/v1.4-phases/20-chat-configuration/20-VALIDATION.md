---
phase: 20
slug: chat-configuration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-21
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with FastAPI TestClient |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/api/test_chat.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/api/test_chat.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 20-01-01 | 01 | 1 | CFG-01 | — | N/A | unit | `uv run pytest tests/api/test_chat.py -x -k system_prompt` | ❌ W0 | ⬜ pending |
| 20-01-02 | 01 | 1 | CFG-01 | — | N/A | unit | `uv run pytest tests/api/test_chat.py -x -k toggle` | ❌ W0 | ⬜ pending |
| 20-01-03 | 01 | 1 | CFG-01 | — | N/A | unit | `uv run pytest tests/api/test_chat.py -x -k panel` | ❌ W0 | ⬜ pending |
| 20-01-04 | 01 | 1 | CFG-02 | — | N/A | manual | Visual spot-check in both themes | Manual only | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/api/test_chat.py` — new test methods for system-prompt textarea, toggle button, panel div, aria attributes

*Existing infrastructure covers framework and fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dark/light mode consistency | CFG-02 | CSS color audit requires visual inspection | Toggle theme in browser, verify system prompt panel colors match surrounding elements in both modes |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
