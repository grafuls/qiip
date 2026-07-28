# Research Summary: v1.7 HuggingFace Integration

**Synthesized:** 2026-07-28
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md
**Confidence:** HIGH

## Executive Summary

v1.7 adds HuggingFace model download capabilities to the gateway. Operators pre-stage models from HuggingFace Hub onto shared NFS storage using the official `huggingface-hub` Python library (single new dependency). The NFS directory doubles as both download target and model catalog. Downloads run as background asyncio tasks in a dedicated ThreadPoolExecutor (2-3 workers) to prevent thread pool exhaustion from 30-120 minute downloads.

Critical risks mitigated: event loop blocking (dedicated executor), disk doubling (use `cache_dir` not `local_dir`), token leakage (`SecretStr`), symlink breakage (verify resolution), state loss on restart (accept in-memory with resume).

All patterns follow existing codebase: optional settings, background tasks, sync-in-thread, DI via `app.state`.

## Stack Additions

| Dependency | Version | Purpose |
|-----------|---------|---------|
| huggingface-hub | >=1.25, <2.0 | Official HF client — `snapshot_download()`, `scan_cache_dir()`, token auth |

- Zero dependency conflicts — huggingface-hub v1.0+ uses httpx internally
- No other runtime or dev dependencies needed
- `snapshot_download()` is sync — wrap with `asyncio.to_thread()` using a dedicated executor
- `disable_progress_bars()` at startup — tqdm thread-safety issue with concurrent downloads

## Feature Table Stakes

| Feature | Complexity | Dependencies |
|---------|-----------|-------------|
| HuggingFace settings + token | Low | None |
| NFS model catalog (`scan_cache_dir`) | Low | Settings |
| Catalog API endpoint | Low | Catalog |
| Download service (`snapshot_download`) | Medium | Settings, catalog |
| Download + status API endpoints | Low | Download service |
| Dashboard download buttons + status | Medium | All APIs |
| "Already downloaded" indicator | Low | Catalog API |

## Key Technical Decisions

1. **Use `cache_dir=` not `local_dir=`** — HF cache layout is what vLLM expects. `start-vllm.sh` symlinks `~/.cache/huggingface` to NFS. Using `local_dir` doubles disk and breaks the chain.
2. **Dedicated ThreadPoolExecutor** — Downloads block for 30-120 min. Default executor would starve etcd, QUADS, and health checks.
3. **Disable XET backend** — `HF_HUB_DISABLE_XET=1` — known hang issues in July 2026.
4. **In-memory download state** — Filesystem (NFS) is source of truth for completion. In-progress state is ephemeral. Resume via `snapshot_download()` blob-level resumption.
5. **llmfit `name` field IS the HF repo_id** — e.g. `meta-llama/Llama-3.1-8B-Instruct`. Zero mapping logic needed.
6. **Pre-flight `model_info()` for gated models** — Fast auth check before queuing multi-hour download.
7. **`GatedRepoError` before `RepositoryNotFoundError`** — Exception ordering matters (subclass).

## Architecture

New components follow existing patterns:

- `huggingface/downloader.py` — ModelDownloadService (mirrors LLMFitRunner, NodeProvisioner)
- `huggingface/catalog.py` — NFSModelCatalog (`scan_cache_dir` wrapper)
- `HuggingFaceSettings` — pydantic-settings with `SecretStr` token (mirrors RedfishSettings)
- Admin API endpoints under `/admin/models/`
- Dashboard additions to existing node detail page recommendations table

## Top 5 Pitfalls

1. **Thread pool exhaustion** — Dedicated executor with 2-3 workers, not default pool
2. **`local_dir` vs `cache_dir`** — Must use `cache_dir` or disk doubles and vLLM breaks
3. **XET backend hangs** — Disable via env var until upstream stabilizes
4. **Gated model errors are unhelpful** — Pre-flight `model_info()` + error mapping needed
5. **NFS symlink chain fragility** — Mount paths must match between gateway and vLLM nodes

## Suggested Build Order

1. **Foundation** — Settings, Pydantic models, NFSModelCatalog, catalog API
2. **Download Service + API** — ModelDownloadService, dedicated executor, download/status endpoints
3. **Dashboard Integration** — Download column in recommendations table, status badges, "already downloaded"

## Open Questions

- NFS write access from gateway host (verify mount permissions)
- `scan_cache_dir()` performance with 20+ models on NFS (profile if slow)
- `hf_transfer` Rust accelerator (defer to measurement)
- Concurrent download limits (start unlimited, add semaphore if needed)

---
*Synthesized: 2026-07-28*
*Ready for requirements: yes*
