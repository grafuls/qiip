# Phase 6: Observability and Admin - Research

**Researched:** 2026-06-25
**Domain:** Request logging middleware, admin API endpoint, structlog, FastAPI middleware patterns
**Confidence:** HIGH

## Summary

Phase 6 adds two capabilities to the inference proxy: (1) a structured request logging middleware that produces a JSON log entry for every HTTP request with method, path, status, duration, and target node; and (2) an admin API endpoint at `/admin/nodes` that returns the live node fleet with models and health status.

This is a well-scoped phase with minimal risk. No new dependencies are required -- all libraries are already installed (structlog 26.1.0, FastAPI, Pydantic). The existing codebase provides clear patterns to follow: `ShutdownMiddleware` for the middleware design, `APIRouter` for the admin router, and `NodeRegistry.get_all()` for the admin data source. The structlog configuration already includes `merge_contextvars` as the first processor, which is the correct setup for request-scoped logging.

**Primary recommendation:** Implement the logging middleware as a `BaseHTTPMiddleware` subclass using `time.perf_counter()` for duration measurement, reading `request.state.target_node` (set by route handlers after node selection) for the target node field. Implement the admin endpoint as a separate `APIRouter` in `inference_proxy/api/admin.py` returning `NodeRegistry.get_all()` data through a Pydantic response model.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Request logging is implemented as a FastAPI middleware (following the ShutdownMiddleware pattern), not per-route logging. A single middleware intercepts all requests and produces a structured log entry on response.
- **D-02:** Log entries include the OBSV-01 minimum fields only: method, path, status_code, duration_ms, target_node. No request_id, model name, or other enrichment in v1.
- **D-03:** The middleware logs ALL requests -- /health, /v1/models, admin endpoints, and proxy routes. Target node is null/absent for non-proxy routes.
- **D-04:** The target node is communicated from route handlers to the middleware via `request.state.target_node`. Route handlers set this after node selection; the middleware reads it in the response phase.
- **D-05:** Admin endpoint lives at `/admin/nodes` under a separate `/admin` namespace, not mixed into the `/v1` proxy API.
- **D-06:** The admin router is a separate `APIRouter` in `inference_proxy/api/admin.py` with `prefix="/admin"`, included via `app.include_router()` in `main.py`. Separate from proxy routes (SRP).
- **D-07:** The endpoint returns core fields per node only: node_id, endpoint, model, status. Matches DISC-04 exactly. No operational data (connection counts, circuit breaker state) in v1.
- **D-08:** Response is a flat node list -- no top-level summary stats. Clients derive counts from the array.

### Claude's Discretion
- Middleware class name and module placement (e.g., `inference_proxy/api/middleware.py` or `inference_proxy/observability/`)
- How to measure request duration (time.monotonic, time.perf_counter, etc.)
- Log level for request log entries (info vs debug for different route types)
- Admin response Pydantic model design (inline or in models/)
- Whether to add the admin router to the OpenAPI docs or exclude it
- Test fixture design for logging middleware and admin endpoint

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBSV-01 | Gateway emits structured JSON logs (structlog) for all requests with method, path, status, duration, and target node | Logging middleware pattern via BaseHTTPMiddleware + structlog; `merge_contextvars` already configured; `request.state.target_node` for node field |
| DISC-04 | Admin can view registered nodes, their models, and health status via admin API endpoint | Admin APIRouter at `/admin/nodes` reading from `NodeRegistry.get_all()`; Pydantic response model with node_id, endpoint, model, status fields |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Request logging | API / Backend (middleware) | -- | Cross-cutting concern owned by the HTTP layer; middleware intercepts all requests at the ASGI level |
| Admin node listing | API / Backend (endpoint) | -- | Server-side data from in-memory NodeRegistry; no client-side component |
| Duration measurement | API / Backend (middleware) | -- | Server-side timing using monotonic clock; measured per-request in middleware dispatch |
| Target node tracking | API / Backend (route handlers) | -- | Route handlers set `request.state.target_node` after node selection; middleware reads it |

## Standard Stack

