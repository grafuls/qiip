---
phase: 15
slug: quads-client-and-models
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-16
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 1.4 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/quads/ tests/models/test_quads.py -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/quads/ tests/models/test_quads.py -x -q`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | QUADS-01 | T-15-01 / SSRF | base_url from env vars only | unit | `uv run pytest tests/quads/test_client.py::TestGetHosts -x` | ❌ W0 | ⬜ pending |
| 15-01-02 | 01 | 1 | QUADS-01 | — | N/A | unit | `uv run pytest tests/config/test_settings.py::TestQUADSSettings -x` | ❌ W0 | ⬜ pending |
| 15-01-03 | 01 | 1 | QUADS-03 | T-15-02 / Tampering | Pydantic validation with extra="ignore" | unit | `uv run pytest tests/quads/test_client.py::TestGPUFilter -x` | ❌ W0 | ⬜ pending |
| 15-01-04 | 01 | 1 | QUADS-04 | — | N/A | unit | `uv run pytest tests/quads/test_client.py::TestCanonicalHostname -x` | ❌ W0 | ⬜ pending |
| 15-01-05 | 01 | 1 | D-06 | — | N/A | unit | `uv run pytest tests/quads/test_client.py::TestBrokenRetiredFilter -x` | ❌ W0 | ⬜ pending |
| 15-01-06 | 01 | 1 | D-08 | — | N/A | unit | `uv run pytest tests/quads/test_client.py::TestGetAvailable -x` | ❌ W0 | ⬜ pending |
| 15-01-07 | 01 | 1 | D-09 | T-15-03 / DoS | QUADSConnectionError raised | unit | `uv run pytest tests/quads/test_client.py::TestConnectionError -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/quads/__init__.py` — package init
- [ ] `tests/quads/test_client.py` — QUADSClient unit tests with pytest-httpx
- [ ] `tests/models/test_quads.py` — QUADSHost model tests

*Existing infrastructure covers all other phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live QUADS API connectivity | QUADS-01 | Requires access to deployed QUADS instance | `curl https://<quads-url>/api/v3/hosts` returns JSON array |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
