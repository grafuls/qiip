# Phase 30: Foundation & Model Catalog — Research

**Researched:** 2026-07-28
**Status:** Complete

## huggingface_hub Library — scan_cache_dir()

`scan_cache_dir(cache_dir)` returns `HFCacheInfo` with `.repos` (frozenset of `CachedRepoInfo`).

Each `CachedRepoInfo` has:
- `.repo_id` (str) — e.g. `"meta-llama/Llama-3.1-8B-Instruct"`
- `.repo_type` — `"model"`, `"dataset"`, or `"space"`
- `.size_on_disk`, `.nb_files`, `.revisions` — available but not needed for Phase 30

**Key behaviors:**
- Filter by `repo_type == "model"` to exclude datasets/spaces from catalog
- Raises `CacheNotFound` if directory doesn't exist — validate at startup
- Synchronous I/O-bound call — must wrap in `asyncio.to_thread()` per D-01
- No network calls (purely local filesystem scan)

## Settings Pattern (from existing code)

Existing pattern in `inference_proxy/config/settings.py`:
- Nested `BaseModel` sub-configs: `QuadsSettings`, `RedfishSettings`, `LlmfitSettings`
- Env var convention: `INFERENCE_PROXY_{SECTION}__{KEY}`
- Optional features use `None` sentinel — but D-03 says `cache_dir` is **required** (no None guard)

**New settings:**
```
HuggingFaceSettings(BaseModel):
    cache_dir: str          # Required, INFERENCE_PROXY_HUGGINGFACE__CACHE_DIR
    api_token: str | None = None  # Optional, INFERENCE_PROXY_HUGGINGFACE__API_TOKEN
```

Wire into root `Settings` as `huggingface: HuggingFaceSettings`.

## Catalog Service Design

Per D-01 (on-demand scan) and D-02 (new package):

- `inference_proxy/huggingface/catalog.py` — `ModelCatalogService` class
- Constructor takes `cache_dir: str`
- `async def list_models() -> list[CatalogEntry]` — wraps `scan_cache_dir()` in `asyncio.to_thread()`
- `CatalogEntry` Pydantic model with `repo_id: str` per D-04 and D-05

## API Endpoint

Per D-05 and CAT-02:
- `GET /admin/models/catalog` → `{"models": [{"repo_id": "..."}]}`
- Added to existing `admin_router` in `inference_proxy/api/admin.py`
- Response model: `ModelCatalogResponse(BaseModel)` with `models: list[CatalogEntry]`

## Startup Configuration

Per D-08 and D-10:
- Set `HF_HUB_DISABLE_XET=1` in process environment at startup
- Call `huggingface_hub.utils.disable_progress_bars()` at startup
- Validate `cache_dir` path exists at startup (fail fast)

## Dependency Injection

Follow `inference_proxy/config/dependencies.py` pattern:
- Create `ModelCatalogService` in lifespan, store on `app.state.catalog_service`
- Add `get_catalog_service(request: Request) -> ModelCatalogService` dependency provider

## Files to Create/Modify

| Action | File | What |
|--------|------|------|
| Create | `inference_proxy/huggingface/__init__.py` | Package init |
| Create | `inference_proxy/huggingface/catalog.py` | CatalogEntry model + ModelCatalogService |
| Modify | `inference_proxy/config/settings.py` | Add HuggingFaceSettings |
| Modify | `inference_proxy/config/dependencies.py` | Add get_catalog_service() |
| Modify | `inference_proxy/api/admin.py` | Add catalog endpoint + response model |
| Modify | `inference_proxy/main.py` | Create service in lifespan, HF startup config |
| Modify | `.env.example` | Add HF env vars section |
| Create | `tests/test_catalog.py` | Unit + integration tests |

## Edge Cases

- Empty cache dir (no models downloaded yet) → return empty list
- Cache dir with only datasets/spaces → return empty list (filter by repo_type)
- Missing cache dir at startup → fail fast with clear error
- NFS mount not available → `scan_cache_dir` raises `CacheNotFound`

## Dependencies

- `huggingface-hub >=1.25, <2.0` (per D-06) — provides `scan_cache_dir()`, `disable_progress_bars()`
- No other new dependencies needed

## RESEARCH COMPLETE
