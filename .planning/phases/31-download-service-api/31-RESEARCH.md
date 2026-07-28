# Phase 31: Download Service & API - Research

**Researched:** 2026-07-28
**Domain:** HuggingFace model downloading, background task concurrency, in-memory state tracking
**Confidence:** HIGH

## Summary

This phase adds a download service that triggers `snapshot_download()` from `huggingface_hub` in background threads, tracks download status in a thread-safe dict, and exposes two admin endpoints (POST trigger, GET status list). All decisions are locked via CONTEXT.md -- no new dependencies, no new patterns to invent.

The implementation follows the exact same structural patterns already established in the codebase: `asyncio.to_thread()` for blocking calls (catalog.py), `threading.Lock`-guarded dict (circuit_breaker.py), dependency injection via `app.state` + `get_X()` functions (dependencies.py), and admin router endpoints (admin.py). The only new concept is the `asyncio.Semaphore` for capping concurrent downloads.

**Primary recommendation:** Follow existing patterns exactly. New file `downloader.py` in the `huggingface/` package, Pydantic models in `models/admin.py`, wiring in `dependencies.py` and `main.py`, endpoints in `admin.py`.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use `snapshot_download()` from `huggingface_hub` with `cache_dir=` per Phase 30 D-07. Resumes interrupted downloads automatically.
- **D-02:** Each download runs in its own thread via `asyncio.to_thread()`. Concurrency limit handled by semaphore (D-09).
- **D-03:** POST body accepts `repo_id` only -- `{"repo_id": "meta-llama/Llama-3.1-8B-Instruct"}`. No revision parameter in v1.
- **D-04:** Pass HF token explicitly to `snapshot_download(token=...)` from `settings.huggingface.api_token`. Do not rely on ambient `HF_TOKEN`.
- **D-05:** 3-state machine: `downloading` / `complete` / `failed`. No `queued` state.
- **D-06:** Thread-safe `dict[str, DownloadStatus]` guarded by `threading.Lock`.
- **D-07:** Keep all entries until restart. No TTL cleanup.
- **D-08:** State only, no progress percentage. Include error message on failure.
- **D-09:** `asyncio.Semaphore(2)` gates concurrent downloads.
- **D-10:** Duplicate download requests return existing status (idempotent).
- **D-11:** Allow re-downloading cached models -- `snapshot_download` is idempotent.

### Claude's Discretion
None -- all decisions locked.

### Deferred Ideas (OUT OF SCOPE)
None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DL-01 | Operator can trigger model download via POST /admin/models/download | D-01, D-02, D-03 define the endpoint contract, execution model, and request shape |
| DL-02 | Gateway tracks download status (downloading/complete/failed) per model in memory | D-05, D-06, D-07, D-08 define the state machine, storage, and retention |
| DL-03 | Admin API exposes GET /admin/models/downloads returning current download statuses | Endpoint returns all entries from the status dict |
| DL-04 | Downloads use configured HF token for gated models | D-04 mandates explicit `token=` parameter from settings |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Download triggering | API / Backend | -- | POST endpoint validates input, delegates to service |
| Background download execution | API / Backend (thread pool) | -- | `snapshot_download` is blocking I/O, runs in thread via `asyncio.to_thread` |
| Status tracking | API / Backend (in-memory) | -- | Thread-safe dict, no persistence needed for v1 |
| Status querying | API / Backend | -- | GET endpoint reads from in-memory dict |
| Concurrency limiting | API / Backend | -- | `asyncio.Semaphore` gates thread dispatch |

## Standard Stack

### Core (already installed -- no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| huggingface_hub | >=1.25, <2.0 | `snapshot_download()` | Already installed (Phase 30). Provides resumable model downloads to HF cache layout. [VERIFIED: pyproject.toml + `python3 -c "import huggingface_hub; print(huggingface_hub.__version__)"` returns 1.25.1] |
| FastAPI | >=0.135, <1.0 | Admin endpoints | Already installed. Pydantic request/response validation. [VERIFIED: pyproject.toml] |
| structlog | >=26.1.0 | Structured logging | Already installed. Used by every service in the codebase. [VERIFIED: pyproject.toml] |
| pydantic | >=2.10, <3.0 | Request/response models | Already installed. Used for `DownloadRequest`, `DownloadStatus` models. [VERIFIED: pyproject.toml] |

### Supporting (stdlib -- no install needed)

