---
phase: 25
slug: core-models-and-runner
status: active
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-24
---

# Phase 25 — Validation Strategy

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
| 25-01-01 | 01 | 1 | EXEC-03 | — | N/A | import | `python -c "from inference_proxy.models.llmfit import LLMFitResult"` | ❌ W0 | ⬜ pending |
| 25-01-02 | 01 | 1 | EXEC-02 | — | N/A | import | `python -c "from inference_proxy.provisioning.ssh_client import SSHClient"` | ❌ W0 | ⬜ pending |
| 25-02-01 | 02 | 2 | EXEC-01,03 | — | N/A | import | `python -c "from inference_proxy.llmfit.runner import LLMFitRunner"` | ❌ W0 | ⬜ pending |
| 25-02-02 | 02 | 2 | EXEC-01,02,03 | — | N/A | unit | `uv run pytest tests/models/test_llmfit.py tests/llmfit/test_runner.py tests/provisioning/test_ssh_client.py -x -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/models/test_llmfit.py` — stubs for EXEC-01 (Pydantic model parsing)
- [ ] `tests/provisioning/test_ssh_client.py` — extend for EXEC-02 (SSH run method + timeout)
- [ ] `tests/llmfit/test_runner.py` — stubs for EXEC-03 (LLMFitRunner end-to-end)

*Existing test infrastructure (pytest, conftest.py) covers framework setup. Tests created inline in Plan 25-02 Task 2.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSH to real remote host | EXEC-02 | Requires lab network access | SSH to a test host and run `llmfit recommend --json` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
