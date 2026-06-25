# Phase 3: Request Proxying and Streaming - Research

**Researched:** 2026-06-11
**Domain:** HTTP reverse proxying with SSE streaming (FastAPI + httpx + httpx-sse)
**Confidence:** HIGH

## Summary

Phase 3 transforms the gateway from a service discovery system into an active request proxy. Clients send OpenAI-compatible requests to the gateway, which selects a vLLM node from the registry and forwards the request. The gateway must handle both synchronous (full JSON response) and streaming (SSE token-by-token) modes transparently.

The core proxy engine uses `httpx.AsyncClient` to forward requests to vLLM backends. For streaming, the gateway consumes upstream SSE events from vLLM using `httpx-sse` and re-emits them to clients using FastAPI's built-in `EventSourceResponse`. Non-streaming responses are proxied as pass-through JSON. Error handling maps vLLM failures to OpenAI-compatible error responses using the existing `ErrorResponse` / `ErrorDetail` Pydantic models.

Node selection for this phase is simple (first available healthy node from the registry). Intelligent routing (least-connections, model-aware filtering) is deferred to Phase 4 per the roadmap.

**Primary recommendation:** Build a `ProxyClient` wrapper around `httpx.AsyncClient` (single long-lived instance created in lifespan) that provides `proxy_request()` and `proxy_stream()` methods. Route handlers in `inference_proxy/api/` consume this client via dependency injection. Use `httpx-sse`'s `aconnect_sse` for upstream SSE consumption and FastAPI's `EventSourceResponse` with `ServerSentEvent(raw_data=...)` for downstream re-emission to avoid double-encoding.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROXY-01 | Client can send chat completion requests via `/v1/chat/completions` and receive responses from a vLLM node | httpx AsyncClient proxying pattern, existing `ChatCompletionRequest` model validates inbound, forward raw JSON body to vLLM, return vLLM response as-is |
| PROXY-02 | Client can send text completion requests via `/v1/completions` and receive responses from a vLLM node | Same proxying pattern as PROXY-01, existing `CompletionRequest` model validates inbound |
| PROXY-03 | Client can list available models via `/v1/models` with model name, node count, and availability | Aggregate from `NodeRegistry.get_all()`, build OpenAI-compatible `/v1/models` response (object: "list", data: [...model objects...]) |
| PROXY-04 | Client can check gateway health via `/health` endpoint | Already exists in `main.py` -- enhance with registry status (node count, ready state) |
| PROXY-05 | Gateway returns OpenAI-compatible error responses with proper status codes and error schema | Existing `ErrorResponse`/`ErrorDetail` models, map httpx exceptions and vLLM error responses to appropriate HTTP status codes |
| STRM-01 | Client receives streaming token-by-token responses via SSE for chat completions | httpx-sse `aconnect_sse` consumes upstream, FastAPI `EventSourceResponse` re-emits with `ServerSentEvent(raw_data=...)` |
| STRM-02 | Client receives streaming token-by-token responses via SSE for text completions | Same SSE proxy pattern as STRM-01, different endpoint |
| STRM-03 | Gateway correctly forwards SSE `data: [DONE]` termination signal from vLLM | Detect `[DONE]` sentinel from upstream, yield as final event, then exit generator |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

### SOLID Principles (Mandatory)
- **SRP:** Proxy client, route handlers, error mapping, and node selection must be separate units
- **OCP:** Node selection strategy must be extensible without modifying proxy code (Phase 4 will add least-connections)
- **DIP:** Route handlers depend on abstractions (protocol/interface for proxy client), not concrete httpx usage directly
- **ISP:** Keep proxy client interface minimal -- `proxy_request()` and `proxy_stream()` are separate concerns

### Tech Stack Constraints
- Python 3.12, FastAPI >=0.135, httpx >=0.28, httpx-sse >=0.4.3
- Internal network only, no auth in v1
- Must implement OpenAI API contract for standard SDK compatibility
- Single process Uvicorn (no multi-worker)

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Request validation (OpenAI schema) | API / Gateway | -- | Pydantic models validate inbound requests before forwarding |
| Request forwarding (proxy) | API / Gateway | -- | Gateway is the reverse proxy; httpx AsyncClient sends to backends |
| SSE stream consumption | API / Gateway | -- | Gateway consumes upstream SSE and re-emits to client |
| SSE stream emission | API / Gateway | -- | FastAPI EventSourceResponse handles downstream SSE |
| Node selection | API / Gateway | -- | Simple first-available for Phase 3; Phase 4 adds routing layer |
| Model listing | API / Gateway | -- | Aggregated from in-memory NodeRegistry |
| Health check | API / Gateway | -- | Gateway-level health, not node health (Phase 5) |
| Error mapping | API / Gateway | -- | Map vLLM/httpx errors to OpenAI error schema |

