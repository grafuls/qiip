# Phase 31: Download Service & API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-28
**Phase:** 31-download-service-api
**Areas discussed:** Download execution, Status tracking, Concurrency model

---

## Download Execution

| Option | Description | Selected |
|--------|-------------|----------|
| snapshot_download | Downloads entire model repo to HF cache layout. Compatible with vLLM. Resumes interrupted downloads. | ✓ |
| hf_hub_download per-file | Download individual files. More control but harder for vLLM compat. | |

**User's choice:** snapshot_download
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Thread per download | Each download via asyncio.to_thread(). Matches catalog scan pattern. | ✓ |
| ThreadPoolExecutor | Shared pool with max_workers. More structured but more setup. | |

**User's choice:** Thread per download
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| repo_id only | POST body: {"repo_id": "..."}. Downloads default revision. Simplest. | ✓ |
| repo_id + optional revision | Allows specifying branches/tags. More flexible. | |

**User's choice:** repo_id only
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Pass token explicitly | Pass settings.huggingface.api_token to snapshot_download(token=...). | ✓ |
| Ambient env var | Let huggingface_hub read HF_TOKEN from environment. | |

**User's choice:** Pass token explicitly
**Notes:** None

---

## Status Tracking

| Option | Description | Selected |
|--------|-------------|----------|
| 3-state: downloading/complete/failed | Matches DL-02 exactly. No queued state. | ✓ |
| 4-state: queued/downloading/complete/failed | Adds queued state for concurrency limit. More complex. | |

**User's choice:** 3-state
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Thread-safe dict | Dict guarded by threading.Lock. Matches circuit breaker pattern. | ✓ |
| asyncio-native dict | Plain dict, needs call_soon_threadsafe from threads. | |

**User's choice:** Thread-safe dict
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Keep all until restart | Status dict grows slowly. Operators see history. Lost on restart. | ✓ |
| TTL-based cleanup | Remove entries after N minutes. Prevents unbounded growth. | |

**User's choice:** Keep all until restart
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| State only | Just downloading/complete/failed plus error message. | ✓ |
| State + progress percent | Track progress via huggingface_hub callbacks. Richer but complex. | |

**User's choice:** State only
**Notes:** None

---

## Concurrency Model

| Option | Description | Selected |
|--------|-------------|----------|
| Semaphore limit of 2 | asyncio.Semaphore(2) gates concurrent downloads. Simple, tunable. | ✓ |
| No limit | Let operators manage bandwidth. Simplest code but risky for NFS. | |
| Configurable limit | Add a setting for max concurrent downloads. More flexible. | |

**User's choice:** Semaphore limit of 2
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Return existing status | Check dict first. If already downloading, return 200 with status. Idempotent. | ✓ |
| Reject with 409 Conflict | Return 409 if in progress. Explicit but less friendly. | |

**User's choice:** Return existing status
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Allow re-download | snapshot_download is idempotent. Downloads only missing/changed files. | ✓ |
| Reject with 200 + message | Check catalog first, return 'already exists'. Blocks legitimate updates. | |

**User's choice:** Allow re-download
**Notes:** None

---

## Claude's Discretion

None — user made all decisions.

## Deferred Ideas

None — discussion stayed within phase scope.
