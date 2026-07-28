# Architecture: HuggingFace Hub Integration (v1.7)

**Domain:** Model download + NFS catalog for existing LLM inference gateway
**Researched:** 2026-07-28
**Confidence:** HIGH

## Executive Decision

The gateway downloads models from HuggingFace Hub to its local NFS mount using `huggingface_hub.snapshot_download()`. Downloads run as background asyncio tasks (same pattern as provisioning). The NFS directory doubles as the HuggingFace cache -- `scan_cache_dir()` provides the model catalog for free. No custom metadata store, no database, no etcd keys for download state.

## Why Gateway Downloads, Not Target Node Downloads

The NFS mount is shared storage. Downloading once on the gateway makes the model available to all vLLM nodes simultaneously. Target nodes already symlink `/root/.cache/huggingface` to the NFS mount point (`/srv/hf-cache`), so any model downloaded to NFS is immediately servable by any node.

Downloading on each target node would be wasteful (duplicate downloads, duplicate storage) and unreliable (nodes may not have HF tokens configured, internet access varies per host).

## Architecture Overview

```
Operator clicks "Download" on a recommended model
        |
        v
  Admin API: POST /admin/models/download
  body: { "repo_id": "meta-llama/Llama-3.3-70B-Instruct" }
        |
        v
  ModelDownloadService checks:
    1. Already downloading? (in-memory task tracker) -> 409
    2. Already on NFS? (scan result) -> 200 with "already_downloaded"
        |
        v
  Fire background asyncio task:
    huggingface_hub.snapshot_download(
        repo_id=repo_id,
        local_dir=nfs_path / "hub" / "models--org--name",
        token=settings.hf_token,
    )
        |
  Track status in-memory: {repo_id: downloading|complete|failed}
        |
        v
  Dashboard polls: GET /admin/models/downloads
  Recommendations table shows per-model download status
```

## Component Boundaries

| Component | Responsibility | New/Modified | Communicates With |
|-----------|---------------|--------------|-------------------|
| `huggingface/downloader.py` | Download models via `snapshot_download`, track status | **NEW** | huggingface_hub library, filesystem |
| `huggingface/catalog.py` | Scan NFS for downloaded models via `scan_cache_dir` | **NEW** | huggingface_hub library, filesystem |
| `models/huggingface.py` | Pydantic models for download requests/responses/catalog | **NEW** | downloader, catalog, admin API |
| `api/admin.py` | New endpoints: download, status, catalog | **MODIFIED** (add 3-4 routes) | ModelDownloadService, NFS catalog |
| `config/settings.py` | `HuggingFaceSettings` nested config | **MODIFIED** (add 1 sub-model) |  Settings root |
| `config/dependencies.py` | Dependency providers for new services | **MODIFIED** (add 2 functions) | app.state |
| `main.py` | Wire download service + catalog in lifespan | **MODIFIED** (add ~10 lines) | downloader, catalog |
| `static/js/node_detail.js` | Download button in recommendations table | **MODIFIED** | Admin API |
| `templates/node_detail.html` | Minor: no structural changes needed | **UNCHANGED** | JS handles rendering |

### What Does NOT Change

- `provisioning/provisioner.py` -- downloads are independent of provisioning
- `provisioning/state.py` -- no new ProvisioningStep members
- `discovery/*` -- no etcd schema changes for downloads
- `models/node.py` -- no Node model changes
- `proxy/*`, `routing/*`, `resilience/*` -- untouched
- `llmfit/*` -- untouched (recommendations still come from SSH)
- `auto-vllm/setup.sh`, `auto-vllm/start-vllm.sh` -- NFS mount already handled

## New Components Detail

### 1. `inference_proxy/huggingface/catalog.py`

Scans the NFS-mounted HuggingFace cache directory to discover which models are already downloaded. Uses `huggingface_hub.scan_cache_dir()` which understands the `models--org--name` directory layout with `blobs/`, `refs/`, `snapshots/` subdirectories.

