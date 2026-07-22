---
phase: 23
slug: auto-power-on-in-provisioner
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-22
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0+ with pytest-asyncio (auto mode) |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/provisioning/test_provisioner.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/provisioning/test_provisioner.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 1 | PWR-05 | — | N/A | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestPowerOnIfNeeded -x` | ❌ W0 | ⬜ pending |
| 23-01-02 | 01 | 1 | PWR-05 | — | N/A | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestWaitForSsh -x` | ❌ W0 | ⬜ pending |
| 23-01-03 | 01 | 1 | PWR-05 | — | N/A | unit | `uv run pytest tests/provisioning/test_provisioner.py::TestProvisionSequence -x` | Modify existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/provisioning/test_provisioner.py::TestPowerOnIfNeeded` — new test class for power-on logic
- [ ] `tests/provisioning/test_provisioner.py::TestWaitForSsh` — new test class for SSH wait loop

*Existing infrastructure covers remaining phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dashboard shows POWERING_ON step | PWR-05 | Requires running dashboard UI | Start provisioning on offline server, verify POWERING_ON appears in dashboard |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