### Core (Already Installed -- No New Dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| structlog | 26.1.0 | Structured logging | Already configured with JSON/console dual mode and `merge_contextvars` processor. Used throughout codebase. [VERIFIED: pyproject.toml] |
| FastAPI | >=0.135 | HTTP framework + middleware | `BaseHTTPMiddleware` from Starlette for cross-cutting logging. `APIRouter` for admin endpoint. Already the project's framework. [VERIFIED: pyproject.toml] |
| Pydantic | >=2.10 | Response models | Frozen `BaseModel` for admin response schema, following existing `models/openai.py` pattern. [VERIFIED: pyproject.toml] |

### Supporting (Already Installed)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=8.0 | Testing | Unit tests for middleware and admin endpoint [VERIFIED: pyproject.toml] |
| pytest-asyncio | >=1.4 | Async test support | Async admin endpoint tests [VERIFIED: pyproject.toml] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BaseHTTPMiddleware | Pure ASGI middleware | Pure ASGI avoids the contextvars propagation issue, but `request.state` (our mechanism per D-04) works fine with BaseHTTPMiddleware. Pure ASGI is more boilerplate for no benefit here. |
| time.perf_counter() | time.monotonic() | Both are monotonic. perf_counter has higher resolution on some platforms. On CPython 3.13+ they use the same clock. For ms-precision request timing, either works. |
| structlog.info() | stdlib logging | structlog is already the project standard and configured with JSON output. No reason to use stdlib directly. |

**Installation:**
```bash
# No new packages needed -- all dependencies already in pyproject.toml
```

## Package Legitimacy Audit

> No new packages are being installed in this phase. All libraries (structlog, FastAPI, Pydantic, pytest) are existing project dependencies verified in previous phases.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Client Request
      |
      v
+---------------------+
|  LoggingMiddleware   |  <-- START timer (time.perf_counter)
+---------------------+
      |
      v
+---------------------+
| ShutdownMiddleware   |  <-- May short-circuit with 503
+---------------------+
      |
      v
+---------------------+
|   FastAPI Router     |  <-- Route handler dispatches to:
|                     |      /v1/chat/completions
|                     |      /v1/completions
|                     |      /v1/models
|                     |      /admin/nodes
|                     |      /health
+---------------------+
      |
      | (proxy routes set request.state.target_node)
      v
+---------------------+
|   ProxyClient /     |  <-- Forwards to vLLM backend
|   NodeSelector      |
+---------------------+
      |
      v
  Response flows back up
      |
      v
+---------------------+
|  LoggingMiddleware   |  <-- STOP timer, compute duration_ms
|  (response phase)   |      Read request.state.target_node
|                     |      Log: method, path, status, duration, node
+---------------------+
      |
      v
  Response to Client
```

**Middleware ordering note:** LoggingMiddleware must be added AFTER ShutdownMiddleware in `main.py` (since middleware stacks are LIFO -- the last added wraps outermost). This means LoggingMiddleware is the outermost layer and will log ALL requests including 503 shutdown rejections. [CITED: https://fastapi.tiangolo.com/tutorial/middleware/]

### Recommended Project Structure

```
inference_proxy/
├── api/
│   ├── admin.py          # NEW: Admin APIRouter with /admin/nodes
│   ├── middleware.py      # NEW: RequestLoggingMiddleware
│   ├── errors.py          # Existing: error response helpers
│   └── routes.py          # Existing: proxy routes (modified to set request.state.target_node)
├── models/
│   ├── admin.py           # NEW: AdminNodeResponse Pydantic model
│   ├── node.py            # Existing: Node, NodeStatus
│   └── openai.py          # Existing: OpenAI models
├── config/
│   ├── dependencies.py    # Existing: DI providers (no changes needed)
│   ├── logging.py         # Existing: structlog config (no changes needed)
│   └── settings.py        # Existing: Settings
├── discovery/
│   └── registry.py        # Existing: NodeRegistry.get_all() (data source for admin)
└── main.py                # Existing: add LoggingMiddleware + include admin router
```

**Discretion recommendation (module placement):** Place the middleware in `inference_proxy/api/middleware.py` alongside the existing route handlers and error helpers. This keeps all HTTP-layer concerns together under `api/`. A separate `observability/` package would be over-engineering for a single middleware class. Place the admin response model in `inference_proxy/models/admin.py` following the existing pattern of `models/openai.py` and `models/node.py`. [ASSUMED]

### Pattern 1: BaseHTTPMiddleware with request.state for Cross-Layer Data

**What:** The logging middleware uses `BaseHTTPMiddleware.dispatch()` to wrap every request. It starts a timer before `call_next`, reads `request.state.target_node` after `call_next`, and emits a structlog entry with all required fields.

**When to use:** For cross-cutting concerns that need data from both the request phase (method, path) and the response phase (status code, data set by route handlers).

**Critical finding:** `request.state` works correctly with `BaseHTTPMiddleware` for cross-layer communication. Unlike `contextvars.ContextVar` (which does NOT propagate from endpoints back to BaseHTTPMiddleware due to task-group context copying), `request.state` is backed by the shared ASGI `scope` dictionary and mutations are visible across task boundaries. This is confirmed by Starlette's own test suite. [CITED: https://github.com/encode/starlette/blob/master/tests/middleware/test_base.py]

**Example:**
```python
# Source: Starlette BaseHTTPMiddleware pattern + structlog
import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
import structlog

