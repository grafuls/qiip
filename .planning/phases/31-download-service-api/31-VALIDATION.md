---
phase: 31
slug: download-service-api
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-28
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 31-01-01 | 01 | 1 | DL-01 | — | N/A | unit | `uv run pytest tests/huggingface/test_downloader.py -x -q` | ❌ W0 | ⬜ pending |
| 31-01-02 | 01 | 1 | DL-02 | — | N/A | unit | `uv run pytest tests/huggingface/test_downloader.py -x -q` | ❌ W0 | ⬜ pending |
| 31-01-03 | 01 | 1 | DL-03 | — | N/A | unit | `uv run pytest tests/huggingface/test_downloader.py -x -q` | ❌ W0 | ⬜ pending |
| 31-01-04 | 01 | 1 | DL-04 | T-31-01 | HF token passed explicitly, never logged | unit | `uv run pytest tests/huggingface/test_downloader.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/huggingface/test_downloader.py` — stubs for DL-01 through DL-04
- [ ] Test fixtures for mocking `snapshot_download` and download status tracking

*Existing pytest infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| NFS download to real storage | DL-01 | Requires NFS mount and HF Hub access | Trigger POST with valid repo_id, verify files appear in cache_dir |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