## Standard Stack

### Core (already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.135, <1.0 | HTTP framework + SSE emission | Built-in `EventSourceResponse` since 0.135. Currently 0.136.3 installed. [VERIFIED: project venv] |
| Pydantic | >=2.10, <3.0 | Request/response validation | Already used for OpenAI models. Rust-backed validation. [VERIFIED: project venv] |

### New Dependencies (must be added to pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | >=0.28, <1.0 | Async HTTP client for proxying | Already a transitive dependency (via FastAPI/Starlette) but must be declared as direct dependency. AsyncClient with streaming, connection pooling, timeout control. Currently 0.28.1 installed. [VERIFIED: project venv, slopcheck OK] |
| httpx-sse | >=0.4.3 | SSE event consumption from upstream | Parses upstream SSE events from vLLM streaming responses. `aconnect_sse()` + `aiter_sse()` for clean async iteration. 176M monthly PyPI downloads. [VERIFIED: slopcheck OK, CITED: github.com/florimondmanca/httpx-sse] |

### Already Available (dev dependencies)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-httpx | >=0.36 | Mock httpx requests in tests | Mock upstream vLLM responses including streaming/SSE. Use `IteratorStream` for SSE mocking. [VERIFIED: project venv] |
| pytest-asyncio | >=1.4 | Async test support | All proxy tests will be async. `asyncio_mode = "auto"` already configured. [VERIFIED: pyproject.toml] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx-sse | Manual `aiter_lines()` parsing | httpx-sse provides structured `ServerSentEvent` objects with `.data`, `.event`, `.id`, `.json()`. Manual parsing is error-prone with multi-line data fields. httpx-sse is the standard. |
| FastAPI EventSourceResponse | sse-starlette | FastAPI 0.135+ has built-in SSE with Pydantic serialization on the Rust side. sse-starlette is now redundant for new projects. |
| Pass-through raw bytes | Parse and re-serialize responses | For non-streaming, pass vLLM's JSON response through without re-serialization. Avoids unnecessary parsing overhead and preserves vLLM-specific fields. |

**Installation:**
```bash
uv add "httpx>=0.28,<1.0" "httpx-sse>=0.4.3"
```

**Version verification:**
```
httpx: 0.28.1 installed (verified in project venv)
httpx-sse: 0.4.3 latest on PyPI (verified via slopcheck)
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| httpx | PyPI | ~6 yrs | 300M+/mo | github.com/encode/httpx | [OK] | Approved |
| httpx-sse | PyPI | ~3 yrs | 176M/mo | github.com/florimondmanca/httpx-sse | [OK] | Approved |
| fastapi | PyPI | ~7 yrs | 100M+/mo | github.com/fastapi/fastapi | [OK] | Approved |
| pytest-httpx | PyPI | ~5 yrs | 10M+/mo | github.com/Colin-b/pytest_httpx | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Client (OpenAI SDK)
    |
    | POST /v1/chat/completions  (stream: true/false)
    | POST /v1/completions       (stream: true/false)
    | GET  /v1/models
    | GET  /health
    v
+-------------------+
|  FastAPI Gateway   |
|  (Route Handlers)  |
|                    |
|  1. Validate req   |  <-- Pydantic models (ChatCompletionRequest, etc.)
|  2. Select node    |  <-- NodeRegistry.get_all() -> pick first available
|  3. Forward req    |  <-- ProxyClient (httpx AsyncClient)
|  4. Return resp    |  <-- JSON pass-through OR SSE re-emission
+-------------------+
    |                          |
    | Non-streaming:           | Streaming:
    | httpx.AsyncClient        | httpx-sse aconnect_sse
    | .post(url, json=body)    | -> aiter_sse()
    | -> return JSON           | -> yield ServerSentEvent
    v                          v
+-------------------+    +-------------------+
|  vLLM Node A      |    |  vLLM Node B      |
|  /v1/chat/compl.  |    |  /v1/completions   |
|  /v1/completions  |    |  /v1/models        |
|  /v1/models       |    |                    |
+-------------------+    +-------------------+
```

