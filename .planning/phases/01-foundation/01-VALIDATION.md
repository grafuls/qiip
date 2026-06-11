---
phase: 1
slug: foundation
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest -x -q` |
| **Full suite command** | `uv run pytest --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -x -q`
- **After every plan wave:** Run `uv run pytest --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | — | — | N/A | unit | `uv run pytest tests/ -x -v` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 2 | — | — | N/A | unit | `uv run pytest tests/config/test_settings.py -x -v` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 2 | — | — | N/A | unit | `uv run pytest tests/models/test_node.py -x -v` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | — | — | N/A | unit | `uv run pytest tests/models/test_openai.py -x -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures
- [ ] `tests/models/test_openai.py` — stubs for OpenAI schema validation
- [ ] `tests/models/test_node.py` — stubs for node state model validation
- [ ] `tests/config/test_settings.py` — stubs for configuration validation
- [ ] pytest + pytest-asyncio installed via pyproject.toml

*Test infrastructure is established as part of Phase 1 itself.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `uv run uvicorn` starts and listens | Success Criteria 2 | Server startup is a system-level check | Run `uv run uvicorn inference_proxy.main:app --host 0.0.0.0 --port 8000` and verify HTTP response |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-11