logger = structlog.get_logger()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        target_node: str | None = getattr(request.state, "target_node", None)

        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            target_node=target_node,
        )
        return response
```

### Pattern 2: Setting request.state.target_node in Route Handlers

**What:** Route handlers (or their helper functions) set `request.state.target_node` after selecting a node for proxying. The logging middleware reads this value in its response phase.

**When to use:** Per D-04, this is the mechanism for communicating the target node from route handlers to the logging middleware.

**Design challenge:** The current route handler signatures use `request: ChatCompletionRequest` (the Pydantic model), not `request: Request` (the Starlette Request). To set `request.state.target_node`, the handlers need access to the Starlette `Request` object.

**Solution:** Add a `starlette_request: Request` parameter to the route handler signatures alongside the Pydantic body parameter. FastAPI resolves both correctly -- the Pydantic model from the JSON body and the Starlette Request from the ASGI scope. Then pass the Starlette request into the helper functions (`_proxy_non_streaming`, `_stream_completion`) so they can set `target_node` after node selection. [CITED: https://fastapi.tiangolo.com/advanced/using-request-directly/]

**Example:**
```python
# Source: FastAPI docs "Using the Request Directly"
from fastapi import Request as StarletteRequest

@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,  # Pydantic body validation
    starlette_request: StarletteRequest,  # Raw Starlette request for state
    node_selector: NodeSelector = Depends(get_node_selector),
    proxy: ProxyClient = Depends(get_proxy_client),
    circuit_breaker_registry: CircuitBreakerRegistry = Depends(
        get_circuit_breaker_registry,
    ),
) -> JSONResponse | EventSourceResponse:
    body = request.model_dump(exclude_none=True)
    # Pass starlette_request to helpers for target_node tracking
    ...

# Inside _proxy_non_streaming, after selecting a node:
starlette_request.state.target_node = node.endpoint  # or node.node_id
```

**Note:** The `starlette_request` parameter name avoids shadowing the Pydantic `request` parameter. FastAPI recognizes the `Request` type hint and injects the current request automatically. [CITED: https://fastapi.tiangolo.com/advanced/using-request-directly/]

### Pattern 3: Separate Admin APIRouter

**What:** A dedicated `APIRouter` with `prefix="/admin"` and `tags=["admin"]` for the admin namespace.

**When to use:** Per D-05/D-06, admin endpoints are isolated from the `/v1` proxy API.

**Example:**
```python
# Source: FastAPI "Bigger Applications" pattern
# inference_proxy/api/admin.py
from fastapi import APIRouter, Depends
from inference_proxy.config.dependencies import get_registry
from inference_proxy.discovery.registry import NodeRegistry

admin_router = APIRouter(prefix="/admin", tags=["admin"])

@admin_router.get("/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
) -> list[AdminNodeResponse]:
    nodes = registry.get_all()
    return [
        AdminNodeResponse(
            node_id=n.node_id,
            endpoint=n.endpoint,
            model=n.model,
            status=n.status.value,
        )
        for n in nodes
    ]
```

### Pattern 4: Frozen Pydantic Response Model

**What:** A frozen Pydantic `BaseModel` for the admin node response, following the project's existing pattern.

**When to use:** All response schemas in this project use `ConfigDict(frozen=True)`.

**Example:**
```python
# inference_proxy/models/admin.py
from pydantic import BaseModel, ConfigDict