| Library | Purpose | When to Use |
|---------|---------|-------------|
| `asyncio` (stdlib) | `Semaphore`, `to_thread` | Concurrency gating and thread dispatch |
| `threading` (stdlib) | `Lock` | Guard the status dict for thread safety |
| `datetime` (stdlib) | `datetime.now(tz=UTC)` | Timestamp download start/completion |
| `enum` (stdlib) | `StrEnum` or `str, Enum` | `DownloadState` enum values |

**Installation:** None. Zero new dependencies.

## Architecture Patterns

### System Architecture Diagram

```
POST /admin/models/download
  |
  v
[Admin Router] --Depends--> [DownloadService]
  |                              |
  |  1. Check status dict        |
  |     (Lock-guarded)           |
  |  2. If already downloading   |
  |     -> return existing       |
  |  3. Set status=downloading   |
  |  4. Acquire semaphore        |
  |  5. asyncio.to_thread(       |
  |       snapshot_download(...) |
  |     )                        |
  |  6. Update status dict       |
  |     (complete or failed)     |
  |                              |
GET /admin/models/downloads      |
  |                              |
  v                              |
[Admin Router] --Depends--> [DownloadService.get_all_statuses()]
                                 |
                            [dict[str, DownloadStatus]]
                              (Lock-guarded read)
```

### Recommended Project Structure

```
inference_proxy/
  huggingface/
    __init__.py          # existing
    catalog.py           # existing (Phase 30)
    downloader.py        # NEW: DownloadService, DownloadStatus model
  models/
    admin.py             # MODIFY: add DownloadRequest, DownloadStatusResponse
  config/
    dependencies.py      # MODIFY: add get_download_service()
  api/
    admin.py             # MODIFY: add POST + GET download endpoints
  main.py                # MODIFY: create DownloadService in lifespan
tests/
  huggingface/
    test_catalog.py      # existing
    test_downloader.py   # NEW: unit tests for DownloadService
  api/
    test_admin_downloads.py  # NEW: endpoint integration tests
```

### Pattern 1: Thread-Safe Status Dict (follows circuit_breaker.py)

**What:** `dict[str, DownloadStatus]` guarded by `threading.Lock`. Same pattern as `CircuitBreakerRegistry._breakers`.
**When to use:** Any shared mutable state accessed from both async handlers and background threads.
**Example:**
```python
# Source: inference_proxy/resilience/circuit_breaker.py (existing pattern)
class DownloadService:
    def __init__(self, cache_dir: str, token: str | None) -> None:
        self._cache_dir = cache_dir
        self._token = token
        self._statuses: dict[str, DownloadStatus] = {}
        self._lock = threading.Lock()
        self._semaphore: asyncio.Semaphore | None = None  # set in async context

    def _get_status(self, repo_id: str) -> DownloadStatus | None:
        with self._lock:
            return self._statuses.get(repo_id)

    def _set_status(self, repo_id: str, status: DownloadStatus) -> None:
        with self._lock:
            self._statuses[repo_id] = status
```

### Pattern 2: asyncio.Semaphore + to_thread (D-02, D-09)

**What:** Acquire async semaphore before dispatching blocking work to a thread. Semaphore lives in the event loop; the thread does the heavy I/O.
**When to use:** Limiting concurrent blocking operations from async code.
**Example:**
```python
# Source: Python stdlib asyncio docs [CITED: docs.python.org/3/library/asyncio-sync.html]
async def _run_download(self, repo_id: str) -> None:
    try:
        async with self._semaphore:
            await asyncio.to_thread(
                snapshot_download,
                repo_id,
                cache_dir=self._cache_dir,
                token=self._token,
            )
        self._set_status(repo_id, DownloadStatus(
            repo_id=repo_id, status=DownloadState.COMPLETE,
        ))
    except Exception as exc:
        self._set_status(repo_id, DownloadStatus(
            repo_id=repo_id, status=DownloadState.FAILED,
            error=str(exc),
        ))
```

### Pattern 3: Fire-and-Forget Background Task (D-02)

**What:** Use `asyncio.create_task()` to launch the download coroutine without awaiting it. The endpoint returns immediately with 202.
**When to use:** POST endpoint triggers long-running work, returns status immediately.
**Example:**
```python
# Source: existing pattern in admin.py setup_node (line 169)
async def trigger_download(self, repo_id: str) -> DownloadStatus:
    existing = self._get_status(repo_id)
    if existing and existing.status == DownloadState.DOWNLOADING:
        return existing  # D-10: idempotent
    status = DownloadStatus(repo_id=repo_id, status=DownloadState.DOWNLOADING)
    self._set_status(repo_id, status)
    asyncio.create_task(self._run_download(repo_id))
    return status
```

