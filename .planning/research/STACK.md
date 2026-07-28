# Stack Research

**Domain:** HuggingFace Hub model downloads, token auth, and NFS model catalog (v1.7 milestone)
**Researched:** 2026-07-28
**Confidence:** HIGH
**Scope:** Stack additions for downloading models from HuggingFace Hub to NFS storage, managing HF API tokens for gated models, and scanning NFS to build a local model catalog. Existing stack (Python 3.12, FastAPI, httpx, etcd3gw, asyncssh, structlog, Pydantic v2, Jinja2) is validated and NOT re-evaluated here.

## New Python Dependencies for v1.7

**One new runtime dependency: `huggingface-hub`.**

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| huggingface-hub | >=1.25, <2.0 | Model downloads, HF API, token auth | Official Python client for HuggingFace Hub. Provides `snapshot_download()` for full model downloads, `HfApi.model_info()` for metadata, and built-in token authentication for gated models (Llama, Mistral, etc.). Since v1.0 it uses httpx internally -- same HTTP client as our stack. Apache-2.0 licensed. Latest stable is 1.25.1 (July 27, 2026). Python >=3.10 required (we use 3.12). | HIGH |

No new dev dependencies.

## Why huggingface-hub

### It Is the Only Correct Choice

HuggingFace Hub is not a generic file server. Models are stored with LFS, Xet storage, revision tracking, access gating, and structured metadata. The `huggingface-hub` library handles all of this:

- **`snapshot_download(repo_id, local_dir, token)`** -- downloads an entire model repo to a local directory, resumable, with file integrity verification. Handles LFS pointers, concurrent file downloads (internal thread pool), and incomplete download recovery via `IncompleteSnapshotError`.
- **`HfApi.model_info(repo_id, token)`** -- fetches model metadata (size, files, gating status) without downloading anything. Useful for the dashboard to show model details before download.
- **Token parameter** -- pass `token="hf_xxx"` to any call for gated model access. No separate auth library needed.
- **`scan_cache_dir(cache_dir)`** -- scans HF cache structure and returns `HFCacheInfo` with `CachedRepoInfo` per model. Useful if we download to HF cache layout. See NFS catalog section for trade-offs.

### Dependency Alignment

huggingface-hub v1.0+ migrated from `requests` to `httpx`. Its transitive dependencies:

| Dependency | Already in our stack? | Notes |
|------------|----------------------|-------|
| httpx | Yes | Same version range. No conflict. Shared HTTP stack. |
| filelock | No (new, small) | File locking for concurrent access. Stdlib-like. |
| fsspec | No (new) | Filesystem abstraction. Pulled transitively. |
| packaging | No (new, tiny) | Version parsing. |
| pyyaml | No (new) | YAML parsing. Well-established. |
| tqdm | No (new) | Progress bars. Used internally for download progress. |
| typer | No (new) | CLI framework (for `hf` CLI). We do not use the CLI. |
| typing-extensions | No (new, tiny) | Backport of typing features. |
| hf-xet | Conditional | Architecture-gated optional. Xet storage acceleration. Auto-installed on x86_64. |

**No conflicts with existing dependencies.** The httpx overlap is a feature -- both our proxy client and the HF client share the same HTTP stack.

## Key API Surface

| Function | What It Does | Sync/Async | Wrap Pattern |
|----------|-------------|------------|--------------|
| `snapshot_download(repo_id, local_dir=, token=)` | Download entire model repo | Sync (internal thread pool) | `asyncio.to_thread()` |
| `scan_cache_dir(cache_dir=)` | List cached repos with metadata | Sync | `asyncio.to_thread()` |
| `HfApi.model_info(repo_id, token=)` | Get model metadata from Hub | Sync | `asyncio.to_thread()` |

All are sync. Wrap in `asyncio.to_thread()` -- same pattern as every etcd3gw call in the codebase.

**Thread-safety caveat:** `snapshot_download()` uses `tqdm` internally for progress, which has a known thread-safety issue when run via `ThreadPoolExecutor`. Call `huggingface_hub.utils.disable_progress_bars()` once at startup. We do not need terminal progress bars -- we track download status in our own state model.

## Key Exception Types

