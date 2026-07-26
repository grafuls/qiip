# Phase 27: Admin API Endpoint - Research

**Researched:** 2026-07-26
**Domain:** FastAPI endpoint wiring, error mapping, DI integration
**Confidence:** HIGH

## Summary

This phase adds a single GET endpoint to the existing admin router, wires an already-built `LLMFitRunner` via DI, maps its error hierarchy to HTTP 502 responses, and optionally introduces `LLMFitSettings` for configurable timeout/binary path. Zero new dependencies. Zero new architectural patterns. Every building block exists in the codebase.

The endpoint follows the exact pattern established by the Redfish power endpoints: validate hostname, call an injected service, catch domain errors and map to `HTTPException(502)`, return a typed Pydantic response. The only design decision is the error response body shape (D-02 wants `error_type` + `detail` rather than plain `detail`).

**Primary recommendation:** Follow the Redfish power endpoint pattern verbatim. Add `get_llmfit_runner()` to dependencies.py, create runner in lifespan, add endpoint to admin_router. Total new code is under 100 lines across 4-5 files.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Raw llmfit output is NOT exposed in API error responses. Raw output stays in server logs only (structlog). API response contains the error type and a human-readable message.
- **D-02:** Error responses include an `error_type` field classifying the failure: `timeout`, `ssh_error`, `parse_error`, `connection_error`. Allows dashboard JS (Phase 29) to show different messaging per failure type.
- **D-03:** All llmfit failures return HTTP 502 (Bad Gateway). Treats llmfit as an upstream dependency, same pattern as Redfish errors in `admin.py`. No distinction between SSH errors and parse errors at the HTTP status level.

### Claude's Discretion
- **Runner wiring:** Follow existing DI pattern -- `get_llmfit_runner()` in `dependencies.py`, runner stored in `app.state.llmfit_runner`. Created during lifespan.
- **LLMFitSettings:** Add to `config/settings.py` if configurability is needed (D-06 from Phase 25). At minimum: timeout and binary path as env vars with current hardcoded defaults. Only add settings that the runner already uses -- no speculative config.
- **Response model:** Create a response Pydantic model in `models/admin.py` (or `models/llmfit.py`) that wraps `LLMFitResult` with the hostname. Follow existing admin response model patterns.
- **Node validation:** Follow the `_validated_hostname()` pattern already in `admin.py`. No requirement for the node to be in etcd registry -- operators may want recommendations for any SSH-reachable host.
- **Error response model:** Create an error response model with `error_type` and `detail` fields. Catch `LLMFitError` hierarchy + SSH errors in the endpoint handler and map to appropriate error types.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | Admin API endpoint `GET /admin/nodes/{hostname}/recommendations` returns ranked model recommendations | Endpoint follows Redfish power endpoint pattern in `admin.py`. `LLMFitRunner.recommend()` already returns `LLMFitResult` with ranked `models` list. |
| API-02 | Endpoint returns detected hardware info (GPU VRAM, GPU name, backend) alongside recommendations | `LLMFitResult.system` field contains `SystemInfo` with `gpu_name`, `gpu_vram_gb`, `backend`. Response model wraps this directly. |
| API-03 | llmfit failures return structured error response (not 500) | Catch `LLMFitTimeoutError`, `LLMFitParseError`, `SSHConnectionError`, `RemoteCommandError` in handler. Map to HTTP 502 with `error_type` + `detail` per D-01/D-02/D-03. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Recommendation endpoint | API / Backend | -- | Pure REST endpoint, no frontend involvement |
| Error mapping (llmfit -> HTTP) | API / Backend | -- | Handler-level concern, translates domain errors to HTTP responses |
| LLMFitRunner wiring | API / Backend | -- | DI provider + lifespan init, backend-only |
| LLMFitSettings config | API / Backend | -- | pydantic-settings env var loading, backend-only |
| Hardware info in response | API / Backend | -- | Data already in LLMFitResult.system, just serialized |

## Standard Stack