```python
from huggingface_hub import scan_cache_dir
from pathlib import Path


class NFSModelCatalog:
    """Scans NFS HuggingFace cache to list available models.

    The NFS mount point (default /srv/hf-cache) is the HF cache root.
    The hub subdirectory contains models--org--name directories.
    scan_cache_dir() parses this structure and returns repo metadata.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def list_models(self) -> dict[str, CatalogEntry]:
        """Return {repo_id: CatalogEntry} for all models on NFS.

        Runs scan_cache_dir() which walks the filesystem. This is
        a sync operation -- wrap in asyncio.to_thread() when called
        from async context.
        """
        # ponytail: scan_cache_dir is sync and walks fs; ~50ms for 20 models
        info = scan_cache_dir(cache_dir=str(self._cache_dir))
        result = {}
        for repo in info.repos:
            if repo.repo_type == "model":
                result[repo.repo_id] = CatalogEntry(
                    repo_id=repo.repo_id,
                    size_on_disk=repo.size_on_disk,
                    nb_files=repo.nb_files,
                    last_modified=repo.last_modified,
                    revisions=[r.commit_hash for r in repo.revisions],
                )
        return result

    def has_model(self, repo_id: str) -> bool:
        """Quick check if a model exists on NFS."""
        # ponytail: for single lookups, check directory existence directly
        # instead of full scan. models--org--name convention.
        dir_name = f"models--{repo_id.replace('/', '--')}"
        model_path = self._cache_dir / dir_name
        if not model_path.is_dir():
            return False
        # Verify it has at least one snapshot (not just an empty dir)
        snapshots = model_path / "snapshots"
        return snapshots.is_dir() and any(snapshots.iterdir())
```

Key design points:
- `scan_cache_dir()` from `huggingface_hub` is the authoritative way to inspect the cache. It handles symlinks, blobs, and incomplete downloads correctly.
- `has_model()` is a fast-path single check using the known directory naming convention (`models--org--name`), avoiding a full scan when we just need a boolean.
- Both methods are sync. Callers wrap with `asyncio.to_thread()`.

### 2. `inference_proxy/huggingface/downloader.py`

Manages background model downloads and tracks their status in-memory.

```python
from huggingface_hub import snapshot_download
import asyncio
from enum import StrEnum


class DownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"


class DownloadTask:
    """In-memory state for a single model download."""
    repo_id: str
    status: DownloadStatus
    error: str | None
    started_at: datetime
    completed_at: datetime | None


class ModelDownloadService:
    """Downloads HuggingFace models to NFS via snapshot_download.

    Downloads run in background threads (snapshot_download is sync
    and long-running). Status tracked in-memory dict.
    """

    def __init__(
        self,
        cache_dir: Path,
        catalog: NFSModelCatalog,
        token: str | None = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._catalog = catalog
        self._token = token
        self._tasks: dict[str, DownloadTask] = {}
        self._background: set[asyncio.Task] = set()

    def get_status(self, repo_id: str) -> DownloadTask | None:
        return self._tasks.get(repo_id)

    def get_all_tasks(self) -> dict[str, DownloadTask]:
        return dict(self._tasks)

    async def start_download(self, repo_id: str) -> DownloadTask:
        """Start a background download for repo_id.

        Returns immediately with PENDING status. The actual download
        runs in a thread via asyncio.to_thread().
        """
        if repo_id in self._tasks:
            existing = self._tasks[repo_id]
            if existing.status in (DownloadStatus.PENDING, DownloadStatus.DOWNLOADING):
                raise DownloadAlreadyInProgress(repo_id)

        task_state = DownloadTask(
            repo_id=repo_id,
            status=DownloadStatus.DOWNLOADING,
            ...
        )
        self._tasks[repo_id] = task_state

        async def _run():
            try:
                await asyncio.to_thread(
                    snapshot_download,
                    repo_id=repo_id,
                    cache_dir=str(self._cache_dir),
                    token=self._token,
                )
                task_state.status = DownloadStatus.COMPLETE
                task_state.completed_at = datetime.now(timezone.utc)
            except Exception as exc:
                task_state.status = DownloadStatus.FAILED
                task_state.error = str(exc)
                task_state.completed_at = datetime.now(timezone.utc)

        bg = asyncio.create_task(_run())
        self._background.add(bg)
        bg.add_done_callback(self._background.discard)
        return task_state
```

Key design points:
- `snapshot_download` is sync and can take minutes to hours for large models. Wrapping in `asyncio.to_thread()` is the natural fit (same pattern as etcd3gw calls).
- Uses `cache_dir` parameter, NOT `local_dir`. This preserves the HuggingFace cache structure (`blobs/`, `refs/`, `snapshots/`) which `scan_cache_dir()` expects and which the NFS symlink setup on target nodes relies on.
- Token passed as parameter. `snapshot_download` accepts `token=` directly -- no need to set `HF_TOKEN` env var or run `hf auth login`.
- In-memory status tracking. No persistence needed -- downloads in progress will be interrupted on gateway restart, and the operator can re-trigger. Completed downloads are discoverable via catalog scan.
- Background task pattern copied from `NodeProvisioner.fire_background()`.

