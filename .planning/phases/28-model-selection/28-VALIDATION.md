---
phase: 28
slug: model-selection
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-26
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 1.4 |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/provisioning/test_provisioner.py tests/models/test_admin.py tests/api/test_admin.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/provisioning/test_provisioner.py tests/models/test_admin.py tests/api/test_admin.py -x -q`
- **After each wave:** Run `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

---

## Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEL-01 | SetupRequest accepts optional model field (None default, str when set) | unit | `python -m pytest tests/models/test_admin.py -x -q` | Exists, needs new tests |
| SEL-01 | POST /admin/nodes/setup accepts model in body | integration | `python -m pytest tests/api/test_admin.py -x -q` | Exists, needs new tests |
| SEL-02 | _run_start_vllm prepends VLLM_MODEL env var when model is set | unit | `python -m pytest tests/provisioning/test_provisioner.py -x -q` | Exists, needs new tests |
| SEL-02 | _run_start_vllm omits VLLM_MODEL when model is None | unit | `python -m pytest tests/provisioning/test_provisioner.py -x -q` | Exists, needs new tests |
| SEL-02 | shlex.quote() sanitizes model string | unit | `python -m pytest tests/provisioning/test_provisioner.py -x -q` | Needs new test |

---

## Wave 0 Gaps

None -- existing test files cover all three modules. New test cases go into existing files.