No new packages. This phase uses only what is already installed.

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.135 | HTTP framework, admin_router | Already the framework. Endpoint is 1 function. |
| Pydantic | >=2.10 | Response/error models | Already used for all models. |
| structlog | >=26.1.0 | Error logging (raw output) | Already used throughout. |
| pydantic-settings | >=2.14 | LLMFitSettings | Already used for all settings sub-models. |

### Supporting (already installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=8.0 | Tests | Endpoint integration tests |
| pytest-asyncio | >=1.4 | Async test support | Runner is async |

No `npm install` or `pip install` needed.

## Architecture Patterns

### System Architecture Diagram

```
Operator (curl / dashboard JS)
        |
        | GET /admin/nodes/{hostname}/recommendations
        v
  [FastAPI admin_router]
        |
        | Depends(get_llmfit_runner)
        v
  [LLMFitRunner.recommend(hostname)]
        |
        | SSHClient.run() over SSH
        v
  [Remote host: llmfit binary]
        |
        | JSON stdout
        v
  [Pydantic parse -> LLMFitResult]
        |
        v
  [RecommendationResponse] --> 200 JSON
        or
  [LLMFitError / SSHError] --> 502 JSON {error_type, detail}
```

### Recommended Project Structure

No new directories. Files touched:

```
inference_proxy/
├── api/admin.py              # + 1 new endpoint function (~25 lines)
├── config/
│   ├── dependencies.py        # + get_llmfit_runner() (~5 lines)
│   └── settings.py            # + LLMFitSettings class (~10 lines)
├── main.py                    # + LLMFitRunner init in lifespan (~5 lines)
└── models/
    └── admin.py               # + RecommendationResponse, LLMFitErrorResponse (~20 lines)
tests/
└── api/test_admin.py          # + recommendation endpoint tests (~100 lines)
```

### Pattern 1: Redfish Error Mapping (the template)

**What:** Existing pattern in `admin.py` for mapping domain errors to HTTP responses.
**When to use:** Exactly this situation -- llmfit is an upstream dependency like Redfish BMC.
**Example:**
```python
# Source: inference_proxy/api/admin.py lines 237-250 (existing code)
@admin_router.get("/nodes/{hostname}/power")
async def get_power_state(
    hostname: str,
    redfish: RedfishClient | None = Depends(get_redfish_client),
) -> PowerStateResponse:
    if redfish is None:
        raise HTTPException(status_code=503, detail="Redfish not configured")
    hostname = _validated_hostname(hostname)
    try:
        state = await redfish.get_power_state(hostname)
    except RedfishError as exc:
        raise HTTPException(status_code=502, detail=exc.human_message) from exc
    return PowerStateResponse(hostname=hostname, power_state=state)
```

### Pattern 2: Error Response with error_type (D-02)

**What:** D-02 requires `error_type` in the response body, but FastAPI's `HTTPException` only supports a `detail` field by default. Two approaches:
**Option A (recommended):** Use `JSONResponse` directly with status 502, bypassing HTTPException. This is simpler and gives full control over the body shape.
**Option B:** Use HTTPException with `detail` as a dict containing both fields. FastAPI serializes dicts in `detail` as JSON.

```python
# Option A -- JSONResponse (cleaner, matches D-02 exactly)
from fastapi.responses import JSONResponse

except LLMFitTimeoutError as exc:
    logger.warning("llmfit_timeout", host=hostname, timeout=exc.timeout)
    return JSONResponse(
        status_code=502,
        content={"error_type": "timeout", "detail": str(exc)},
    )

# Option B -- HTTPException with dict detail (simpler, less explicit)
except LLMFitTimeoutError as exc:
    raise HTTPException(
        status_code=502,
        detail={"error_type": "timeout", "detail": str(exc)},
    ) from exc
```

**Recommendation:** Option A (JSONResponse). It makes the response body explicit and avoids FastAPI's default error schema wrapping. But Option B also works fine -- HTTPException with a dict `detail` serializes correctly.

### Pattern 3: DI Provider (existing pattern)

**What:** All services use `app.state.*` + a `get_*()` function in `dependencies.py`.
**Example:**
```python
# Source: inference_proxy/config/dependencies.py (existing pattern)
def get_llmfit_runner(request: Request) -> LLMFitRunner:
    """Return the LLMFit runner from application state."""
    return request.app.state.llmfit_runner  # type: ignore[no-any-return]
```

