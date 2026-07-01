---
phase: 10
slug: script-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-01
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | bash -n + shellcheck (structural), manual execution (behavioral) |
| **Config file** | none — shell scripts, no test framework config |
| **Quick run command** | `bash -n auto-vllm-container/setup.sh && bash -n auto-vllm-container/start-vllm.sh && bash -n auto-vllm-container/entrypoint.sh` |
| **Full suite command** | `shellcheck auto-vllm-container/setup.sh auto-vllm-container/start-vllm.sh auto-vllm-container/entrypoint.sh` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `bash -n` syntax check on modified scripts
- **After every plan wave:** Run shellcheck on all scripts
- **Before `/gsd:verify-work`:** Full shellcheck must pass
- **Max feedback latency:** 2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | SCRIPT-01 | — | set -euo pipefail, early exit on error | structural | `bash -n setup.sh` | TBD | ⬜ pending |
| TBD | TBD | TBD | SCRIPT-02 | — | guard checks skip completed steps | structural | `shellcheck setup.sh` | TBD | ⬜ pending |
| TBD | TBD | TBD | SCRIPT-03 | — | timeout on NFS mount, abort on failure | structural | `bash -n setup.sh` | TBD | ⬜ pending |
| TBD | TBD | TBD | SCRIPT-04 | — | podman run --replace for name collisions | structural | `bash -n start-vllm.sh` | TBD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements — shell scripts need no test framework installation.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Re-running setup.sh skips completed steps | SCRIPT-02 | Requires bare metal with NVIDIA GPU and NFS | Run setup.sh twice on target host, verify second run skips all steps |
| NFS mount times out within 30s | SCRIPT-03 | Requires NFS server or simulated network failure | Run with unreachable NFS_SERVER, verify timeout and non-zero exit |
| podman --replace swaps container | SCRIPT-04 | Requires podman and GPU on target host | Start container, run start-vllm.sh again, verify old container replaced |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 2s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