### Recommended Project Structure

```
inference_proxy/
  api/
    __init__.py
    routes.py           # FastAPI router with /v1/* and /health endpoints
    errors.py           # Error mapping: httpx/vLLM errors -> OpenAI ErrorResponse
  proxy/
    __init__.py
    client.py           # ProxyClient: httpx.AsyncClient wrapper
    node_selector.py    # Simple node selection (first available); Phase 4 replaces
  models/
    openai.py           # Existing OpenAI request/response/streaming/error models
    node.py             # Existing Node model
  config/
    settings.py         # Add ProxySettings (timeouts, connection limits)
    dependencies.py     # Add get_proxy_client dependency
  discovery/            # Existing, unchanged
  routing/              # Empty stub, Phase 4
  resilience/           # Empty stub, Phase 5
```

### Pattern 1: Non-Streaming Proxy (Pass-Through)

**What:** Forward request body to vLLM, return raw JSON response to client.
**When to use:** `stream: false` (default) on completion requests.

```python
# Source: httpx official docs (python-httpx.org/async) + FastAPI patterns
async def proxy_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    body: dict,
    timeout: httpx.Timeout,
) -> httpx.Response:
    """Forward a request to a vLLM backend and return the response."""
    response = await client.request(
        method=method,
        url=url,
        json=body,
        timeout=timeout,
    )
    return response
```

Route handler pattern:
```python
# Source: FastAPI proxy discussion github.com/fastapi/fastapi/discussions/9599
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    registry: NodeRegistry = Depends(get_registry),
    proxy: ProxyClient = Depends(get_proxy_client),
) -> JSONResponse:
    if request.stream:
        return await _stream_chat(request, registry, proxy)

    node = select_node(registry)
    url = f"http://{node.endpoint}/v1/chat/completions"
    body = request.model_dump(exclude_none=True)
    response = await proxy.forward(url, body)
    return JSONResponse(
        content=response.json(),
        status_code=response.status_code,
    )
```

### Pattern 2: Streaming SSE Proxy (Consume + Re-Emit)

**What:** Consume SSE events from upstream vLLM via httpx-sse, re-emit to client via FastAPI EventSourceResponse.
**When to use:** `stream: true` on completion requests.

```python
# Source: httpx-sse docs (github.com/florimondmanca/httpx-sse)
#         FastAPI SSE docs (fastapi.tiangolo.com/tutorial/server-sent-events/)
from fastapi.sse import EventSourceResponse, ServerSentEvent
from httpx_sse import aconnect_sse

async def _stream_completion(
    url: str,
    body: dict,
    client: httpx.AsyncClient,
) -> EventSourceResponse:
    async def event_generator():
        async with aconnect_sse(client, "POST", url, json=body) as event_source:
            event_source.response.raise_for_status()
            async for sse in event_source.aiter_sse():
                if sse.data == "[DONE]":
                    yield ServerSentEvent(raw_data="[DONE]")
                    break
                yield ServerSentEvent(raw_data=sse.data)

    return EventSourceResponse(event_generator())
```

**Critical detail:** Use `raw_data` not `data` in `ServerSentEvent` to avoid double JSON-encoding. The upstream vLLM already sends JSON-encoded data; we re-emit it verbatim. [CITED: fastapi.tiangolo.com/tutorial/server-sent-events/]

### Pattern 3: OpenAI-Compatible Error Responses

**What:** Map upstream failures to the OpenAI error schema.
**When to use:** Any proxy failure (connection error, timeout, vLLM error response).

```python
# Source: OpenAI API error format (platform.openai.com/docs/api-reference)
from inference_proxy.models.openai import ErrorDetail, ErrorResponse

def map_proxy_error(exc: Exception) -> tuple[int, ErrorResponse]:
    """Map proxy exceptions to OpenAI-compatible error responses."""
    if isinstance(exc, httpx.ConnectError):
        return 502, ErrorResponse(error=ErrorDetail(
            message="Failed to connect to inference backend",
            type="upstream_error",
            code="backend_unavailable",
        ))
    if isinstance(exc, httpx.TimeoutException):
        return 504, ErrorResponse(error=ErrorDetail(
            message="Inference backend timed out",
            type="upstream_error",
            code="backend_timeout",
        ))
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code, ErrorResponse(error=ErrorDetail(
            message=f"Inference backend returned error: {exc.response.text}",
            type="upstream_error",
            code=str(exc.response.status_code),
        ))
    return 500, ErrorResponse(error=ErrorDetail(
        message="Internal gateway error",
        type="server_error",
        code="internal_error",
    ))
```