### 3. `inference_proxy/models/huggingface.py`

Pydantic models for the HuggingFace integration API.

```python
class DownloadRequest(BaseModel):
    """POST /admin/models/download request body."""
    model_config = ConfigDict(frozen=True)
    repo_id: str  # e.g. "meta-llama/Llama-3.3-70B-Instruct"

class DownloadStatusResponse(BaseModel):
    """Status of a single download task."""
    model_config = ConfigDict(frozen=True)
    repo_id: str
    status: str  # pending|downloading|complete|failed
    error: str | None = None
    started_at: datetime
    completed_at: datetime | None = None

class CatalogEntry(BaseModel):
    """A model present on NFS storage."""
    model_config = ConfigDict(frozen=True)
    repo_id: str
    size_on_disk: int  # bytes
    nb_files: int
    last_modified: float  # timestamp
    revisions: list[str]

class CatalogResponse(BaseModel):
    """GET /admin/models/catalog response."""
    model_config = ConfigDict(frozen=True)
    models: list[CatalogEntry]
    cache_dir: str
```

### 4. Admin API Endpoints

Three new routes in `api/admin.py`:

```python
@admin_router.post("/models/download", status_code=202)
async def download_model(
    body: DownloadRequest,
    downloader: ModelDownloadService = Depends(get_downloader),
) -> DownloadStatusResponse:
    """Start downloading a model from HuggingFace Hub to NFS."""
    ...

@admin_router.get("/models/downloads")
async def list_downloads(
    downloader: ModelDownloadService = Depends(get_downloader),
) -> list[DownloadStatusResponse]:
    """Return status of all download tasks (active + recent)."""
    ...

@admin_router.get("/models/catalog")
async def list_catalog(
    catalog: NFSModelCatalog = Depends(get_catalog),
) -> CatalogResponse:
    """Return all models available on NFS storage."""
    ...
```

Error mapping follows existing patterns:
- 202: Download started (same as setup_node)
- 409: Download already in progress
- 200: Catalog/status queries

### 5. Settings

```python
class HuggingFaceSettings(BaseModel):
    """HuggingFace Hub integration configuration.

    When cache_dir is None, HuggingFace features are disabled
    (same pattern as QUADSSettings.base_url).
    """
    cache_dir: Path | None = None  # NFS mount point, e.g. /srv/hf-cache
    token: SecretStr | None = None  # HF API token for gated models
```

Env vars:
- `INFERENCE_PROXY_HUGGINGFACE__CACHE_DIR=/srv/hf-cache`
- `INFERENCE_PROXY_HUGGINGFACE__TOKEN=hf_xxxxx`

Follows the QUADSSettings/RedfishSettings pattern: feature disabled when key config is `None`.

### 6. Dashboard UI Changes

The recommendations table in `node_detail.js` already renders per-model rows. The change adds:
- A "Download" column to the recommendations table
- Per-row download button that calls `POST /admin/models/download`
- Status indicator: "Downloaded" (green badge), "Downloading..." (spinner), "Download" (button), "Failed" (red, retry)

The recommendations endpoint response does NOT change. Instead, the JS fetches the catalog (`GET /admin/models/catalog`) when loading recommendations, then cross-references `model.name` against the catalog to determine download status.

```
loadRecommendations() flow (modified):

1. Fetch recommendations (existing)
2. Fetch catalog (new parallel call)
3. Fetch active downloads (new parallel call)
4. For each model row:
   - If model.name in catalog -> show "Downloaded" badge
   - If model.name in active downloads -> show status badge
   - Else -> show "Download" button
```

This keeps the llmfit API untouched and the download API decoupled.

## Data Flow

### Download: POST /admin/models/download

```
1. Validate repo_id format
2. Check if already downloading (in-memory tasks) -> 409
3. Optional: check catalog if already on NFS -> return 200 with complete status
4. Create DownloadTask with status=DOWNLOADING
5. Fire asyncio.create_task wrapping asyncio.to_thread(snapshot_download(...))
6. Return 202 with DownloadStatusResponse
7. Background: snapshot_download runs (minutes to hours for large models)
8. On completion: update task status to COMPLETE
9. On error: update task status to FAILED with error message
```

### Catalog: GET /admin/models/catalog

```
1. await asyncio.to_thread(catalog.list_models)
2. scan_cache_dir() walks NFS mount directory
3. Returns {repo_id: CatalogEntry} for all models--* directories
4. Serialize as CatalogResponse
```