class AdminNodeResponse(BaseModel):
    """Admin API response for a single node."""
    model_config = ConfigDict(frozen=True)

    node_id: str
    endpoint: str
    model: str
    status: str  # String value of NodeStatus enum
```

### Anti-Patterns to Avoid

- **Per-route logging instead of middleware:** Violates D-01 and DRY. Every route would need its own log call, and adding new routes would require remembering to add logging.
- **Using contextvars for cross-layer data with BaseHTTPMiddleware:** `contextvars.ContextVar` values set in endpoints do NOT propagate back to `BaseHTTPMiddleware` dispatch due to task-group context copying. Use `request.state` instead (per D-04). [CITED: https://www.structlog.org/en/stable/contextvars.html]
- **Logging inside a try/except that swallows the exception:** The middleware should log ALL requests including failed ones. The `call_next` wrapper handles exceptions from route handlers, so the middleware sees the error response, not the raw exception.
- **Including admin endpoints in the `/v1` namespace:** Violates D-05. Admin operations are operational, not part of the OpenAI API contract.
- **Returning `Node` model directly from admin endpoint:** The `Node` model includes `last_heartbeat`, `capabilities`, `active_connections` which are not part of DISC-04 scope (D-07). Use a dedicated response model with only the four required fields.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured logging | Custom JSON formatter | structlog (already configured) | Processor pipeline handles JSON rendering, timestamping, log levels. Already in the project. |
| Request timing | Manual start/end time tracking per route | Middleware with `time.perf_counter()` | Centralizes timing in one place; middleware pattern ensures consistency across all routes. |
| Response model serialization | Manual dict construction | Pydantic BaseModel | Type safety, validation, automatic JSON serialization. Already the project standard. |
| Thread-safe node data access | Manual locking | `NodeRegistry.get_all()` | Already provides thread-safe read access with lock-protected shallow copy. |

**Key insight:** This phase introduces no new dependencies or complex patterns. Everything is built from existing project infrastructure -- structlog for logging, BaseHTTPMiddleware for the middleware, APIRouter for the admin endpoint, and Pydantic for response models.

## Common Pitfalls

### Pitfall 1: Middleware Ordering (LoggingMiddleware vs ShutdownMiddleware)

**What goes wrong:** If LoggingMiddleware is added before ShutdownMiddleware in `main.py`, it becomes the inner middleware. ShutdownMiddleware's 503 responses during shutdown bypass LoggingMiddleware entirely, so shutdown rejections are not logged.
**Why it happens:** FastAPI middleware stacking is LIFO -- the last middleware added via `app.add_middleware()` wraps outermost and runs first.
**How to avoid:** Add LoggingMiddleware AFTER ShutdownMiddleware in `create_app()`:
```python
application.add_middleware(ShutdownMiddleware)    # inner (added first)
application.add_middleware(RequestLoggingMiddleware)  # outer (added second)
```
**Warning signs:** Shutdown 503 responses missing from logs. [CITED: https://fastapi.tiangolo.com/tutorial/middleware/]

### Pitfall 2: contextvars vs request.state with BaseHTTPMiddleware

**What goes wrong:** If you try to use `structlog.contextvars.bind_contextvars(target_node=...)` in a route handler and read it in the middleware after `call_next`, the binding is invisible because BaseHTTPMiddleware runs the downstream app in a separate task with a copied context.
**Why it happens:** `BaseHTTPMiddleware` uses `anyio.create_task_group()` internally, which copies the context. Context variable changes in the child task don't propagate back to the parent.
**How to avoid:** Use `request.state.target_node` (D-04), not contextvars, for passing data from route handlers to middleware. `request.state` is backed by the shared ASGI `scope` dict, which IS shared across task boundaries. [CITED: https://github.com/encode/starlette/blob/master/starlette/middleware/base.py]
**Warning signs:** `target_node` always appearing as `None` in log entries for proxy routes.

### Pitfall 3: Naming Conflict with `request` Parameter

**What goes wrong:** The current route handlers use `request: ChatCompletionRequest` as the Pydantic body parameter name. Adding `request: Request` for the Starlette Request creates a naming collision.
**Why it happens:** FastAPI uses type hints to resolve parameters -- `Request` type is special-cased as the raw request. But two parameters named `request` is invalid Python.
**How to avoid:** Name the Starlette Request parameter differently, e.g., `starlette_request: Request`. FastAPI resolves it by type hint, not by name. [CITED: https://fastapi.tiangolo.com/advanced/using-request-directly/]
**Warning signs:** `TypeError` or unexpected behavior during request handling.

### Pitfall 4: Logging Duration for Streaming Responses

**What goes wrong:** For streaming SSE responses, `call_next` returns immediately with the `EventSourceResponse` object -- the actual streaming hasn't completed yet. The duration logged by the middleware is only the time to create the response object, not the total streaming duration.
**Why it happens:** SSE responses are async generators. The middleware sees the response headers (200) immediately, but the body streams over time.
**How to avoid:** Accept this behavior as correct for v1 -- the logged duration represents time-to-first-byte (TTFB), which is still valuable for diagnostics. Total streaming duration would require wrapping the response body, which is out of scope.
**Warning signs:** Very fast duration_ms values for streaming requests. This is expected, not a bug.

### Pitfall 5: Missing target_node for Non-Proxy Routes

**What goes wrong:** Accessing `request.state.target_node` raises `AttributeError` for routes that don't set it (/health, /v1/models, /admin/nodes).
**Why it happens:** `request.state` attributes don't exist until set. Non-proxy routes never call node selection.
**How to avoid:** Use `getattr(request.state, "target_node", None)` in the middleware (D-03 specifies null/absent for non-proxy routes).
**Warning signs:** Middleware crashes on /health or /v1/models requests.

## Code Examples

### RequestLoggingMiddleware (Complete)

```python
# Source: Project pattern (ShutdownMiddleware) + structlog docs + FastAPI middleware docs
"""Request logging middleware for structured observability.

Produces a structured JSON log entry for every HTTP request containing
method, path, status_code, duration_ms, and target_node (per OBSV-01).

Per D-01: Single middleware, not per-route logging.
Per D-02: OBSV-01 minimum fields only.
Per D-03: Logs ALL requests; target_node is null for non-proxy routes.
Per D-04: Reads target_node from request.state (set by route handlers).
"""
from __future__ import annotations

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, duration, and target node."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        target_node: str | None = getattr(request.state, "target_node", None)

        logger.info(
            "request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            target_node=target_node,
        )
        return response