### Pattern 4: /v1/models Aggregation

**What:** Build OpenAI-compatible model list from the node registry.
**When to use:** GET /v1/models endpoint.

```python
# Source: OpenAI API reference (platform.openai.com/docs/api-reference/models/list)
@router.get("/v1/models")
async def list_models(
    registry: NodeRegistry = Depends(get_registry),
) -> JSONResponse:
    nodes = registry.get_all()
    models_seen: dict[str, dict] = {}
    for node in nodes:
        if node.model and node.model not in models_seen:
            models_seen[node.model] = {
                "id": node.model,
                "object": "model",
                "created": 0,  # Not tracked per-model
                "owned_by": "vllm",
            }
    return JSONResponse(content={
        "object": "list",
        "data": list(models_seen.values()),
    })
```

### Pattern 5: httpx AsyncClient Lifecycle (Lifespan)

**What:** Create a single long-lived `httpx.AsyncClient` during app startup, close on shutdown.
**When to use:** Always -- connection pooling requires a persistent client.

```python
# Source: httpx docs (python-httpx.org/async) -- connection reuse guidance
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing setup ...
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=5.0,
            read=120.0,   # Long read timeout for LLM inference
            write=10.0,
            pool=10.0,
        ),
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30,
        ),
    )
    app.state.http_client = http_client
    yield
    await http_client.aclose()
```

### Anti-Patterns to Avoid

- **Creating AsyncClient per request:** Destroys connection pooling. Use a single long-lived instance stored in `app.state`. [CITED: python-httpx.org/async]
- **Double JSON encoding in SSE:** Using `ServerSentEvent(data=sse.data)` when `sse.data` is already a JSON string will double-encode it. Use `raw_data=` instead. [CITED: fastapi.tiangolo.com/tutorial/server-sent-events/]
- **Forwarding the Host header:** When proxying to a different host, the original `Host` header causes the target server to reject or misroute the request. Strip it. [CITED: github.com/fastapi/fastapi/discussions/9599]
- **Buffering entire streaming response:** Never `await response.aread()` on a streaming response. Use `aiter_sse()` or `aiter_lines()` to process incrementally. [CITED: python-httpx.org/async]
- **Missing cleanup for streaming responses:** In non-SSE streaming, forgetting `BackgroundTask(response.aclose)` leaks connections. With httpx-sse's `aconnect_sse` context manager, cleanup is automatic. [CITED: python-httpx.org/async]
- **Re-serializing pass-through responses:** For non-streaming, return vLLM's JSON directly via `JSONResponse(content=response.json())`. Do not parse into Pydantic models and re-serialize -- it adds latency and may drop vLLM-specific fields that clients expect.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE event parsing | Custom line parser for `data:` prefix | `httpx-sse` `aiter_sse()` | Multi-line data fields, event/id/retry fields, content-type validation. Edge cases abound. [CITED: github.com/florimondmanca/httpx-sse] |
| SSE event emission | Manual `text/event-stream` formatting | FastAPI `EventSourceResponse` + `ServerSentEvent` | Automatic keep-alive pings (15s), `Cache-Control: no-cache`, `X-Accel-Buffering: no` headers. [CITED: fastapi.tiangolo.com/tutorial/server-sent-events/] |
| Connection pooling | Manual socket/connection management | `httpx.AsyncClient` with `Limits` | Configurable max_connections, keepalive, automatic pool management. [CITED: python-httpx.org/advanced/resource-limits] |
| Timeout management | Manual asyncio timeout wrappers | `httpx.Timeout` with per-phase granularity | connect/read/write/pool timeouts with proper exception types. [CITED: python-httpx.org/advanced/timeouts] |
| OpenAI error schema | Custom error dict construction | Existing `ErrorResponse`/`ErrorDetail` Pydantic models | Already defined in Phase 1. Validated structure matching OpenAI spec. |

