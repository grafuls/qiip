---
phase: 27
slug: admin-api-endpoint
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-26
---

# Phase 27 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 1.4 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/api/test_admin.py -x -q` |
| **Full suite command** | `uv run pytest -x -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/api/test_admin.py -x -q`
- **After every plan wave:** Run `uv run pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 27-01-01 | 01 | 1 | API-01 | — | N/A | integration | `uv run pytest tests/api/test_admin.py::TestRecommendations::test_returns_200_with_models -x` | ❌ W0 | ⬜ pending |
| 27-01-02 | 01 | 1 | API-01 | — | N/A | integration | `uv run pytest tests/api/test_admin.py::TestRecommendations::test_response_includes_hostname -x` | ❌ W0 | ⬜ pending |
| 27-01-03 | 01 | 1 | API-02 | — | N/A | integration | `uv run pytest tests/api/test_admin.py::TestRecommendations::test_response_includes_hardware -x` | ❌ W0 | ⬜ pending |
| 27-01-04 | 01 | 1 | API-03 | T-27-01 | Raw output NOT in API response (D-01) | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_timeout_returns_502 -x` | ❌ W0 | ⬜ pending |
| 27-01-05 | 01 | 1 | API-03 | T-27-02 | Raw output NOT in API response (D-01) | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_parse_error_returns_502 -x` | ❌ W0 | ⬜ pending |
| 27-01-06 | 01 | 1 | API-03 | T-27-03 | SSH errors mapped to 502 not 500 | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_ssh_error_returns_502 -x` | ❌ W0 | ⬜ pending |
| 27-01-07 | 01 | 1 | API-03 | T-27-03 | SSH errors mapped to 502 not 500 | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_command_error_returns_502 -x` | ❌ W0 | ⬜ pending |
| 27-01-08 | 01 | 1 | D-01 | T-27-02 | Raw output stays in logs only | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_raw_output_not_exposed -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/api/test_admin.py` — add TestRecommendations + TestRecommendationErrors classes (file exists, classes are new)
- [ ] `tests/conftest.py` — add mock_llmfit_runner fixture + app fixture wiring

*Existing test infrastructure covers framework install.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