### Anti-Patterns to Avoid

- **Don't use `ThreadPoolExecutor` directly:** `asyncio.to_thread()` already manages the default executor. Adding a custom executor is unnecessary complexity. [ASSUMED]
- **Don't use `asyncio.Semaphore` inside the thread:** The semaphore must be acquired in the async context (before `to_thread`), not inside the thread function. `asyncio.Semaphore` is not thread-safe.
- **Don't catch `GatedRepoError` before `RepositoryNotFoundError`:** `GatedRepoError` inherits from `RepositoryNotFoundError`. Catch `GatedRepoError` first, then `RepositoryNotFoundError`, to get the specific error message. [VERIFIED: `python3 -c` confirmed inheritance chain]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Model downloading | Custom HTTP download + file assembly | `huggingface_hub.snapshot_download()` | Handles sharded models, LFS pointers, resume, ETag validation, HF cache layout |
| Thread-safe state | Custom lock-free structure | `threading.Lock` + `dict` | Simple, proven, matches existing codebase pattern |
| Concurrency limiting | Custom queue/worker pool | `asyncio.Semaphore(2)` | One line, stdlib, integrates with `async with` |
| Blocking-to-async bridge | Manual thread management | `asyncio.to_thread()` | Stdlib, handles executor lifecycle |

## Common Pitfalls

### Pitfall 1: Semaphore Created Outside Event Loop
**What goes wrong:** `asyncio.Semaphore()` created in `__init__` (which runs synchronously in lifespan) may bind to the wrong event loop or no loop.
**Why it happens:** Python 3.12 removed implicit event loop creation, but semaphores are still loop-bound.
**How to avoid:** Create the semaphore lazily on first use in an async method, or create it in an async factory method called from the lifespan.
**Warning signs:** `RuntimeError: no running event loop` or semaphore not blocking.

### Pitfall 2: Exception Ordering for Gated Repos
**What goes wrong:** Catching `RepositoryNotFoundError` swallows `GatedRepoError` because `GatedRepoError` is a subclass.
**Why it happens:** `GatedRepoError` inherits from `RepositoryNotFoundError` in huggingface_hub.
**How to avoid:** Catch `GatedRepoError` first in the except chain. [VERIFIED: python3 confirmed `GatedRepoError.__bases__ == (RepositoryNotFoundError,)`]
**Warning signs:** Gated model failures reported as "not found" instead of "gated".

### Pitfall 3: SecretStr Not Unwrapped
**What goes wrong:** Passing `settings.huggingface.api_token` (a `SecretStr`) directly to `snapshot_download(token=...)` -- the SDK expects a plain `str` or `None`.
**Why it happens:** Pydantic `SecretStr` wraps the value; `str(secret_str)` returns `"**********"`.
**How to avoid:** Use `api_token.get_secret_value()` when extracting the token, or `None` if not set.
**Warning signs:** Auth failures despite correct token in env.

### Pitfall 4: Status Dict Race on Duplicate Requests
**What goes wrong:** Two concurrent POST requests for the same repo_id both see "no existing status" and launch two downloads.
**Why it happens:** Check-then-act without holding the lock across both operations.
**How to avoid:** Hold the lock while checking AND setting the initial "downloading" status in a single critical section.
**Warning signs:** Duplicate download threads for the same model.

### Pitfall 5: create_task Without Reference
**What goes wrong:** `asyncio.create_task()` returns a `Task` that can be garbage collected if not referenced, silently cancelling the download.
**Why it happens:** Python GC collects unreferenced tasks.
**How to avoid:** Store task references in a set on the service instance. Add a done callback to discard completed tasks.
**Warning signs:** Downloads silently disappearing, status stuck on "downloading" forever.

## Code Examples

### DownloadState Enum
```python
# Pattern from existing codebase (models/admin.py uses str Enum)
from enum import Enum

class DownloadState(str, Enum):
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    FAILED = "failed"
```

### DownloadStatus Pydantic Model
```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class DownloadStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_id: str
    status: DownloadState
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
```

### DownloadRequest Pydantic Model
```python
class DownloadRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_id: str  # D-03: repo_id only
```

### snapshot_download Call
```python
# Source: huggingface_hub installed v1.25.1 help(snapshot_download)
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id,
    cache_dir=self._cache_dir,
    token=self._token,  # str | None, from SecretStr.get_secret_value()
    # repo_type defaults to "model"
    # revision defaults to "main"
)
```