### Pattern 4: Settings Sub-model (existing pattern)

**What:** Nested BaseModel in settings.py with env var defaults.
**Example:**
```python
# Source: inference_proxy/config/settings.py (follows SSHSettings pattern)
class LLMFitSettings(BaseModel):
    """LLMFit execution configuration."""
    binary_path: str = "/usr/local/bin/llmfit"
    timeout: float = 60.0

# In Settings class:
class Settings(BaseSettings):
    ...
    llmfit: LLMFitSettings = LLMFitSettings()
```

Env vars: `INFERENCE_PROXY_LLMFIT__BINARY_PATH`, `INFERENCE_PROXY_LLMFIT__TIMEOUT`.

### Anti-Patterns to Avoid
- **Creating a separate router for recommendations:** The endpoint belongs on `admin_router` alongside power/setup/teardown. No new router file.
- **Wrapping SSH errors in LLMFitError:** D-03 from Phase 25 says SSH errors bubble unchanged. The endpoint handler catches them separately and maps to `error_type: "ssh_error"` or `"connection_error"`.
- **Adding query parameters (--limit, --use-case):** Deferred to future milestone (FILT-01/02/03 in REQUIREMENTS.md). This phase is the bare endpoint.
- **Requiring node to be in etcd registry:** CONTEXT.md explicitly says operators may want recommendations for any SSH-reachable host.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hostname validation | Custom regex parser | `_validated_hostname()` in admin.py | Already handles normalization + length + pattern check |
| SSH execution | Direct asyncssh calls | `LLMFitRunner.recommend()` | Already built in Phase 25, DI-injected |
| JSON parsing + validation | Manual dict traversal | `LLMFitResult.model_validate()` | Already built in Phase 25 with `extra="ignore"` |
| Settings env vars | os.environ / dotenv | pydantic-settings `LLMFitSettings` | Existing pattern, type-safe, validating |

## Common Pitfalls

### Pitfall 1: Forgetting to catch RemoteCommandError
**What goes wrong:** `LLMFitRunner.recommend()` can raise `RemoteCommandError` (non-zero exit) in addition to `SSHConnectionError`. If only `LLMFitError` subclasses and `SSHConnectionError` are caught, `RemoteCommandError` becomes a 500.
**Why it happens:** `RemoteCommandError` is not in the `LLMFitError` hierarchy -- it bubbles from SSHClient per D-03.
**How to avoid:** Catch both `SSHConnectionError` and `RemoteCommandError` explicitly in the handler.
**Warning signs:** Unhandled exception in test for non-zero exit status.

### Pitfall 2: JSONResponse skips response_model validation
**What goes wrong:** If using `JSONResponse` directly (Option A), FastAPI does not validate the response against a `response_model` type hint. The error response shape is whatever you put in `content=`.
**Why it happens:** `JSONResponse` bypasses Pydantic serialization.
**How to avoid:** For the success path, use a return type annotation (`-> RecommendationResponse`) so FastAPI validates the happy path. For error paths, the typed `content` dict is fine since it is a simple {error_type, detail} shape.
**Warning signs:** None -- this is acceptable for error responses. Just document the error response schema in `responses={}` on the decorator.

### Pitfall 3: Missing LLMFitRunner in test conftest
**What goes wrong:** The test `app` fixture does not set `app.state.llmfit_runner` or override `get_llmfit_runner`, causing `AttributeError` in tests.
**Why it happens:** New DI provider not added to the test fixture setup.
**How to avoid:** Add mock runner to conftest `app` fixture alongside existing mock_provisioner pattern.
**Warning signs:** All new recommendation tests fail with AttributeError.

### Pitfall 4: Not updating .env.example
**What goes wrong:** New `INFERENCE_PROXY_LLMFIT__*` env vars exist in code but not in `.env.example`.
**Why it happens:** Convention from CLAUDE.md requires updating `.env.example` when env vars change.
**How to avoid:** Add commented-out LLMFIT entries to `.env.example` alongside other settings.
**Warning signs:** Linting step or code review catches missing documentation.

## Code Examples

