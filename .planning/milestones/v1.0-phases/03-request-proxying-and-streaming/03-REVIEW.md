---
phase: 03-request-proxying-and-streaming
reviewed: 2026-06-11T18:45:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - inference_proxy/api/errors.py
  - inference_proxy/api/routes.py
  - inference_proxy/config/dependencies.py
  - inference_proxy/config/settings.py
  - inference_proxy/main.py
  - inference_proxy/proxy/client.py
  - inference_proxy/proxy/node_selector.py
  - tests/api/test_errors.py
  - tests/api/test_routes.py
  - tests/conftest.py
  - tests/proxy/test_client.py
  - tests/proxy/test_node_selector.py
  - tests/test_app.py
findings:
  critical: 3
  warning: 5
  info: 2
  total: 10
status: issues_found
---

# Phase 03: Code Review Report

**Reviewed:** 2026-06-11T18:45:00Z
**Depth:** standard
**Files Reviewed:** 13 (7 production, 6 test)
**Status:** issues_found

## Summary

Phase 3 implements request proxying and SSE streaming for the OpenAI-compatible gateway. The overall structure is sound: clean dependency injection, SOLID-compliant module boundaries, proper use of `format_sse_event` to avoid double JSON encoding, and good test coverage.

However, the review found three critical issues: (1) streaming errors are silently swallowed, leaving clients with truncated SSE streams and no error indication; (2) `response.json()` can crash on non-JSON backend responses, masking the real upstream error; and (3) the httpx.AsyncClient created in the test fixture is never closed, leaking connections across the test suite.

## Critical Issues

### CR-01: Streaming errors silently swallowed -- client receives truncated stream with no error signal

**File:** `inference_proxy/api/routes.py:185-190`
**Issue:** When an exception occurs during SSE streaming (backend disconnect, HTTP status error from `raise_for_status()`, network failure), the `except Exception` block logs the error but yields nothing to the client. The async generator simply ends, and the client receives a truncated SSE stream without a `[DONE]` signal or any error indication. OpenAI-compatible clients will hang or timeout waiting for more data.

This is particularly dangerous because `raise_for_status()` on line 179 will throw `httpx.HTTPStatusError` if the backend returns 4xx/5xx, and the client gets an empty SSE response with a 200 status code -- a completely misleading result.

**Fix:**
```python
async def event_generator() -> AsyncGenerator[bytes, None]:
    try:
        async with aconnect_sse(
            proxy.client, "POST", url, json=body
        ) as event_source:
            event_source.response.raise_for_status()
            async for sse in event_source.aiter_sse():
                if sse.data == "[DONE]":
                    yield format_sse_event(data_str="[DONE]")
                    break
                yield format_sse_event(data_str=sse.data)
    except Exception as exc:
        logger.error(
            "streaming proxy error",
            error=str(exc),
            url=url,
        )
        # Emit an SSE error event so the client knows the stream failed,
        # then terminate with [DONE] so clients don't hang.
        _, error_resp = map_proxy_error(exc)
        yield format_sse_event(
            data_str=error_resp.model_dump_json(),
            event="error",
        )
        yield format_sse_event(data_str="[DONE]")
```

### CR-02: `response.json()` crashes on non-JSON backend responses

**File:** `inference_proxy/api/routes.py:68` (and duplicated at line 105)
**Issue:** `response.json()` calls `json.loads()` on the response body. If the vLLM backend returns a non-JSON response (HTML error page, plain text, empty body, or a 204 No Content), this throws `json.JSONDecodeError`. The exception is caught by the outer `except Exception` on line 71/109 and mapped to a generic 500 "Internal gateway error" -- losing the actual upstream status code and response content.

A backend returning `422 Unprocessable Entity` with a plain-text body would appear to the client as a `500 Internal gateway error` instead of the real 422.

**Fix:**
```python
try:
    response = await proxy.forward("POST", url, body)
    try:
        content = response.json()
    except (ValueError, UnicodeDecodeError):
        content = {"error": {"message": response.text, "type": "upstream_error", "code": str(response.status_code)}}
    return JSONResponse(
        content=content,
        status_code=response.status_code,
    )
except Exception as exc:
    status, error_resp = map_proxy_error(exc)
    return JSONResponse(content=error_resp.model_dump(), status_code=status)
```

### CR-03: Test fixture leaks httpx.AsyncClient -- never closed

**File:** `tests/conftest.py:41-43`
**Issue:** The `mock_http_client` fixture creates `httpx.AsyncClient()` but never calls `aclose()`. httpx logs a `ResourceWarning` for unclosed clients, and the underlying connection pool is leaked for every test that uses this fixture. Over a large test suite run, this accumulates file descriptors.

**Fix:**
```python
@pytest.fixture
async def mock_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    client = httpx.AsyncClient()
    yield client
    await client.aclose()
```

Or since conftest uses synchronous fixtures and TestClient manages its own event loop, use the sync pattern:

```python
@pytest.fixture
def mock_http_client() -> Generator[httpx.AsyncClient, None, None]:
    client = httpx.AsyncClient()
    yield client
    # httpx.AsyncClient.aclose() must be awaited, but in sync fixture context
    # we rely on garbage collection. Alternative: use httpx.Client for tests
    # or restructure to async fixture.
```

The cleanest fix is to make this an async fixture with proper cleanup.

## Warnings