### Exception Handling (ordered correctly per Pitfall 2)
```python
from huggingface_hub.errors import (
    GatedRepoError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)

try:
    await asyncio.to_thread(snapshot_download, ...)
except GatedRepoError:
    error = f"Model '{repo_id}' requires access approval on HuggingFace"
except RepositoryNotFoundError:
    error = f"Model '{repo_id}' not found on HuggingFace"
except RevisionNotFoundError:
    error = f"Revision not found for '{repo_id}'"
except Exception as exc:
    error = str(exc)
```

### Dependency Injection (follows existing pattern)
```python
# In dependencies.py
def get_download_service(request: Request) -> DownloadService:
    return request.app.state.download_service

# In main.py lifespan
token = (
    resolved_settings.huggingface.api_token.get_secret_value()
    if resolved_settings.huggingface.api_token
    else None
)
download_service = DownloadService(
    cache_dir=resolved_settings.huggingface.cache_dir,
    token=token,
)
app.state.download_service = download_service
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `huggingface_hub.utils.GatedRepoError` | `huggingface_hub.errors.GatedRepoError` | huggingface_hub 0.25+ | Import path changed; both work via re-export but `.errors` is canonical |
| Manual thread pools for background work | `asyncio.to_thread()` | Python 3.9+ | Stdlib, no executor management needed |

**Deprecated/outdated:**
- `huggingface_hub.utils` error imports: still work but `.errors` is the canonical module since 0.25+. Use `.errors` for new code. [ASSUMED]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Don't use `ThreadPoolExecutor` directly -- `asyncio.to_thread()` manages the default executor | Anti-Patterns | Low -- both approaches work, `to_thread` is simpler |
| A2 | `.errors` is canonical import path for HF exceptions since 0.25+ | State of the Art | Low -- `.utils` re-exports still work |

## Open Questions

None. All decisions are locked and the implementation path is clear from existing patterns.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/huggingface/test_downloader.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DL-01 | POST /admin/models/download triggers background download | unit + integration | `uv run pytest tests/huggingface/test_downloader.py tests/api/test_admin_downloads.py -x` | No -- Wave 0 |
| DL-02 | Status tracking (downloading/complete/failed) | unit | `uv run pytest tests/huggingface/test_downloader.py -x` | No -- Wave 0 |
| DL-03 | GET /admin/models/downloads returns statuses | integration | `uv run pytest tests/api/test_admin_downloads.py -x` | No -- Wave 0 |
| DL-04 | HF token passed to snapshot_download | unit | `uv run pytest tests/huggingface/test_downloader.py::TestDownloadToken -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/huggingface/test_downloader.py tests/api/test_admin_downloads.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/huggingface/test_downloader.py` -- covers DL-01, DL-02, DL-04
- [ ] `tests/api/test_admin_downloads.py` -- covers DL-01, DL-03
- [ ] `tests/conftest.py` -- add `get_download_service` override and mock

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (HF token) | `SecretStr` for token storage, explicit `get_secret_value()` at point of use |
| V3 Session Management | no | -- |
| V4 Access Control | no (internal API) | Internal network only per project constraints |
| V5 Input Validation | yes | Pydantic model validates `repo_id` field presence and type |
| V6 Cryptography | no | -- |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token leakage in logs | Information Disclosure | `SecretStr` prevents accidental `str()` serialization; structlog won't render it |
| Malicious repo_id (path traversal in cache_dir) | Tampering | `snapshot_download` handles path construction internally via HF cache layout -- no raw path joins |
| Unbounded concurrent downloads (resource exhaustion) | Denial of Service | `asyncio.Semaphore(2)` caps concurrent downloads per D-09 |

## Sources

### Primary (HIGH confidence)
- `huggingface_hub` installed v1.25.1 -- `help(snapshot_download)` for function signature and params
- `huggingface_hub.errors` module -- `dir()` for exception exports, inheritance chain verified via `.__bases__`
- Existing codebase files: `catalog.py`, `circuit_breaker.py`, `dependencies.py`, `admin.py`, `main.py`, `conftest.py`

### Secondary (MEDIUM confidence)
- Python stdlib docs for `asyncio.Semaphore`, `asyncio.to_thread`, `threading.Lock`

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all patterns exist in codebase
- Architecture: HIGH -- direct extension of Phase 30 catalog pattern
- Pitfalls: HIGH -- exception hierarchy verified via runtime inspection, concurrency patterns well-understood

**Research date:** 2026-07-28
**Valid until:** 2026-08-28 (stable -- no moving parts)
