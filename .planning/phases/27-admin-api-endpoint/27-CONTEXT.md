# Phase 27: Admin API Endpoint - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase adds `GET /admin/nodes/{hostname}/recommendations` to the admin API. The endpoint runs llmfit on a remote host via `LLMFitRunner`, returns typed recommendations with hardware info, and returns structured error responses on failure. No dashboard UI, no query parameters, no settings UI — just the API endpoint with proper error handling.

</domain>

<decisions>
## Implementation Decisions

### Error Response Format
- **D-01:** Raw llmfit output is NOT exposed in API error responses. Raw output stays in server logs only (structlog). API response contains the error type and a human-readable message.
- **D-02:** Error responses include an `error_type` field classifying the failure: `timeout`, `ssh_error`, `parse_error`, `connection_error`. Allows dashboard JS (Phase 29) to show different messaging per failure type.
- **D-03:** All llmfit failures return HTTP 502 (Bad Gateway). Treats llmfit as an upstream dependency, same pattern as Redfish errors in `admin.py`. No distinction between SSH errors and parse errors at the HTTP status level.

### Claude's Discretion
- **Runner wiring:** Follow existing DI pattern — `get_llmfit_runner()` in `dependencies.py`, runner stored in `app.state.llmfit_runner`. Created during lifespan.
- **LLMFitSettings:** Add to `config/settings.py` if configurability is needed (D-06 from Phase 25). At minimum: timeout and binary path as env vars with current hardcoded defaults. Only add settings that the runner already uses — no speculative config.
- **Response model:** Create a response Pydantic model in `models/admin.py` (or `models/llmfit.py`) that wraps `LLMFitResult` with the hostname. Follow existing admin response model patterns.
- **Node validation:** Follow the `_validated_hostname()` pattern already in `admin.py`. No requirement for the node to be in etcd registry — operators may want recommendations for any SSH-reachable host.
- **Error response model:** Create an error response model with `error_type` and `detail` fields. Catch `LLMFitError` hierarchy + SSH errors in the endpoint handler and map to appropriate error types.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Admin API
- `inference_proxy/api/admin.py` — Admin router with endpoint patterns, `_validated_hostname()`, DI via `Depends()`, HTTPException error handling. New endpoint goes here.

### LLMFit Layer (Phase 25)
- `inference_proxy/llmfit/runner.py` — `LLMFitRunner.recommend(hostname)` returns `LLMFitResult`. Constructor-injected `SSHClient`.
- `inference_proxy/llmfit/errors.py` — `LLMFitError` → `LLMFitTimeoutError`, `LLMFitParseError`. SSH errors bubble unchanged.
- `inference_proxy/models/llmfit.py` — `LLMFitResult`, `SystemInfo`, `ModelRecommendation` Pydantic models.

### DI and Configuration
- `inference_proxy/config/dependencies.py` — DI providers using `app.state.*`. Add `get_llmfit_runner()` here.
- `inference_proxy/config/settings.py` — Nested settings with env var defaults. Add `LLMFitSettings` if needed.

### SSH Layer
- `inference_proxy/provisioning/ssh_client.py` — `SSHClient` with `run()` method, typed errors (`SSHConnectionError`, `RemoteCommandError`).

### Response Models
- `inference_proxy/models/admin.py` — Existing admin response models (pattern reference for new recommendation response model).

### Requirements
- `.planning/REQUIREMENTS.md` — API-01, API-02, API-03 map to this phase.

### Prior Phase Context
- `.planning/phases/25-core-models-and-runner/25-CONTEXT.md` — D-04 (raw output in parse errors), D-05 (hardcoded flags), D-06 (deferred LLMFitSettings).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LLMFitRunner` (`inference_proxy/llmfit/runner.py`): Fully built. `recommend(hostname)` → `LLMFitResult`. Just needs wiring.
- `_validated_hostname()` (`inference_proxy/api/admin.py`): Hostname normalization + validation. Reuse for the new endpoint.
- `admin_router` (`inference_proxy/api/admin.py`): Add the new route to existing router.
- Error hierarchy (`inference_proxy/llmfit/errors.py`): `LLMFitTimeoutError`, `LLMFitParseError` ready for catch blocks.

### Established Patterns
- DI via `Depends(get_*)` functions reading from `app.state.*`
- `HTTPException` for error responses (but D-02 wants typed error body — may need a custom response instead)
- Admin endpoints return Pydantic response models
- Redfish errors use 502 with `exc.human_message` as detail

### Integration Points
- `inference_proxy/api/admin.py` — New `GET` route on `admin_router`
- `inference_proxy/config/dependencies.py` — New `get_llmfit_runner()` provider
- `inference_proxy/main.py` — `LLMFitRunner` initialization in lifespan (if stored in `app.state`)
- `inference_proxy/config/settings.py` — Optional `LLMFitSettings` nested model

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Follow existing admin.py patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 27-Admin API Endpoint*
*Context gathered: 2026-07-26*