**Key insight:** The SSE proxy pipeline has two distinct halves -- consumption (httpx-sse) and emission (FastAPI EventSourceResponse). Using raw `aiter_lines()` for consumption means re-implementing SSE parsing with all its edge cases. Using manual string formatting for emission means missing keep-alive pings and proxy-friendly headers.

## Common Pitfalls

### Pitfall 1: Double JSON Encoding in SSE Pass-Through
**What goes wrong:** vLLM sends `data: {"id":"cmpl-123","choices":[...]}`. If you yield `ServerSentEvent(data=sse.data)`, FastAPI JSON-encodes the already-JSON string, producing `data: "{\"id\":\"cmpl-123\",...}"` -- a JSON string wrapping JSON.
**Why it happens:** FastAPI's `ServerSentEvent(data=...)` applies Pydantic/JSON serialization. The upstream data is already serialized.
**How to avoid:** Always use `ServerSentEvent(raw_data=sse.data)` for pass-through proxying. `raw_data` sends the value verbatim without encoding. [CITED: fastapi.tiangolo.com/tutorial/server-sent-events/]
**Warning signs:** Client receives escaped JSON strings instead of parsed objects.

### Pitfall 2: Read Timeout During Long Inference
**What goes wrong:** LLM inference can take 30-120+ seconds for first token (especially long prompts, large models). Default httpx 5s timeout triggers `ReadTimeout` before vLLM responds.
**Why it happens:** httpx default timeout is 5 seconds across all phases.
**How to avoid:** Set `read` timeout to 120s+ for inference endpoints. For streaming, the read timeout applies between chunks -- once streaming starts, each chunk arrives quickly (sub-second), but first-chunk latency can be high.
**Warning signs:** `httpx.ReadTimeout` exceptions on large prompts.

### Pitfall 3: Connection Pool Exhaustion Under Load
**What goes wrong:** With many concurrent streaming requests and default `max_connections=100`, the pool fills up and new requests get `PoolTimeout`.
**Why it happens:** Streaming requests hold connections open for seconds to minutes. 100 concurrent streams = 100 connections.
**How to avoid:** Configure `max_connections` based on expected concurrency. Monitor pool usage. Set explicit `pool` timeout (10s default is reasonable).
**Warning signs:** `httpx.PoolTimeout` under load.

### Pitfall 4: vLLM SSE Content-Type Variation
**What goes wrong:** `httpx-sse` raises `SSEError` if the response `Content-Type` is not `text/event-stream`. vLLM may include charset or other parameters.
**Why it happens:** httpx-sse does strict content-type checking during `aiter_sse()`. [CITED: github.com/florimondmanca/httpx-sse]
**How to avoid:** Verify vLLM's actual Content-Type header. If it differs, you may need to handle `SSEError` gracefully or fall back to manual line parsing.
**Warning signs:** `SSEError` exceptions on streaming requests that work with `curl`.

### Pitfall 5: Empty Registry (No Nodes Available)
**What goes wrong:** Client sends a request but no nodes are registered in the registry. Without handling, this causes an unhandled exception or cryptic error.
**Why it happens:** Gateway started before any vLLM nodes, or etcd is down, or all nodes removed.
**How to avoid:** Check registry before attempting proxy. Return `503 Service Unavailable` with OpenAI error schema: `{"error": {"message": "No inference nodes available", "type": "server_error", "code": "no_nodes"}}`.
**Warning signs:** Unhandled `IndexError` or `None` returns from node selection.

### Pitfall 6: Client Disconnect During Streaming
**What goes wrong:** Client closes connection mid-stream, but the gateway keeps consuming from vLLM and holding the upstream connection.
**Why it happens:** The async generator continues running even after the client disconnects.
**How to avoid:** FastAPI's `EventSourceResponse` handles this -- when the client disconnects, the generator receives a `CancelledError` or write fails, breaking the loop. The `aconnect_sse` context manager ensures upstream cleanup. Verify this behavior in tests. [ASSUMED]
**Warning signs:** Orphaned upstream connections after client disconnects.

### Pitfall 7: Forwarding Host Header to vLLM
**What goes wrong:** The gateway forwards the original `Host: gateway.example.com` header to vLLM, which expects `Host: vllm-node:8000`.
**Why it happens:** Naive header forwarding copies all inbound headers.
**How to avoid:** Do not forward the `Host` header. When using `httpx.AsyncClient.post(url, json=body)` (not `build_request` + `send`), httpx sets the correct Host automatically. [CITED: github.com/fastapi/fastapi/discussions/9599]
**Warning signs:** vLLM returns 404 or routing errors.

