---
phase: 11
slug: ssh-provisioning
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-01
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | PROV-01 | — | SSH key auth only, no passwords | unit | `uv run pytest tests/provisioning/test_ssh_client.py -x` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | PROV-02 | — | stdout/stderr separation, step marker parsing | unit | `uv run pytest tests/provisioning/test_ssh_client.py -x` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 2 | PROV-03 | — | GPU auto-detection via start-vllm.sh | integration | `uv run pytest tests/provisioning/test_provisioner.py -x` | ❌ W0 | ⬜ pending |
| 11-02-02 | 02 | 2 | PROV-04 | — | Health poll + etcd registration with correct format | integration | `uv run pytest tests/provisioning/test_provisioner.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/provisioning/test_ssh_client.py` — stubs for PROV-01, PROV-02
- [ ] `tests/provisioning/test_provisioner.py` — stubs for PROV-03, PROV-04
- [ ] `tests/provisioning/__init__.py` — package init
- [ ] `asyncssh` — new dependency to add to pyproject.toml

*Existing test infrastructure (pytest, pytest-asyncio, pytest-httpx) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSH to real lab host | PROV-01 | Requires live lab server with SSH access | Connect to a lab host, verify key-based auth succeeds |
| Full setup.sh execution | PROV-02 | 10+ min runtime, requires GPU host | Run provisioner against a host with GPUs, verify all steps complete |
| vLLM container health | PROV-04 | Requires running vLLM with GPU | After container starts, verify /health returns 200 within timeout |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
