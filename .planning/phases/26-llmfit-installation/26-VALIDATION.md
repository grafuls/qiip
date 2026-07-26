---
phase: 26
slug: llmfit-installation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-26
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/provisioning/test_state.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/provisioning/test_state.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 26-01-01 | 01 | 1 | INST-01, INST-02 | syntax + grep | `bash -n auto-vllm/setup.sh && grep -q 'soft_step llmfit_install' auto-vllm/setup.sh` | N/A (script) | ⬜ pending |
| 26-01-02 | 01 | 1 | D-01 | unit | `uv run pytest tests/provisioning/test_state.py -x` | ✅ (needs update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

- [x] `tests/provisioning/test_state.py` — update member count 18→19, add LLMFIT_INSTALL to expected dict

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| llmfit binary download/install on remote server | INST-01 | Runs on remote target via SSH provisioning, not in local test env | Provision a test server and verify `/usr/local/bin/llmfit` exists |
| Non-fatal soft_step behavior under set -e | INST-02 | Requires running setup.sh with a failing download URL to verify WARN not exit | Override LLMFIT_URL to a bad URL, run setup.sh, verify it completes |
