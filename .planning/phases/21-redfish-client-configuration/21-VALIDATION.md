---
phase: 21
slug: redfish-client-configuration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-21
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio + pytest-httpx |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/redfish/ -x -q` |
| **Full suite command** | `uv run pytest --tb=short` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/redfish/ -x -q`
- **After every plan wave:** Run `uv run pytest --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | DIAG-03 | — | SecretStr masks BMC password in repr/dump | unit | `uv run pytest tests/redfish/test_client.py -x -q` | ❌ W0 | ⬜ pending |
| 21-01-02 | 01 | 1 | — | — | RedfishClient queries power state | unit | `uv run pytest tests/redfish/test_client.py -x -q` | ❌ W0 | ⬜ pending |
| 21-01-03 | 01 | 1 | — | — | RedfishClient issues power actions with check-before-act | unit | `uv run pytest tests/redfish/test_client.py -x -q` | ❌ W0 | ⬜ pending |
| 21-01-04 | 01 | 1 | DIAG-03 | — | Redfish errors mapped to human-readable messages | unit | `uv run pytest tests/redfish/test_client.py -x -q` | ❌ W0 | ⬜ pending |
| 21-01-05 | 01 | 1 | — | — | RedfishSettings loads from env vars with SecretStr | unit | `uv run pytest tests/config/test_settings.py -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/redfish/__init__.py` — test package
- [ ] `tests/redfish/test_client.py` — stubs for RedfishClient tests

*Existing pytest infrastructure covers framework and fixtures.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| BMC credentials never in logs | — | Requires structlog output inspection | Run app with REDFISH config, trigger error, grep logs for password |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
