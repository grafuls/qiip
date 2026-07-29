# Phase 30: Foundation & Model Catalog - Research

**Researched:** 2026-07-28
**Domain:** HuggingFace Hub cache scanning, FastAPI admin endpoints
**Confidence:** HIGH

## Summary

Phase 30 adds HuggingFace configuration and a model catalog service that scans NFS-cached models. The single new dependency (`huggingface-hub`) provides `scan_cache_dir(cache_dir=...)` which returns structured cache metadata without network calls. The entire phase follows established codebase patterns: nested `BaseModel` settings, domain-package under `inference_proxy/huggingface/`, dependency injection via `app.state`, and admin router endpoints.

All decisions are locked from CONTEXT.md. The implementation is straightforward: one settings sub-model, one service class with a single async method wrapping a sync filesystem scan, one Pydantic response model, and one GET endpoint on the existing admin router.

**Primary recommendation:** Follow existing patterns exactly. The `scan_cache_dir()` API does all the heavy lifting -- the service is a thin wrapper that filters by `repo_type == "model"` and extracts `repo_id`.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** On-demand scan per API request -- wrap `scan_cache_dir()` in `asyncio.to_thread()` on each `GET /admin/models/catalog` call. No background thread, no cached state. Add caching later only if NFS latency becomes a measured problem.
- **D-02:** New `inference_proxy/huggingface/` package -- `catalog.py` for the catalog service. Follows the domain-package pattern of `quads/`, `llmfit/`, `redfish/`. Phase 31 download service joins the same package.
- **D-03:** Always-on with required `cache_dir` -- NFS cache path is required configuration (gateway won't start without it). HF API token is optional (only needed for gated model downloads in Phase 31). No `None` guard pattern.
- **D-04:** Repo ID only per catalog entry -- no size, last_modified, or file count. Minimal response matching CAT-01 requirement.
- **D-05:** Objects with `repo_id` field, not flat strings -- response is a list of `{"repo_id": "meta-llama/..."}` objects. Extensible without breaking clients when fields are added later.
- **D-06:** Single new dependency: `huggingface-hub >=1.25, <2.0`
- **D-07:** Must use `cache_dir=` parameter (not `local_dir=`) for HF cache layout compatible with vLLM
- **D-08:** `HF_HUB_DISABLE_XET=1` env var set at startup to avoid hang issues
- **D-09:** llmfit model name IS the HF `repo_id` -- zero mapping needed between llmfit recommendations and HF downloads
- **D-10:** `disable_progress_bars()` at startup for thread safety

### Claude's Discretion
No specific discretion areas -- all implementation details locked.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CFG-01 | Operator can configure HuggingFace API token via environment variable for gated model access | `HuggingFaceSettings.api_token: SecretStr \| None` with env var `INFERENCE_PROXY_HUGGINGFACE__API_TOKEN`. Uses existing pydantic-settings nested env var pattern. |
| CFG-02 | Operator can configure the NFS cache directory path where models are stored | `HuggingFaceSettings.cache_dir: str` (required, no default) with env var `INFERENCE_PROXY_HUGGINGFACE__CACHE_DIR`. Validated at startup via Path existence check. |
| CAT-01 | Gateway scans NFS cache directory and returns a list of downloaded models with repo IDs | `scan_cache_dir(cache_dir=...)` returns `HFCacheInfo.repos` frozenset. Filter by `repo_type == "model"`, extract `repo_id`. Wrapped in `asyncio.to_thread()`. |
| CAT-02 | Admin API exposes GET /admin/models/catalog returning all models currently on NFS | New endpoint on existing `admin_router`. Returns `ModelCatalogResponse` with `models: list[CatalogEntry]`. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HF configuration (token, cache path) | API / Backend | -- | Settings loaded at startup, validated server-side |
| NFS cache scanning | API / Backend | -- | Filesystem I/O on server-local NFS mount |
| Catalog API endpoint | API / Backend | -- | Admin REST endpoint, no frontend in this phase |
| HF startup guards (XET, progress bars) | API / Backend | -- | Process-level env vars and library config at boot |

## Standard Stack

### Core (new dependency)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| huggingface-hub | >=1.25, <2.0 (latest: 1.25.1) | NFS cache scanning via `scan_cache_dir()` | Official HF client. Only library that understands the HF cache directory structure. [VERIFIED: PyPI registry, slopcheck OK, official HF docs] |

### Already Installed (no changes)
| Library | Purpose | Used For |
|---------|---------|----------|
| fastapi | HTTP framework | Admin router endpoint |
| pydantic | Data models | `CatalogEntry`, `ModelCatalogResponse`, `HuggingFaceSettings` |
| pydantic-settings | Configuration | Env var loading for HF settings |
| structlog | Logging | Service-level logging |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `scan_cache_dir()` | Manual directory walk of `models--*` dirs | Fragile, reimplements HF cache structure parsing. `scan_cache_dir()` handles corruption, symlinks, edge cases. |

**Installation:**
```bash
uv add "huggingface-hub>=1.25,<2.0"
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| huggingface-hub | PyPI | 5+ years (since 2020) | 30M+/week | github.com/huggingface/huggingface_hub | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Operator (env vars)
    |
    v
HuggingFaceSettings -----> Settings (root)
    |                           |
    | cache_dir, api_token      | lifespan startup
    v                           v
ModelCatalogService -------> app.state.catalog_service
    |                           |
    | scan_cache_dir()          | get_catalog_service()
    | (asyncio.to_thread)       |
    v                           v
NFS /path/to/cache          GET /admin/models/catalog
    |                           |
    | models--org--name/        | ModelCatalogResponse
    | blobs/, snapshots/        |   models: [{repo_id: "..."}]
    v                           v
HFCacheInfo.repos           JSON response to client
```

### Recommended Project Structure
```
inference_proxy/
  huggingface/
    __init__.py          # empty
    catalog.py           # CatalogEntry, ModelCatalogService
  config/
    settings.py          # + HuggingFaceSettings
    dependencies.py      # + get_catalog_service()
  api/
    admin.py             # + GET /admin/models/catalog, ModelCatalogResponse
  models/
    admin.py             # + ModelCatalogResponse, CatalogEntry (OR in huggingface/catalog.py)
  main.py                # + HF startup config, catalog service in lifespan
```

### Pattern 1: Nested Settings Sub-Model
**What:** Add `HuggingFaceSettings(BaseModel)` as nested config under root `Settings`.
**When to use:** Every domain-specific configuration group.
**Example:**
```python
# Source: inference_proxy/config/settings.py (existing pattern)
class HuggingFaceSettings(BaseModel):
    """HuggingFace Hub configuration."""
    cache_dir: str                    # Required -- no default
    api_token: SecretStr | None = None  # Optional for Phase 30, needed Phase 31

# In root Settings class:
class Settings(BaseSettings):
    # ... existing fields ...
    huggingface: HuggingFaceSettings  # No default = required
```
**Env vars:** `INFERENCE_PROXY_HUGGINGFACE__CACHE_DIR`, `INFERENCE_PROXY_HUGGINGFACE__API_TOKEN`

### Pattern 2: Domain Service with Sync-to-Async Wrapping
**What:** Service class wrapping a sync library call in `asyncio.to_thread()`.
**When to use:** When the underlying library (huggingface_hub) is synchronous.
**Example:**
```python
# Source: follows inference_proxy/llmfit/runner.py pattern
import asyncio
from pathlib import Path
from huggingface_hub import scan_cache_dir

class ModelCatalogService:
    def __init__(self, cache_dir: str) -> None:
        self._cache_dir = cache_dir

    async def list_models(self) -> list[CatalogEntry]:
        cache_info = await asyncio.to_thread(scan_cache_dir, self._cache_dir)
        return [
            CatalogEntry(repo_id=repo.repo_id)
            for repo in cache_info.repos
            if repo.repo_type == "model"
        ]
```

### Pattern 3: Dependency Injection via app.state
**What:** Create service in lifespan, store on `app.state`, expose via `get_X()` function.
**When to use:** All services that need to be available to route handlers.
**Example:**
```python
# Source: inference_proxy/config/dependencies.py (existing pattern)
def get_catalog_service(request: Request) -> ModelCatalogService:
    """Return the model catalog service from the current application state."""
    return request.app.state.catalog_service  # type: ignore[no-any-return]
```

### Anti-Patterns to Avoid
- **Caching scan results in memory:** D-01 explicitly says on-demand per request. No `@lru_cache`, no background refresh, no stale state.
- **Using `local_dir=` instead of `cache_dir=`:** D-07 requires `cache_dir=` for vLLM-compatible HF cache layout. The `local_dir` parameter uses a flat file structure incompatible with vLLM's expectations.
- **Making `cache_dir` optional with None:** D-03 says always-on with required `cache_dir`. The gateway should fail to start if `INFERENCE_PROXY_HUGGINGFACE__CACHE_DIR` is not set.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HF cache directory parsing | Walk `models--*` dirs manually | `scan_cache_dir(cache_dir=...)` | HF cache has symlinks, blobs, snapshots, corruption handling. The library handles all edge cases. |
| Progress bar suppression | Set env vars manually | `disable_progress_bars()` | Thread-safe, respects HF internal state |
| Repo ID extraction from directory names | Parse `models--org--name` format | `CachedRepoInfo.repo_id` | Format may change between HF versions |

## Common Pitfalls

### Pitfall 1: CacheNotFound on Missing Directory
**What goes wrong:** `scan_cache_dir()` raises `CacheNotFound` if the cache directory doesn't exist.
**Why it happens:** NFS mount not available, path misconfigured, directory not created yet.
**How to avoid:** Validate `cache_dir` path exists at startup in lifespan. Fail fast with a clear error message.
**Warning signs:** Gateway starts but catalog endpoint returns 500 errors.

### Pitfall 2: XET Hang on Scan
**What goes wrong:** Without `HF_HUB_DISABLE_XET=1`, the HF library may attempt Xet storage operations that hang on scan.
**Why it happens:** Xet is a newer chunked caching layer that can cause issues when not properly configured.
**How to avoid:** Set `os.environ["HF_HUB_DISABLE_XET"] = "1"` early in lifespan, before any HF imports or calls. Per D-08.
**Warning signs:** `scan_cache_dir()` hangs or takes abnormally long.

### Pitfall 3: Progress Bar Thread Safety
**What goes wrong:** tqdm progress bars in background threads can cause output corruption or thread contention.
**Why it happens:** `scan_cache_dir()` runs in `asyncio.to_thread()`, tqdm is not thread-safe by default.
**How to avoid:** Call `disable_progress_bars()` once at startup. Per D-10.
**Warning signs:** Garbled console output, occasional hangs during scan.

### Pitfall 4: Including Non-Model Repos in Catalog
**What goes wrong:** Catalog returns datasets and spaces alongside models.
**Why it happens:** HF cache stores all repo types (`model`, `dataset`, `space`) in the same directory.
**How to avoid:** Filter `repo.repo_type == "model"` when iterating `cache_info.repos`.
**Warning signs:** Unexpected entries in catalog response that aren't model repo IDs.

### Pitfall 5: Required Settings Preventing Startup
**What goes wrong:** Gateway fails to start because `HuggingFaceSettings` has no defaults.
**Why it happens:** `cache_dir: str` with no default raises `ValidationError` when env var is missing.
**How to avoid:** This is intentional per D-03. Document clearly in `.env.example`. Error message from pydantic-settings is already descriptive.
**Warning signs:** Existing deployments that haven't added the new env var will break on upgrade. Document in release notes.

## Code Examples

### scan_cache_dir() API Usage
```python
# Source: https://huggingface.co/docs/huggingface_hub/package_reference/cache
from huggingface_hub import scan_cache_dir

hf_cache_info = scan_cache_dir(cache_dir="/path/to/nfs/cache")
# hf_cache_info.repos is frozenset[CachedRepoInfo]
# Each CachedRepoInfo has:
#   .repo_id: str         (e.g. "meta-llama/Llama-3.1-8B-Instruct")
#   .repo_type: str       ("model", "dataset", "space")
#   .size_on_disk: int    (bytes)
#   .nb_files: int
#   .revisions: frozenset[CachedRevisionInfo]
# hf_cache_info.warnings is list[CorruptedCacheException]
```

### disable_progress_bars() API
```python
# Source: https://huggingface.co/docs/huggingface_hub/package_reference/utilities
from huggingface_hub.utils import disable_progress_bars

# Call once at startup, before any scan_cache_dir() calls
disable_progress_bars()
```

### Startup Configuration Pattern
```python
# In lifespan, before creating catalog service:
import os
os.environ["HF_HUB_DISABLE_XET"] = "1"  # D-08

from huggingface_hub.utils import disable_progress_bars
disable_progress_bars()  # D-10

# Validate cache_dir exists
cache_path = Path(resolved_settings.huggingface.cache_dir)
if not cache_path.is_dir():
    raise RuntimeError(
        f"HuggingFace cache directory does not exist: {cache_path}"
    )
```

### Admin Endpoint Pattern
```python
# Follows existing admin.py patterns
from inference_proxy.config.dependencies import get_catalog_service

@admin_router.get("/models/catalog")
async def list_catalog(
    catalog: ModelCatalogService = Depends(get_catalog_service),
) -> ModelCatalogResponse:
    models = await catalog.list_models()
    return ModelCatalogResponse(models=models)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual HF cache directory parsing | `scan_cache_dir()` API | huggingface_hub 0.8.0+ (2022) | Structured dataclass return, corruption handling |
| `requests` HTTP backend | `httpx` HTTP backend | huggingface_hub 1.0 (2025) | Library now uses httpx internally (same as this project) |
| No Xet storage | Xet chunk-based caching | huggingface_hub ~0.24+ | Must disable with `HF_HUB_DISABLE_XET=1` to avoid hangs |

**Deprecated/outdated:**
- `huggingface_hub.utils.CacheNotFound` -- may have moved to `huggingface_hub.errors.CacheNotFound` in recent versions. Import defensively or catch base exception. [ASSUMED]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `CacheNotFound` exception import path is `huggingface_hub.utils` or `huggingface_hub.errors` | Pitfall 1 | Low -- catch `Exception` at startup validation instead, or use `Path.is_dir()` pre-check |
| A2 | `scan_cache_dir()` with 20+ models on NFS completes in reasonable time (<5s) | Performance | Medium -- if slow, D-01 allows adding caching later |

## Open Questions

1. **CacheNotFound Import Path**
   - What we know: Official docs say `scan_cache_dir()` raises `CacheNotFound` when dir doesn't exist
   - What's unclear: Exact import location in v1.25 (may be `huggingface_hub.errors` or `huggingface_hub.utils`)
   - Recommendation: Pre-validate with `Path.is_dir()` check at startup instead of relying on the exception. Simpler, no import ambiguity.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 1.4+ |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/huggingface/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CFG-01 | HF API token configurable via env var | unit | `uv run pytest tests/config/test_settings.py -x -k huggingface` | No -- Wave 0 |
| CFG-02 | NFS cache dir configurable via env var | unit | `uv run pytest tests/config/test_settings.py -x -k huggingface` | No -- Wave 0 |
| CAT-01 | scan_cache_dir returns model repo IDs | unit | `uv run pytest tests/huggingface/test_catalog.py -x` | No -- Wave 0 |
| CAT-02 | GET /admin/models/catalog returns catalog | integration | `uv run pytest tests/api/test_admin.py -x -k catalog` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/huggingface/ tests/api/test_admin.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/huggingface/__init__.py` -- package init
- [ ] `tests/huggingface/test_catalog.py` -- covers CAT-01 (scan_cache_dir mock, model filtering)
- [ ] `tests/api/test_admin.py` -- extend with catalog endpoint tests for CAT-02
- [ ] `tests/config/test_settings.py` -- extend with HuggingFaceSettings tests for CFG-01, CFG-02

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | -- |
| V3 Session Management | no | -- |
| V4 Access Control | no | Internal network only, no auth on admin endpoints (existing pattern) |
| V5 Input Validation | yes | Pydantic model validation on response shapes; `cache_dir` path validated at startup |
| V6 Cryptography | no | -- |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via cache_dir config | Tampering | Env var set by operator (trusted), not user input. Validate path exists and is a directory. |
| API token exposure in logs | Information Disclosure | Use `SecretStr` for `api_token` (pydantic masks in repr/logs). Never log token value. |

## Sources

### Primary (HIGH confidence)
- [huggingface_hub cache guide](https://huggingface.co/docs/huggingface_hub/guides/manage-cache) -- scan_cache_dir usage, cache structure, HFCacheInfo/CachedRepoInfo fields
- [huggingface_hub cache reference](https://huggingface.co/docs/huggingface_hub/package_reference/cache) -- scan_cache_dir signature, data structure fields, CacheNotFound exception
- [huggingface_hub utilities reference](https://huggingface.co/docs/huggingface_hub/package_reference/utilities) -- disable_progress_bars() API, import path
- [PyPI huggingface-hub](https://pypi.org/project/huggingface-hub/) -- v1.25.1 latest, verified via `pip index versions`
- Existing codebase: `settings.py`, `dependencies.py`, `admin.py`, `main.py` -- verified patterns by reading source

### Secondary (MEDIUM confidence)
- slopcheck verification -- huggingface-hub rated [OK]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- single well-known dependency, verified on PyPI and slopcheck
- Architecture: HIGH -- follows 100% established codebase patterns (settings, DI, admin router, domain packages)
- Pitfalls: HIGH -- verified from official HF docs (CacheNotFound, XET, progress bars)

**Research date:** 2026-07-28
**Valid until:** 2026-08-28 (stable domain, no fast-moving pieces)