### Dashboard: Recommendations + Download Status

```
1. User clicks "Load" on recommendations panel
2. JS fires 3 parallel fetches:
   - GET /admin/nodes/{hostname}/recommendations (existing)
   - GET /admin/models/catalog (new)
   - GET /admin/models/downloads (new)
3. Render table with download column cross-referenced
4. User clicks "Download" on a model row
5. JS fires POST /admin/models/download { repo_id: "..." }
6. Toast: "Download started for meta-llama/..."
7. Next poll cycle updates the status badge
```

### Error Cases

| Error | Source | HTTP Status | Detail |
|-------|--------|-------------|--------|
| Download already in progress | DownloadAlreadyInProgress | 409 | "Download already in progress for {repo_id}" |
| HF token missing for gated model | GatedRepoError from hf_hub | 502 | "Access denied: {repo_id} requires authentication" |
| Invalid repo_id | RepositoryNotFoundError from hf_hub | 404 | "Repository not found: {repo_id}" |
| NFS not mounted / cache_dir missing | FileNotFoundError | 503 | "HuggingFace cache directory not available" |
| Network error during download | Background task catches | N/A | Task status set to FAILED with error string |
| Disk full | Background task catches | N/A | Task status set to FAILED with error string |

## Patterns to Follow

### Pattern: Optional Feature via Settings (QUADS/Redfish Precedent)

HuggingFace integration is disabled when `cache_dir` is `None`. Same conditional init pattern as `QUADSSettings.base_url` and `RedfishSettings.bmc_username`. In lifespan:

```python
if resolved_settings.huggingface.cache_dir is not None:
    catalog = NFSModelCatalog(resolved_settings.huggingface.cache_dir)
    downloader = ModelDownloadService(
        cache_dir=resolved_settings.huggingface.cache_dir,
        catalog=catalog,
        token=resolved_settings.huggingface.token.get_secret_value() if ...,
    )
    app.state.catalog = catalog
    app.state.downloader = downloader
else:
    app.state.catalog = None
    app.state.downloader = None
```

### Pattern: Background Task Tracking (Provisioner Precedent)

`ModelDownloadService` uses the same `asyncio.create_task` + `set[Task]` + `add_done_callback(discard)` pattern as `NodeProvisioner.fire_background()`.

### Pattern: Sync-in-Thread (etcd3gw Precedent)

`snapshot_download()` and `scan_cache_dir()` are both sync. Wrap in `asyncio.to_thread()`, same as every etcd3gw call in the codebase.

### Pattern: Dependency Provider via app.state (All Services)

Create in lifespan, store in app.state, expose via `get_downloader()` and `get_catalog()`. The dependency functions return `None` when the feature is disabled, matching `get_quads_client()`.

## Anti-Patterns to Avoid

### Anti-Pattern: Custom Metadata Database

**What:** Tracking downloaded models in SQLite/etcd/JSON files alongside the NFS cache.
**Why bad:** `scan_cache_dir()` already provides authoritative metadata. A separate store gets out of sync when models are deleted manually or downloaded outside the gateway.
**Instead:** Scan the NFS directory. It IS the catalog. `scan_cache_dir()` is the reader.

### Anti-Pattern: Downloading to a Non-Cache Directory

**What:** Using `local_dir` parameter of `snapshot_download()` instead of `cache_dir`.
**Why bad:** `local_dir` places files in a flat structure. The target nodes expect HuggingFace cache layout (with `blobs/`, `refs/`, `snapshots/` symlinks) because `start-vllm.sh` symlinks `/root/.cache/huggingface` to the NFS mount. `scan_cache_dir()` also expects cache layout.
**Instead:** Use `cache_dir=` parameter. This preserves the standard HF cache structure.

### Anti-Pattern: Download Progress Streaming

**What:** SSE endpoint streaming download byte counts in real-time.
**Why bad:** `snapshot_download()` uses internal tqdm progress bars. Intercepting progress requires custom `tqdm_class` override, threading complexity, and SSE state management. The milestone scope says "simple download status (downloading/complete/failed)."
**Instead:** Simple status polling. Status is one of three states. Dashboard polls on its existing refresh interval.

### Anti-Pattern: Persisting Download State to etcd

**What:** Writing download tasks to etcd like provisioning tasks.
**Why bad:** Downloads are ephemeral operations. If the gateway restarts mid-download, the download is interrupted anyway (the thread dies). The catalog scan tells us what completed. No value in persisting "was downloading" state.
**Instead:** In-memory dict. Gateway restart clears tasks. Completed downloads persist on NFS (the actual state).