| Exception | When | Map To |
|-----------|------|--------|
| `RepositoryNotFoundError` | Invalid repo_id or private repo without token | 404 |
| `GatedRepoError` | Gated model, no/invalid token | 403 |
| `HfHubHTTPError` | Network/API errors | 502 |
| `EntryNotFoundError` | Specific file not found in repo | 404 |
| `IncompleteSnapshotError` | Download did not complete all files | Internal retry/fail |

## NFS Model Catalog: Two Approaches

### Option A: Use HF Cache Layout + `scan_cache_dir()` (RECOMMENDED)

Download models using `snapshot_download(cache_dir="/nfs/models")` which creates the standard HF cache structure: `models--org--name/snapshots/<hash>/`. Then use `scan_cache_dir("/nfs/models")` to enumerate what is downloaded.

**Why this approach:**
- The existing `start-vllm.sh` already symlinks `~/.cache/huggingface` to NFS. vLLM loads models from the HF cache layout.
- `scan_cache_dir()` returns structured `CachedRepoInfo` objects with repo_id, size, file count, and revision info. No custom parsing needed.
- Resumable downloads and blob deduplication work automatically.

### Option B: Use `local_dir` + Filesystem Scan

Download models using `snapshot_download(local_dir="/nfs/models/meta-llama--Llama-3.1-8B-Instruct")` which writes files flat (no cache structure). Scan with `pathlib.Path.iterdir()`.

**Why not:** Loses HF cache deduplication, resume logic is less reliable, and requires custom completeness detection. vLLM can load from flat dirs but the existing provisioning scripts use HF cache layout.

## Integration with Existing App

### Settings Addition

```python
class HuggingFaceSettings(BaseModel):
    """HuggingFace Hub configuration.

    When ``token`` is ``None`` (the default), only public models
    can be downloaded. Setting it via
    ``INFERENCE_PROXY_HUGGINGFACE__TOKEN`` enables gated model access.
    """
    token: SecretStr | None = None
    models_dir: Path = Path("/nfs/models")
    download_timeout: int = 7200  # seconds, 2 hours for large models (70B+)
```

Follows the `RedfishSettings.bmc_password` pattern for `SecretStr`. Add to root `Settings` class:

```python
huggingface: HuggingFaceSettings = HuggingFaceSettings()
```

Env vars: `INFERENCE_PROXY_HUGGINGFACE__TOKEN=hf_xxxxx`, `INFERENCE_PROXY_HUGGINGFACE__MODELS_DIR=/nfs/models`

### Download Execution Pattern

Same pattern as etcd3gw sync calls throughout the codebase:

```python
from huggingface_hub import snapshot_download
from huggingface_hub.utils import disable_progress_bars

disable_progress_bars()  # call once at startup

# In async context:
path = await asyncio.to_thread(
    snapshot_download,
    repo_id="meta-llama/Llama-3.1-8B-Instruct",
    cache_dir=str(settings.huggingface.models_dir),
    token=settings.huggingface.token.get_secret_value() if settings.huggingface.token else None,
)
```

### Download Status Tracking

Downloads are long-running (minutes to hours). Track status in-memory, same pattern as provisioning state:

```python
class DownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"
```

In-memory dict is sufficient for v1.7. Completed state is visible on the filesystem via `scan_cache_dir()`. If a download is interrupted and the gateway restarts, the model simply is not present in the catalog -- operator retries manually. No persistence needed beyond what the filesystem provides.

### Admin API Extension

New endpoints following existing admin patterns:

```
GET  /admin/models/catalog          -> list models on NFS (scan_cache_dir)
POST /admin/models/download         -> start download (repo_id in body)
GET  /admin/models/downloads        -> current download statuses
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Download client | huggingface-hub | httpx direct to HF API | Would need to reimplement cache structure, LFS handling, blob dedup, resume, gated auth. Months of fragile work. |
| Download client | huggingface-hub | `hf` CLI via subprocess | Harder to integrate (output parsing, error handling, token passing). Library gives typed Python exceptions. |
| Download client | huggingface-hub | `git lfs clone` | Requires git-lfs installed. No Python-level progress tracking. No token management API. |
| Cache scanning | `scan_cache_dir()` | Custom `os.walk()` | Would need to parse `models--org--name` naming, handle symlinks, verify completeness. `scan_cache_dir()` does this correctly with `CachedRepoInfo`. |
| Download tracking | In-memory dict | SQLite / etcd | Downloads are ephemeral. Completed state lives on filesystem. No persistence needed. |
| Download tracking | In-memory dict | Redis | New infrastructure dependency for transient data. YAGNI. |
| Token storage | `SecretStr` in settings | Vault / external secret manager | Internal network tool. Env var + SecretStr is the established pattern (see Redfish BMC password). |

## What NOT to Add

| Technology | Why Not |
|------------|---------|
| `transformers` | Massive dependency (PyTorch). We only download model files, not load them. |
| `torch` / `tensorflow` | Model execution happens on vLLM nodes, not the gateway. |
| `datasets` | Not downloading datasets. |
| `safetensors` | vLLM handles model loading. Gateway only downloads. |
| `boto3` / `s3fs` | Models are on HuggingFace Hub, not S3. |
| `celery` / `dramatiq` | `asyncio.to_thread` is sufficient for background downloads. Same pattern as provisioning. No task queue needed. |
| `requests` | huggingface-hub uses httpx since v1.0. We already use httpx. No reason to add requests. |
| `hf_transfer` | Rust-based download accelerator. Optional optimization. Not needed for v1.7 -- standard downloads are fast enough on internal networks. Add when download speed is measurably a problem. |
| WebSocket / SSE for download progress | Scope says "simple status (downloading/complete/failed)". Dashboard polling on existing 10-second interval suffices. |

## Installation

```bash
# Add to pyproject.toml dependencies:
uv add "huggingface-hub>=1.25,<2.0"
```

No other installation steps on the gateway. No changes to target server provisioning scripts.

## Key Version Constraints

| Dependency | Minimum | Why This Minimum |
|------------|---------|------------------|
| huggingface-hub >= 1.25 | Latest stable (July 2026). Uses httpx internally (since v1.0). Python >=3.10 required (we use 3.12). Includes `snapshot_download` with `local_dir`/`cache_dir` support, `HfApi.model_info()`, `scan_cache_dir()`, and token auth. |

**Existing constraints unchanged:**

| Existing Dependency | Minimum | v1.7 Relevance |
|---------------------|---------|----------------|
| FastAPI >= 0.135 | New admin endpoints for download management and catalog |
| Pydantic >= 2.10 | New models for download status, catalog entries, HF settings |
| pydantic-settings >= 2.14 | HuggingFaceSettings with SecretStr token |
| structlog >= 26.1.0 | Download operation logging |

## Sources

- huggingface-hub PyPI: https://pypi.org/project/huggingface-hub/ -- v1.25.1 (July 2026), Apache-2.0
- huggingface-hub GitHub: https://github.com/huggingface/huggingface_hub -- official Python client
- huggingface-hub download guide: Context7 /huggingface/huggingface_hub -- snapshot_download, local_dir, cache_dir, allow_patterns, token parameter (HIGH)
- huggingface-hub cache management: Context7 /huggingface/huggingface_hub -- scan_cache_dir, HFCacheInfo, CachedRepoInfo (HIGH)
- huggingface-hub HfApi: Context7 /huggingface/huggingface_hub -- model_info, list_models (HIGH)
- huggingface-hub async discussion: https://github.com/huggingface/huggingface_hub/issues/1123 -- no native async for snapshot_download, asyncio.to_thread is the pattern
- huggingface-hub tqdm thread safety: https://github.com/huggingface/huggingface_hub/issues/3285 -- disable_progress_bars() workaround for ThreadPoolExecutor usage
- huggingface-hub NFS + Xet: https://github.com/huggingface/huggingface_hub/issues/3463 -- NFS volumes work, Xet activation is repo-dependent
- Existing codebase: `inference_proxy/config/settings.py` -- SecretStr pattern (RedfishSettings.bmc_password), pydantic-settings nested model pattern
- Existing codebase: `inference_proxy/provisioning/provisioner.py` -- asyncio.to_thread pattern for sync operations, background task pattern
- Existing codebase: `inference_proxy/provisioning/state.py` -- StrEnum + frozen Pydantic model for state tracking

---
*Stack research for: HuggingFace Hub model downloads, token auth, and NFS model catalog (v1.7)*
*Researched: 2026-07-28*
