---
phase: 13
slug: teardown-and-admin-api
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-07
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` |
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
| TBD | 01 | 1 | TEAR-01 | — | N/A | unit | `uv run pytest tests/test_provisioner.py -x -q` | ❌ W0 | ⬜ pending |
| TBD | 01 | 1 | TEAR-02 | — | N/A | unit | `uv run pytest tests/test_provisioner.py -x -q` | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | API-01 | — | N/A | integration | `uv run pytest tests/test_admin.py -x -q` | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | API-02 | — | N/A | integration | `uv run pytest tests/test_admin.py -x -q` | ❌ W0 | ⬜ pending |
| TBD | 02 | 2 | API-03 | — | N/A | integration | `uv run pytest tests/test_admin.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_provisioner.py` — teardown method tests (TEAR-01, TEAR-02)
- [ ] `tests/test_admin.py` — admin API endpoint tests (API-01, API-02, API-03)

*Existing test infrastructure covers framework installation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SSH container stop on remote host | TEAR-01 | Requires live SSH to remote host | SSH to host, run `podman ps`, verify container stopped |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