### Anti-Pattern: Model Validation Before Download

**What:** Calling `model_info()` to verify repo exists before starting download.
**Why bad:** `snapshot_download()` already validates the repo and raises `RepositoryNotFoundError`. Double-checking adds latency and an extra API call for zero benefit.
**Instead:** Let `snapshot_download()` fail naturally. Catch and map the exception.

## File Layout

```
inference_proxy/
    huggingface/
        __init__.py              # NEW
        downloader.py            # NEW: ModelDownloadService
        catalog.py               # NEW: NFSModelCatalog
    models/
        huggingface.py           # NEW: DownloadRequest, CatalogEntry, etc.
    config/
        settings.py              # MODIFY: add HuggingFaceSettings
        dependencies.py          # MODIFY: add get_downloader(), get_catalog()
    api/
        admin.py                 # MODIFY: add 3 routes (download, downloads, catalog)
    main.py                      # MODIFY: wire catalog + downloader in lifespan
    static/js/
        node_detail.js           # MODIFY: download column in recommendations table

tests/
    huggingface/
        __init__.py              # NEW
        test_downloader.py       # NEW: mock snapshot_download, verify status tracking
        test_catalog.py          # NEW: mock scan_cache_dir, verify model listing
    models/
        test_huggingface.py      # NEW: Pydantic model validation tests
```

New files: 6 production + 4 test.
Modified files: 4 production.

## Build Order (Suggested Phases)

Dependencies flow top-down. Each phase is independently testable.

### Phase 1: Pydantic Models

Files: `models/huggingface.py`, tests
Dependencies: None
**Deliverable:** Data models exist. Pure Pydantic, no external deps.

### Phase 2: NFS Catalog Scanner

Files: `huggingface/__init__.py`, `huggingface/catalog.py`, tests
Dependencies: Phase 1, `huggingface_hub` library
**Deliverable:** `NFSModelCatalog.list_models()` and `has_model()` work against a test directory.

### Phase 3: Settings + Dependency Wiring

Files: `config/settings.py`, `config/dependencies.py`, `main.py`, `.env.example`
Dependencies: Phase 2
**Deliverable:** Catalog and downloader created at startup when configured.

### Phase 4: Catalog API Endpoint

Files: `api/admin.py` (add catalog route), tests
Dependencies: Phase 3
**Deliverable:** `GET /admin/models/catalog` returns NFS model list.

### Phase 5: Download Service + API

Files: `huggingface/downloader.py`, `api/admin.py` (add download routes), tests
Dependencies: Phase 3, Phase 4
**Deliverable:** `POST /admin/models/download` starts downloads, `GET /admin/models/downloads` shows status.

### Phase 6: Dashboard UI Integration

Files: `static/js/node_detail.js`
Dependencies: Phase 4 + Phase 5 (needs both API endpoints)
**Deliverable:** Download button per recommended model, status badges, "already downloaded" indicator.

## Dependency: huggingface_hub

One new production dependency: `huggingface_hub`. Add to `pyproject.toml`:

```toml
"huggingface-hub>=0.30",
```

This library provides:
- `snapshot_download()` -- download entire model repos
- `scan_cache_dir()` -- scan cache directory for downloaded models
- Token handling via `token=` parameter
- Proper error types: `RepositoryNotFoundError`, `GatedRepoError`, `HfHubHTTPError`

The library is well-maintained (Hugging Face official), MIT licensed, and has minimal transitive dependencies (requests, filelock, pyyaml, tqdm, packaging). It does NOT pull in PyTorch or transformers.

## Sources

- [huggingface_hub snapshot_download docs](https://huggingface.co/docs/huggingface_hub/guides/download) -- download API (HIGH confidence, verified via Context7)
- [huggingface_hub scan_cache_dir docs](https://huggingface.co/docs/huggingface_hub/guides/manage-cache) -- cache scanning API (HIGH confidence, verified via Context7)
- [huggingface_hub cache directory layout](https://huggingface.co/docs/huggingface_hub/guides/manage-cache) -- models--org--name structure (HIGH confidence, verified via Context7)
- [huggingface_hub token/auth](https://huggingface.co/docs/huggingface_hub/guides/cli) -- HF_TOKEN env var and token= parameter (HIGH confidence, verified via Context7)
- Existing codebase: start-vllm.sh (NFS symlink), setup.sh (NFS mount), provisioner.py, admin.py, settings.py, dependencies.py, main.py, node_detail.js (HIGH confidence)