### Endpoint Implementation (verified pattern from codebase)

```python
# Source: follows admin.py Redfish pattern exactly
@admin_router.get(
    "/nodes/{hostname}/recommendations",
    response_model=RecommendationResponse,
    responses={502: {"description": "LLMFit or SSH failure"}},
)
async def get_recommendations(
    hostname: str,
    runner: LLMFitRunner = Depends(get_llmfit_runner),
) -> RecommendationResponse | JSONResponse:
    hostname = _validated_hostname(hostname)
    try:
        result = await runner.recommend(hostname)
    except LLMFitTimeoutError as exc:
        logger.warning("llmfit_timeout", host=hostname, timeout=exc.timeout)
        return JSONResponse(
            status_code=502,
            content={"error_type": "timeout", "detail": str(exc)},
        )
    except LLMFitParseError as exc:
        logger.warning("llmfit_parse_error", host=hostname, reason=exc.reason,
                        raw_output=exc.raw_output)  # D-01: raw in logs only
        return JSONResponse(
            status_code=502,
            content={"error_type": "parse_error", "detail": f"Failed to parse llmfit output: {exc.reason}"},
        )
    except SSHConnectionError as exc:
        logger.warning("llmfit_ssh_error", host=hostname, reason=exc.reason)
        return JSONResponse(
            status_code=502,
            content={"error_type": "connection_error", "detail": f"SSH connection failed: {exc.reason}"},
        )
    except RemoteCommandError as exc:
        logger.warning("llmfit_command_error", host=hostname,
                        exit_status=exc.exit_status)
        return JSONResponse(
            status_code=502,
            content={"error_type": "ssh_error", "detail": f"llmfit exited with status {exc.exit_status}"},
        )
    return RecommendationResponse(hostname=hostname, system=result.system, models=result.models)
```

### Response Model

```python
# Source: follows models/admin.py PowerStateResponse pattern
class RecommendationResponse(BaseModel):
    """Response for GET /admin/nodes/{hostname}/recommendations."""
    model_config = ConfigDict(frozen=True)

    hostname: str
    system: SystemInfo
    models: list[ModelRecommendation]
```

### LLMFitSettings

```python
# Source: follows settings.py SSHSettings / RedfishSettings pattern
class LLMFitSettings(BaseModel):
    """LLMFit execution configuration."""
    binary_path: str = "/usr/local/bin/llmfit"
    timeout: float = 60.0
```

### Lifespan Wiring

```python
# Source: follows main.py provisioner / redfish init pattern
from inference_proxy.llmfit.runner import LLMFitRunner

# In lifespan, after ssh_client is created:
llmfit_runner = LLMFitRunner(ssh_client=ssh_client)
app.state.llmfit_runner = llmfit_runner
```

### Test Fixture Addition