### WR-01: Code duplication between `chat_completions` and `text_completions` handlers

**File:** `inference_proxy/api/routes.py:38-73` and `inference_proxy/api/routes.py:76-111`
**Issue:** The two endpoint handlers are nearly identical -- same node selection, same error handling, same forwarding logic. Only the Pydantic model type and URL path differ. This violates the DRY principle and means any bug fix (like CR-02) must be applied in two places. The `_stream_completion` function already demonstrates the correct factoring pattern (parameterized by `endpoint_path`).

**Fix:** Extract a shared `_forward_completion(endpoint_path, body, registry, proxy)` function mirroring the streaming function pattern:
```python
async def _forward_completion(
    endpoint_path: str,
    body: dict,
    registry: NodeRegistry,
    proxy: ProxyClient,
) -> JSONResponse:
    node = select_node(registry)
    if node is None:
        status, error_resp = no_nodes_error()
        return JSONResponse(content=error_resp.model_dump(), status_code=status)
    url = f"http://{node.endpoint}{endpoint_path}"
    try:
        response = await proxy.forward("POST", url, body)
        return JSONResponse(content=response.json(), status_code=response.status_code)
    except Exception as exc:
        status, error_resp = map_proxy_error(exc)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)
```

### WR-02: Information disclosure via `HTTPStatusError` mapping passes raw backend response text to client

**File:** `inference_proxy/api/errors.py:54-59`
**Issue:** When the vLLM backend returns an HTTP error, `exc.response.text` is embedded verbatim in the error message returned to the client. While the threat model accepts this for internal network use, the response text could contain stack traces, internal paths, or debug information from the vLLM backend that should not be relayed to API consumers. This is an information disclosure risk if the network boundary assumptions change.

**Fix:** Truncate or sanitize the response text:
```python
response_text = exc.response.text[:500] if exc.response.text else "Unknown error"
return status, ErrorResponse(
    error=ErrorDetail(
        message=f"Inference backend returned error: {response_text}",
        type="upstream_error",
        code=str(status),
    )
)
```

### WR-03: `_stream_completion` returns `EventSourceResponse` with 200 status even when upstream returns error status

**File:** `inference_proxy/api/routes.py:174-192`
**Issue:** If `raise_for_status()` (line 179) throws because the upstream returned a 4xx/5xx status, the `except` block catches it, and the function returns the `EventSourceResponse` that was already created with status_code=200 (default). The client sees a 200 response with an empty body (or just the error event if CR-01 is fixed). The HTTP status code of the response should reflect the upstream error.

An alternative approach is to check the response status *before* starting the SSE response, returning a regular JSONResponse for error statuses:
```python
async def event_generator() -> AsyncGenerator[bytes, None]:
    async with aconnect_sse(
        proxy.client, "POST", url, json=body
    ) as event_source:
        # Check status before streaming
        if event_source.response.status_code >= 400:
            # This is too late -- EventSourceResponse is already committed
            ...
```

Since HTTP status must be set before streaming begins, consider restructuring: make the initial connection and status check *outside* the generator, and only start the EventSourceResponse if the upstream returns 2xx.

### WR-04: `health()` endpoint accesses `application.state.registry` directly instead of through dependency injection

**File:** `inference_proxy/main.py:150`
**Issue:** The health endpoint at line 150 reads `application.state.registry` via closure over the `application` variable, bypassing the `get_registry` dependency injection pattern used by all other endpoints. This makes the health endpoint harder to test in isolation and creates an inconsistency -- tests must set both `app.state.registry` and the dependency override, and the health endpoint ignores the override.

**Fix:** Move the health endpoint to the router (or a separate health router) and use `Depends(get_registry)`:
```python
@router.get("/health")
async def health(registry: NodeRegistry = Depends(get_registry)) -> JSONResponse:
    return JSONResponse(content={"status": "ok", "nodes_registered": len(registry.get_all())})
```

### WR-05: `body: dict` type annotation missing generic parameter with only `# type: ignore` suppression

**File:** `inference_proxy/proxy/client.py:44` and `inference_proxy/api/routes.py:145`
**Issue:** `dict` without type parameters (`dict[str, Any]`) is used in two places with `# type: ignore[type-arg]` comments. This suppresses a legitimate mypy warning and loses type safety at the API boundary. The body should be typed as `dict[str, Any]` to be explicit about what the function accepts.

**Fix:**
```python
from typing import Any

async def forward(
    self,
    method: str,
    url: str,
    body: dict[str, Any],
) -> httpx.Response:
```

## Info

### IN-01: Unused `pytest` import in test_routes.py

**File:** `tests/api/test_routes.py:17`
**Issue:** `pytest` is imported but never used in this module. No `pytest.raises`, `pytest.mark`, or `pytest.fixture` calls exist.

**Fix:** Remove the unused import:
```python
# Remove: import pytest
```

### IN-02: `select_node` always returns the first healthy node -- no load distribution

**File:** `inference_proxy/proxy/node_selector.py:40`
**Issue:** `select_node` always returns `healthy[0]`, which means all traffic goes to the same node as long as it remains healthy. The docstring and module comment acknowledge this is intentional for Phase 3, with Phase 4 planned to add least-connections routing. Noted here for tracking.

**Fix:** No fix needed -- already planned for Phase 4 per module docstring.

---

_Reviewed: 2026-06-11T18:45:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