## Code Examples

### Complete Non-Streaming Proxy Handler

```python
# Source: Composite from httpx docs + FastAPI proxy patterns
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from inference_proxy.api.errors import handle_proxy_error
from inference_proxy.config.dependencies import get_proxy_client, get_registry
from inference_proxy.models.openai import ChatCompletionRequest
from inference_proxy.proxy.client import ProxyClient
from inference_proxy.proxy.node_selector import select_node
from inference_proxy.discovery.registry import NodeRegistry

router = APIRouter()

@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    registry: NodeRegistry = Depends(get_registry),
    proxy: ProxyClient = Depends(get_proxy_client),
):
    if request.stream:
        return await _stream_chat_completions(request, registry, proxy)

    node = select_node(registry)
    if node is None:
        return handle_proxy_error(no_nodes_available_error())

    url = f"http://{node.endpoint}/v1/chat/completions"
    body = request.model_dump(exclude_none=True)

    try:
        response = await proxy.forward("POST", url, body)
        return JSONResponse(
            content=response.json(),
            status_code=response.status_code,
        )
    except Exception as exc:
        return handle_proxy_error(exc)
```

### Complete Streaming SSE Proxy Handler

```python
# Source: httpx-sse docs + FastAPI SSE docs
from fastapi.sse import EventSourceResponse, ServerSentEvent
from httpx_sse import aconnect_sse

async def _stream_chat_completions(
    request: ChatCompletionRequest,
    registry: NodeRegistry,
    proxy: ProxyClient,
) -> EventSourceResponse:
    node = select_node(registry)
    if node is None:
        raise handle_proxy_error(no_nodes_available_error())

    url = f"http://{node.endpoint}/v1/chat/completions"
    body = request.model_dump(exclude_none=True)

    async def event_generator():
        try:
            async with aconnect_sse(
                proxy.client, "POST", url, json=body
            ) as event_source:
                event_source.response.raise_for_status()
                async for sse in event_source.aiter_sse():
                    if sse.data == "[DONE]":
                        yield ServerSentEvent(raw_data="[DONE]")
                        break
                    yield ServerSentEvent(raw_data=sse.data)
        except Exception as exc:
            # Log the error; the client sees the stream terminate
            logger.error("streaming proxy error", error=str(exc))

    return EventSourceResponse(event_generator())
```

### pytest-httpx Mocking for SSE Streams

```python
# Source: pytest-httpx docs (colin-b.github.io/pytest_httpx)
import pytest
from pytest_httpx import HTTPXMock, IteratorStream

@pytest.mark.asyncio
async def test_streaming_proxy(httpx_mock: HTTPXMock):
    """Mock a vLLM streaming SSE response."""
    sse_chunks = [
        b'data: {"id":"cmpl-1","object":"chat.completion.chunk","created":1234,"model":"llama","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n',
        b'data: {"id":"cmpl-1","object":"chat.completion.chunk","created":1234,"model":"llama","choices":[{"index":0,"delta":{"content":" world"},"finish_reason":"stop"}]}\n\n',
        b'data: [DONE]\n\n',
    ]
    httpx_mock.add_response(
        url="http://node1:8000/v1/chat/completions",
        headers={"content-type": "text/event-stream"},
        stream=IteratorStream(sse_chunks),
    )
```

### ProxyClient Wrapper

