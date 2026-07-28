# Phase 31: Download Service & API - Context

**Gathered:** 2026-07-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Operators can download models from HuggingFace Hub to NFS and monitor download status. Adds a download service with background execution, in-memory status tracking, and two admin endpoints (POST to trigger, GET to list statuses).

</domain>

<decisions>
## Implementation Decisions

### Download Execution
- **D-01:** Use `snapshot_download()` from `huggingface_hub` — downloads entire model repo to HF cache layout. Compatible with vLLM model loading. Uses `cache_dir=` per Phase 30 D-07. Resumes interrupted downloads automatically.
- **D-02:** Each download runs in its own thread via `asyncio.to_thread()` — matches the catalog scan pattern from Phase 30. Concurrency limit handled by semaphore (see D-08).
- **D-03:** POST body accepts `repo_id` only — `{"repo_id": "meta-llama/Llama-3.1-8B-Instruct"}`. Downloads default revision (main). No revision parameter in v1.
- **D-04:** Pass HF token explicitly to `snapshot_download(token=...)` from `settings.huggingface.api_token` — explicit, testable, satisfies DL-04. Do not rely on ambient `HF_TOKEN` env var.

### Status Tracking
- **D-05:** 3-state machine: `downloading` / `complete` / `failed` — matches DL-02 requirement text exactly. No `queued` state since downloads start immediately (semaphore gates within the thread).
- **D-06:** Thread-safe `dict[str, DownloadStatus]` guarded by `threading.Lock` — matches the circuit breaker pattern in `resilience/circuit_breaker.py`. Lost on restart, which is fine for v1 per DL-02.
- **D-07:** Keep all entries until restart — status dict grows slowly (one entry per download). Operators expect to see history. No TTL cleanup.
- **D-08:** State only, no progress percentage — DL-02/DL-03 don't mention progress. Include error message on failure. Add progress tracking later only if operators ask.

### Concurrency Model
- **D-09:** `asyncio.Semaphore(2)` gates concurrent downloads — prevents NFS bandwidth saturation. Simple, tunable later.
- **D-10:** Duplicate download requests return existing status — check status dict first. If model is already downloading, return 200 with current status. Idempotent.
- **D-11:** Allow re-downloading cached models — `snapshot_download` is idempotent (checks existing files, downloads only missing/changed). Useful for updating to latest revision.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — project overview, constraints, key decisions
- `.planning/REQUIREMENTS.md` — v1.7 requirements (DL-01 through DL-04 map to this phase)
- `.planning/ROADMAP.md` — phase 31 success criteria and phase dependencies

### Phase 30 Decisions (carry forward)
- `.planning/phases/30-foundation-model-catalog/30-CONTEXT.md` — D-02 (huggingface package), D-06 (huggingface-hub dep), D-07 (cache_dir parameter), D-08 (XET disable), D-09 (repo_id = model name), D-10 (disable_progress_bars)

### Existing Patterns
- `inference_proxy/huggingface/catalog.py` — catalog service pattern to extend (same package, same asyncio.to_thread wrapping)
- `inference_proxy/config/settings.py` — HuggingFaceSettings already has `cache_dir` and `api_token`
- `inference_proxy/config/dependencies.py` — dependency injection pattern for new download service
- `inference_proxy/api/admin.py` — admin router for new endpoints
- `inference_proxy/main.py` — lifespan wiring for service creation, threading.Event stop pattern
- `inference_proxy/resilience/circuit_breaker.py` — thread-safe dict with Lock pattern to follow

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `HuggingFaceSettings` in settings.py: already has `cache_dir` and `api_token` (SecretStr) — download service reads both
- `huggingface_hub` already installed with `snapshot_download` available
- `admin_router` in api/admin.py: add POST and GET download endpoints
- `threading.Lock` pattern from circuit_breaker.py: follow for status dict

### Established Patterns
- Domain packages: download service goes in `inference_proxy/huggingface/downloader.py` (same package as catalog.py)
- Dependency injection: service created in lifespan, stored on `app.state`, exposed via `get_download_service()` in dependencies.py
- Background threads: `threading.Thread(target=..., daemon=True)` with `threading.Event` for stop signal — used by etcd watch and health check
- `asyncio.to_thread()`: wraps blocking calls for non-blocking use in FastAPI handlers

### Integration Points
- `inference_proxy/huggingface/downloader.py` — new file: DownloadService, DownloadStatus model
- `inference_proxy/config/dependencies.py` — add `get_download_service()` provider
- `inference_proxy/api/admin.py` — add POST /admin/models/download and GET /admin/models/downloads
- `inference_proxy/main.py` — create download service in lifespan, store on app.state

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 31-Download Service & API*
*Context gathered: 2026-07-28*
