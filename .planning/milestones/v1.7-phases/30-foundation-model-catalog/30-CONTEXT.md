# Phase 30: Foundation & Model Catalog - Context

**Gathered:** 2026-07-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Gateway discovers which models are already downloaded on NFS storage. Adds HuggingFace configuration (API token, NFS cache path), a catalog service that scans NFS via `scan_cache_dir()`, and an admin API endpoint returning the catalog.

</domain>

<decisions>
## Implementation Decisions

### Catalog Scan Strategy
- **D-01:** On-demand scan per API request — wrap `scan_cache_dir()` in `asyncio.to_thread()` on each `GET /admin/models/catalog` call. No background thread, no cached state. Add caching later only if NFS latency becomes a measured problem.
- **D-02:** New `inference_proxy/huggingface/` package — `catalog.py` for the catalog service. Follows the domain-package pattern of `quads/`, `llmfit/`, `redfish/`. Phase 31 download service joins the same package.
- **D-03:** Always-on with required `cache_dir` — NFS cache path is required configuration (gateway won't start without it). HF API token is optional (only needed for gated model downloads in Phase 31). No `None` guard pattern.

### Catalog Response Shape
- **D-04:** Repo ID only per catalog entry — no size, last_modified, or file count. Minimal response matching CAT-01 requirement.
- **D-05:** Objects with `repo_id` field, not flat strings — response is a list of `{"repo_id": "meta-llama/..."}` objects. Extensible without breaking clients when fields are added later.

### Prior Research (locked from v1.7 research)
- **D-06:** Single new dependency: `huggingface-hub >=1.25, <2.0`
- **D-07:** Must use `cache_dir=` parameter (not `local_dir=`) for HF cache layout compatible with vLLM
- **D-08:** `HF_HUB_DISABLE_XET=1` env var set at startup to avoid hang issues
- **D-09:** llmfit model name IS the HF `repo_id` — zero mapping needed between llmfit recommendations and HF downloads
- **D-10:** `disable_progress_bars()` at startup for thread safety

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — project overview, constraints, key decisions
- `.planning/REQUIREMENTS.md` — v1.7 requirements (CFG-01, CFG-02, CAT-01, CAT-02 map to this phase)
- `.planning/ROADMAP.md` — phase 30 success criteria and phase dependencies

### Existing Patterns
- `inference_proxy/config/settings.py` — settings sub-model pattern (add `HuggingFaceSettings`)
- `inference_proxy/config/dependencies.py` — dependency injection pattern (`app.state` + `get_X()`)
- `inference_proxy/api/admin.py` — admin router pattern for new endpoints
- `inference_proxy/quads/client.py` — domain-package pattern to follow
- `inference_proxy/llmfit/runner.py` — sync-to-async wrapping pattern

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Settings` class with nested `BaseModel` sub-configs: add `HuggingFaceSettings` sub-model
- `admin_router` in `api/admin.py`: add `GET /admin/models/catalog` endpoint
- `config/dependencies.py`: add `get_catalog_service()` dependency provider

### Established Patterns
- Nested settings: each domain has a `BaseModel` sub-config in `settings.py` with `INFERENCE_PROXY_{SECTION}__{KEY}` env vars
- Optional features: `None` sentinel for opt-in features (QUADS, Redfish) — NOT used here, cache_dir is required
- Domain packages: `quads/`, `llmfit/`, `redfish/` each have their own package — new `huggingface/` follows this
- Dependency injection: services created in lifespan, stored on `app.state`, exposed via `get_X()` functions

### Integration Points
- `inference_proxy/config/settings.py` — add `HuggingFaceSettings` and wire into root `Settings`
- `inference_proxy/config/dependencies.py` — add `get_catalog_service()` provider
- `inference_proxy/api/admin.py` — add catalog endpoint
- `inference_proxy/main.py` — create catalog service in lifespan, store on `app.state`
- `.env.example` — add HF settings section

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

*Phase: 30-Foundation & Model Catalog*
*Context gathered: 2026-07-28*