```python
# Source: httpx docs (python-httpx.org/async) -- connection reuse pattern
import httpx

class ProxyClient:
    """Wrapper around httpx.AsyncClient for proxying to vLLM backends."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @property
    def client(self) -> httpx.AsyncClient:
        """Expose the underlying client for httpx-sse aconnect_sse."""
        return self._client

    async def forward(
        self,
        method: str,
        url: str,
        body: dict,
    ) -> httpx.Response:
        """Forward a non-streaming request to a vLLM backend."""
        response = await self._client.request(
            method=method,
            url=url,
            json=body,
        )
        return response
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sse-starlette for SSE emission | FastAPI built-in EventSourceResponse | FastAPI 0.135.0 (2025) | No external SSE dependency needed. Pydantic Rust-side serialization for performance. |
| Manual `aiter_lines()` for SSE parsing | httpx-sse `aiter_sse()` | httpx-sse 0.4+ (2024) | Structured event parsing with `.data`, `.event`, `.id`, `.json()`. Content-type validation. |
| `requests` library for HTTP proxying | httpx AsyncClient | httpx 0.28+ (2024) | Native async, streaming, connection pooling, timeout granularity. |
| `ServerSentEvent(data=...)` for raw strings | `ServerSentEvent(raw_data=...)` | FastAPI 0.135.0 (2025) | `raw_data` sends verbatim without JSON encoding. Critical for pass-through proxying. |

**Deprecated/outdated:**
- **sse-starlette:** Still works but redundant for new projects targeting FastAPI 0.135+
- **requests library:** Synchronous only. httpx is the modern replacement.
- **Manual SSE line parsing:** Error-prone. httpx-sse handles edge cases (multi-line data, event types, retry).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | FastAPI EventSourceResponse handles client disconnect by cancelling the async generator | Pitfall 6 | If not handled automatically, orphaned upstream connections could accumulate. Verify with a test. |
| A2 | vLLM sends `Content-Type: text/event-stream` for streaming responses | Pitfall 4 | If vLLM uses a different content type, httpx-sse will raise SSEError. May need fallback to manual parsing. |
| A3 | vLLM's SSE format is `data: {json}\n\n` followed by `data: [DONE]\n\n` | Pattern 2, STRM-03 | If vLLM uses a different sentinel or event format, the proxy's SSE parsing will break. Based on OpenAI API spec which vLLM implements. |
| A4 | `httpx.AsyncClient` timeout's `read` parameter applies between chunks in streaming mode | Pitfall 2 | If read timeout applies to total stream duration, long completions will timeout. Test with real vLLM. |
| A5 | Simple "first available node" selection is sufficient for Phase 3 MVP | Architecture | Phase 4 adds intelligent routing. If all nodes are unhealthy, this returns the first one anyway -- needs filtering. |

## Open Questions

1. **vLLM Content-Type Header for Streaming**
   - What we know: OpenAI API uses `text/event-stream`. httpx-sse requires this header.
   - What's unclear: Whether vLLM always sends exactly `text/event-stream` or includes additional parameters (e.g., `charset=utf-8`).
   - Recommendation: Test with a real vLLM instance during development. If Content-Type varies, catch `SSEError` and fall back to `aiter_lines()` parsing.

2. **Should `/health` be enhanced or left as-is?**
   - What we know: Current `/health` returns `{"status": "ok"}` unconditionally. PROXY-04 says "check gateway health via `/health`" which the current implementation satisfies.
   - What's unclear: Whether to add registry node count, upstream connectivity status.
   - Recommendation: Enhance minimally -- add `nodes_registered` count. Deep health checks (per-node pings) are Phase 5 (RESL-01).

3. **Request body forwarding: validate-then-forward vs. pass-through**
   - What we know: Request models have `extra='allow'` (D-10) for forward compatibility.
   - What's unclear: Whether to use `request.model_dump(exclude_none=True)` (strips None fields) or forward the raw JSON body verbatim.
   - Recommendation: Use `model_dump(exclude_none=True)` for validated requests. This preserves vLLM-specific `extra` fields while stripping explicit `None` values. The `extra='allow'` config ensures unknown fields pass through.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.12.9 (project venv) | -- |
| uv | Package management | Yes | 0.6.5 | -- |
| FastAPI | HTTP framework | Yes | 0.136.3 | -- |
| httpx | Proxy engine | Yes (transitive) | 0.28.1 | Add as direct dependency |
| httpx-sse | SSE consumption | No | -- | `uv add "httpx-sse>=0.4.3"` |
| pytest-httpx | Test mocking | Yes (dev dep) | 0.36.2 | -- |

**Missing dependencies with no fallback:** None (httpx-sse can be installed via uv add)

**Missing dependencies with fallback:**
- httpx-sse: Not installed yet but available on PyPI. Add to pyproject.toml.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROXY-01 | POST /v1/chat/completions returns vLLM response | integration | `uv run pytest tests/api/test_routes.py::test_chat_completion_non_streaming -x` | No -- Wave 0 |
| PROXY-02 | POST /v1/completions returns vLLM response | integration | `uv run pytest tests/api/test_routes.py::test_text_completion_non_streaming -x` | No -- Wave 0 |
| PROXY-03 | GET /v1/models returns aggregated model list | unit | `uv run pytest tests/api/test_routes.py::test_list_models -x` | No -- Wave 0 |
| PROXY-04 | GET /health returns gateway status | unit | `uv run pytest tests/test_app.py::test_health_endpoint -x` | Yes |
| PROXY-05 | Error responses match OpenAI schema | unit | `uv run pytest tests/api/test_errors.py -x` | No -- Wave 0 |
| STRM-01 | Streaming chat completions via SSE | integration | `uv run pytest tests/api/test_routes.py::test_chat_completion_streaming -x` | No -- Wave 0 |
| STRM-02 | Streaming text completions via SSE | integration | `uv run pytest tests/api/test_routes.py::test_text_completion_streaming -x` | No -- Wave 0 |
| STRM-03 | SSE [DONE] termination forwarded | integration | `uv run pytest tests/api/test_routes.py::test_streaming_done_signal -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/api/__init__.py` -- test subpackage for API route tests
- [ ] `tests/api/test_routes.py` -- covers PROXY-01, PROXY-02, PROXY-03, STRM-01, STRM-02, STRM-03
- [ ] `tests/api/test_errors.py` -- covers PROXY-05
- [ ] `tests/proxy/__init__.py` -- test subpackage for proxy client tests
- [ ] `tests/proxy/test_client.py` -- covers ProxyClient unit tests
- [ ] `tests/proxy/test_node_selector.py` -- covers node selection logic

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Internal network only, no auth in v1 |
| V3 Session Management | No | Stateless proxy, no sessions |
| V4 Access Control | No | Internal network only |
| V5 Input Validation | Yes | Pydantic models with field constraints (`ge`, `le`, `gt`, `min_length`) validate all inbound requests |
| V6 Cryptography | No | Internal network, no encryption |

### Known Threat Patterns for Proxy Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Request body injection | Tampering | Pydantic validation with `extra='allow'` passes unknown fields but validates known ones. vLLM handles its own input validation. |
| SSRF via model/endpoint manipulation | Spoofing | Nodes come only from etcd registry, not from request parameters. Client cannot specify a target URL. |
| Resource exhaustion via streaming | Denial of Service | httpx connection pool limits (`max_connections=100`), read timeouts (120s), pool timeouts (10s). |
| Response injection via SSE | Tampering | SSE events are forwarded verbatim from trusted vLLM backends on internal network. |

## Sources

### Primary (HIGH confidence)
- [httpx async docs](https://www.python-httpx.org/async/) -- AsyncClient usage, streaming, proxy pattern
- [httpx timeouts](https://www.python-httpx.org/advanced/timeouts/) -- Timeout configuration
- [httpx resource limits](https://www.python-httpx.org/advanced/resource-limits/) -- Connection pool limits
- [httpx-sse README](https://github.com/florimondmanca/httpx-sse) -- aconnect_sse, aiter_sse, SSE event structure
- [FastAPI SSE docs](https://fastapi.tiangolo.com/tutorial/server-sent-events/) -- EventSourceResponse, ServerSentEvent, raw_data
- [pytest-httpx docs](https://colin-b.github.io/pytest_httpx/) -- IteratorStream, mock streaming, async mocking
- [OpenAI API models endpoint](https://platform.openai.com/docs/api-reference/models/list) -- /v1/models response format
- [OpenAI streaming guide](https://developers.openai.com/api/docs/guides/streaming-responses) -- SSE wire format, [DONE] sentinel

### Secondary (MEDIUM confidence)
- [FastAPI proxy discussion #9599](https://github.com/fastapi/fastapi/discussions/9599) -- Reverse proxy patterns, header stripping
- [vLLM OpenAI-compatible server docs](https://docs.vllm.ai/en/v0.8.1/serving/openai_compatible_server.html) -- Supported endpoints, extra parameters
- [FastAPI client disconnect discussion](https://github.com/fastapi/fastapi/discussions/7572) -- request.is_disconnected() patterns

### Tertiary (LOW confidence)
- General LLM gateway patterns from web search (community articles, not official docs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages verified via slopcheck and project venv, versions confirmed
- Architecture: HIGH -- patterns derived from official httpx, httpx-sse, and FastAPI documentation
- Pitfalls: MEDIUM -- most pitfalls from official docs, but client disconnect behavior (A1) and vLLM content-type (A2) need runtime verification

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable domain, well-established libraries)