```

### Admin Endpoint (Complete)

```python
# Source: FastAPI "Bigger Applications" pattern + project DI pattern
"""Admin API for operational visibility into the gateway.

Per D-05: Endpoints under /admin namespace.
Per D-06: Separate APIRouter in api/admin.py.
Per D-07: Core fields only (node_id, endpoint, model, status).
Per D-08: Flat node list response.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from inference_proxy.config.dependencies import get_registry
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.admin import AdminNodeResponse

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
) -> list[AdminNodeResponse]:
    """Return all registered nodes with their models and health status."""
    nodes = registry.get_all()
    return [
        AdminNodeResponse(
            node_id=n.node_id,
            endpoint=n.endpoint,
            model=n.model,
            status=n.status.value,
        )
        for n in nodes
    ]
```

### Route Handler Modification (request.state.target_node)

```python
# Source: FastAPI "Using the Request Directly" docs
# Modified route handler showing how to pass Starlette request for target_node

from fastapi import Request as StarletteRequest

@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    starlette_request: StarletteRequest,  # NEW: for request.state
    node_selector: NodeSelector = Depends(get_node_selector),
    proxy: ProxyClient = Depends(get_proxy_client),
    circuit_breaker_registry: CircuitBreakerRegistry = Depends(
        get_circuit_breaker_registry,
    ),
) -> JSONResponse | EventSourceResponse:
    body = request.model_dump(exclude_none=True)
    settings = get_settings()
    if request.stream:
        return await _stream_completion(
            endpoint_path="/v1/chat/completions",
            body=body,
            node_selector=node_selector,
            proxy=proxy,
            circuit_breaker_registry=circuit_breaker_registry,
            starlette_request=starlette_request,  # NEW
        )
    return await _proxy_non_streaming(
        "/v1/chat/completions",
        body,
        node_selector,
        proxy,
        circuit_breaker_registry=circuit_breaker_registry,
        max_retries=settings.routing.max_retries,
        starlette_request=starlette_request,  # NEW
    )

# Inside _proxy_non_streaming, after node selection:
async def _proxy_non_streaming(
    endpoint_path: str,
    body: dict[str, Any],
    node_selector: NodeSelector,
    proxy: ProxyClient,
    circuit_breaker_registry: CircuitBreakerRegistry,
    max_retries: int = 3,
    starlette_request: StarletteRequest | None = None,  # NEW
) -> JSONResponse:
    # ... existing logic ...
    node = node_selector.select(model=model, exclude_node_ids=excluded or None)
    if node is not None and starlette_request is not None:
        starlette_request.state.target_node = node.endpoint  # NEW
    # ... rest of existing logic ...
```

### main.py Integration

```python
# Source: Existing main.py pattern
from inference_proxy.api.admin import admin_router
from inference_proxy.api.middleware import RequestLoggingMiddleware

# In create_app():
application.add_middleware(ShutdownMiddleware)        # inner
application.add_middleware(RequestLoggingMiddleware)   # outer (logs everything)

application.include_router(router)           # existing proxy routes
application.include_router(admin_router)     # NEW: admin routes
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.middleware("http")` function decorator | `BaseHTTPMiddleware` class | Starlette 0.13+ | Class-based approach is cleaner for stateful middleware, matches project pattern |
| `time.time()` for duration | `time.perf_counter()` | Python 3.3+ | Monotonic clock, not affected by system clock changes |
| Manual dict logging | structlog structured logging | Project standard | JSON output in production, console in dev, processor pipeline for enrichment |
| Per-route logging | Middleware logging | Standard practice | Single point of logging, consistent format, no missed routes |

**Deprecated/outdated:**
- `@app.middleware("http")` decorator: Still works but class-based `BaseHTTPMiddleware` is preferred for this project (matches `ShutdownMiddleware` pattern)
- `time.time()`: Not monotonic; affected by NTP adjustments and manual clock changes

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this
> section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Place middleware in `inference_proxy/api/middleware.py` and admin model in `inference_proxy/models/admin.py` | Recommended Project Structure | Low -- module placement is a discretion area per CONTEXT.md; easy to relocate |
| A2 | Use `time.perf_counter()` over `time.monotonic()` | Pattern 1 / Discretion | Very low -- both are monotonic; on CPython 3.13+ they use the same clock; either works for ms-precision |
| A3 | Log all requests at `info` level uniformly | Pattern 1 / Discretion | Low -- could differentiate levels (debug for /health, info for proxy routes) but uniform info is simpler and matches D-03 "logs ALL requests" intent |
| A4 | Include admin router in OpenAPI docs (via `tags=["admin"]`) | Pattern 3 / Discretion | Very low -- visible in docs aids debugging; can exclude later with `include_in_schema=False` if needed |
| A5 | Use `node.endpoint` (not `node.node_id`) as the `target_node` value in log entries | Pattern 2 | Low -- endpoint is more useful operationally (shows actual host:port); node_id is an internal identifier |

**If this table is empty:** N/A -- 5 assumptions listed above.

## Open Questions (RESOLVED)

1. **What value should `target_node` contain -- `node.endpoint` or `node.node_id`?** RESOLVED
   - What we know: D-04 says "target node" generically. `node.endpoint` is the `host:port` string; `node.node_id` is the unique identifier.
   - Resolution: Use `node.endpoint` (the `host:port` string) as it's directly actionable for debugging network issues. Adopted in Plan 06-01.

2. **Should streaming requests update `target_node` even though duration is TTFB-only?** RESOLVED
   - What we know: For streaming responses, middleware sees the response immediately (before streaming completes). Duration is time-to-first-byte, not total request time.
   - Resolution: Yes, set target_node for streaming requests. Knowing which node handled a streaming request is valuable even if duration is TTFB. Adopted in Plan 06-01.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 1.4+ |
| Config file | `pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `uv run pytest tests/ -x --tb=short -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OBSV-01 | Middleware logs method, path, status, duration_ms, target_node | unit + integration | `uv run pytest tests/api/test_middleware.py -x` | No -- Wave 0 |
| OBSV-01 | Duration is positive number | unit | `uv run pytest tests/api/test_middleware.py::TestRequestLoggingDuration -x` | No -- Wave 0 |
| OBSV-01 | target_node is null for non-proxy routes | integration | `uv run pytest tests/api/test_middleware.py::TestRequestLoggingTargetNode -x` | No -- Wave 0 |
| OBSV-01 | target_node is set for proxy routes | integration | `uv run pytest tests/api/test_middleware.py::TestRequestLoggingTargetNode -x` | No -- Wave 0 |
| DISC-04 | GET /admin/nodes returns node list | unit | `uv run pytest tests/api/test_admin.py -x` | No -- Wave 0 |
| DISC-04 | Response includes node_id, endpoint, model, status per node | unit | `uv run pytest tests/api/test_admin.py::TestAdminNodesResponse -x` | No -- Wave 0 |
| DISC-04 | Empty registry returns empty list | unit | `uv run pytest tests/api/test_admin.py::TestAdminNodesEmpty -x` | No -- Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/api/test_middleware.py tests/api/test_admin.py -x --tb=short -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/api/test_middleware.py` -- covers OBSV-01 (logging middleware behavior)
- [ ] `tests/api/test_admin.py` -- covers DISC-04 (admin endpoint behavior)
- [ ] `tests/models/test_admin.py` -- covers AdminNodeResponse model validation

*(No framework install needed -- pytest and pytest-asyncio are already configured and 213 tests pass.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Admin endpoint has no auth in v1 (internal network per project constraints) |
| V3 Session Management | No | Stateless proxy; no sessions |
| V4 Access Control | No | No authorization controls in v1 (internal network) |
| V5 Input Validation | Yes | Admin endpoint has no user input; logging middleware uses `getattr` with default for safe access |
| V6 Cryptography | No | No cryptographic operations in this phase |

### Known Threat Patterns for Logging + Admin

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Log injection (user-controlled data in log fields) | Tampering | structlog handles escaping in JSON renderer; `path` comes from HTTP request URL, not request body. No user-controlled strings in OBSV-01 fields. |
| Information disclosure via admin endpoint | Information Disclosure | Per project constraints: internal network only. No sensitive data exposed (only node_id, endpoint, model, status). |
| Log flooding / DoS | Denial of Service | Per D-03: logs ALL requests. If under high load, log volume scales linearly. Acceptable for v1 internal use. |

## Sources

### Primary (HIGH confidence)
- structlog 26.1.0 contextvars documentation: https://www.structlog.org/en/stable/contextvars.html -- verified `merge_contextvars`, `bind_contextvars`, `clear_contextvars` API
- FastAPI middleware documentation: https://fastapi.tiangolo.com/tutorial/middleware/ -- middleware ordering, `call_next`, process time pattern
- FastAPI "Using the Request Directly": https://fastapi.tiangolo.com/advanced/using-request-directly/ -- accessing Starlette Request alongside Pydantic body
- FastAPI "Bigger Applications": https://fastapi.tiangolo.com/tutorial/bigger-applications/ -- APIRouter with prefix pattern
- Starlette BaseHTTPMiddleware source: https://github.com/encode/starlette/blob/master/starlette/middleware/base.py -- `request.state` works across task boundaries
- Starlette BaseHTTPMiddleware test suite: https://github.com/encode/starlette/blob/master/tests/middleware/test_base.py -- confirms `request.state` set in endpoint is readable in middleware post-`call_next`

### Secondary (MEDIUM confidence)
- Angelos Panagiotopoulos structlog + FastAPI blog: https://www.angelospanag.me/blog/structured-logging-using-structlog-and-fastapi -- real-world middleware patterns
- Apitally FastAPI logging guide: https://apitally.io/blog/fastapi-logging-guide -- request vs application logging categorization
- Python docs time.perf_counter: https://docs.python.org/3/library/time.html -- monotonic, high-resolution clock

### Tertiary (LOW confidence)
- None -- all findings verified against primary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies; all libraries already in project and verified
- Architecture: HIGH -- follows established project patterns (ShutdownMiddleware, APIRouter, Pydantic models)
- Pitfalls: HIGH -- verified critical `request.state` vs `contextvars` behavior against Starlette source/tests

**Research date:** 2026-06-25
**Valid until:** 2026-07-25 (stable domain, no fast-moving dependencies)