```python
# Source: follows conftest.py mock_provisioner pattern
# In app fixture:
mock_llmfit_runner = MagicMock(spec=LLMFitRunner)
mock_llmfit_runner.recommend = AsyncMock()
application.state.llmfit_runner = mock_llmfit_runner
application.dependency_overrides[get_llmfit_runner] = lambda: mock_llmfit_runner

# Separate fixture:
@pytest.fixture
def mock_llmfit_runner(app: FastAPI) -> MagicMock:
    return app.state.llmfit_runner
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `sse-starlette` for SSE | FastAPI built-in `EventSourceResponse` | FastAPI 0.135 | Not relevant to this phase (no SSE) |
| Manual error dict in HTTPException | JSONResponse for typed error bodies | Always available | Gives full control over error shape without HTTPException wrapping |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `LLMFitRunner` constructor only needs `SSHClient` (no settings injection yet) | Code Examples | LOW -- verified by reading runner.py; if settings are added, constructor signature changes but pattern is the same |
| A2 | JSONResponse approach is preferred over HTTPException for typed error bodies | Architecture Patterns | LOW -- both work; if team prefers HTTPException with dict detail, it is a 1-line change per error branch |

## Open Questions

1. **Should LLMFitSettings be injected into LLMFitRunner constructor?**
   - What we know: Runner currently hardcodes `_BINARY`, `_COMMAND`, `_TIMEOUT` as class variables (lines 30-32 of runner.py).
   - What's unclear: Whether to refactor Runner to accept settings or just update the class variables from settings at construction time.
   - Recommendation: Pass settings to constructor, replace class variables. Keeps Runner testable with different configs. Minimal diff since only timeout and binary_path need extracting.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/api/test_admin.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | GET /admin/nodes/{hostname}/recommendations returns 200 with ranked models | integration | `uv run pytest tests/api/test_admin.py::TestRecommendations::test_returns_200_with_models -x` | Wave 0 |
| API-01 | Response includes hostname in output | integration | `uv run pytest tests/api/test_admin.py::TestRecommendations::test_response_includes_hostname -x` | Wave 0 |
| API-02 | Response includes system hardware info | integration | `uv run pytest tests/api/test_admin.py::TestRecommendations::test_response_includes_hardware -x` | Wave 0 |
| API-03 | Timeout returns 502 with error_type=timeout | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_timeout_returns_502 -x` | Wave 0 |
| API-03 | Parse error returns 502 with error_type=parse_error | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_parse_error_returns_502 -x` | Wave 0 |
| API-03 | SSH connection error returns 502 with error_type=connection_error | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_ssh_error_returns_502 -x` | Wave 0 |
| API-03 | Remote command error returns 502 with error_type=ssh_error | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_command_error_returns_502 -x` | Wave 0 |
| D-01 | Raw output NOT in API error response | integration | `uv run pytest tests/api/test_admin.py::TestRecommendationErrors::test_raw_output_not_exposed -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/api/test_admin.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/api/test_admin.py` -- add TestRecommendations + TestRecommendationErrors classes (file exists, classes are new)
- [ ] `tests/conftest.py` -- add mock_llmfit_runner fixture + app fixture wiring

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Internal network only (v1 constraint) |
| V3 Session Management | no | Stateless API |
| V4 Access Control | no | No auth in v1 (internal network) |
| V5 Input Validation | yes | `_validated_hostname()` -- regex + length check on path parameter |
| V6 Cryptography | no | No crypto operations |

### Known Threat Patterns for this endpoint

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Hostname injection (path traversal via hostname) | Tampering | `_validated_hostname()` regex blocks special chars |
| Information leakage via raw llmfit output | Information Disclosure | D-01: raw output in logs only, not API response |
| SSRF via arbitrary hostname SSH | Spoofing | Accepted risk for v1 (internal network, operators only). Future: allowlist. |

## Sources

### Primary (HIGH confidence)
- `inference_proxy/api/admin.py` -- existing endpoint patterns, `_validated_hostname()`, Redfish error mapping (lines 237-267)
- `inference_proxy/llmfit/runner.py` -- LLMFitRunner API surface, exception contract
- `inference_proxy/llmfit/errors.py` -- error hierarchy: LLMFitError -> LLMFitTimeoutError, LLMFitParseError
- `inference_proxy/provisioning/ssh_client.py` -- SSHConnectionError, RemoteCommandError (lines 22-47)
- `inference_proxy/models/llmfit.py` -- LLMFitResult, SystemInfo, ModelRecommendation
- `inference_proxy/models/admin.py` -- response model patterns (ConfigDict(frozen=True))
- `inference_proxy/config/dependencies.py` -- DI provider pattern
- `inference_proxy/config/settings.py` -- settings sub-model pattern
- `inference_proxy/main.py` -- lifespan init pattern
- `tests/conftest.py` -- test fixture wiring pattern
- `tests/api/test_admin.py` -- integration test patterns
- `tests/llmfit/test_runner.py` -- runner unit test patterns, FIXTURE_JSON

### Secondary (MEDIUM confidence)
- `.planning/phases/25-core-models-and-runner/25-CONTEXT.md` -- D-03 (SSH errors bubble unchanged), D-06 (deferred LLMFitSettings)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all patterns verified from codebase
- Architecture: HIGH -- direct copy of Redfish endpoint pattern
- Pitfalls: HIGH -- derived from reading actual code and test fixtures

**Research date:** 2026-07-26
**Valid until:** 2026-08-26 (stable -- no external deps, internal patterns only)
