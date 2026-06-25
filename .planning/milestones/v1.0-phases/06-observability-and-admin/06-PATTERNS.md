# Phase 6: Observability and Admin - Pattern Map

**Mapped:** 2026-06-25
**Files analyzed:** 7 new/modified files
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/api/middleware.py` | middleware | request-response | `inference_proxy/resilience/shutdown.py` | exact |
| `inference_proxy/api/admin.py` | controller | request-response | `inference_proxy/api/routes.py` (GET /v1/models) | exact |
| `inference_proxy/models/admin.py` | model | transform | `inference_proxy/models/node.py` | exact |
| `inference_proxy/api/routes.py` | controller | request-response | self (existing file, modification) | exact |
| `inference_proxy/main.py` | config | request-response | self (existing file, modification) | exact |
| `tests/api/test_middleware.py` | test | request-response | `tests/resilience/test_shutdown.py` | exact |
| `tests/api/test_admin.py` | test | request-response | `tests/api/test_routes.py` (TestListModels) | exact |

## Pattern Assignments

### `inference_proxy/api/middleware.py` (middleware, request-response)

**Analog:** `inference_proxy/resilience/shutdown.py`

**Imports pattern** (lines 1-22):
```python
"""Docstring with decision references (D-XX) and purpose."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
```

**Core middleware pattern** (lines 25-51):
```python
class ShutdownMiddleware(BaseHTTPMiddleware):
    """Docstring explaining the middleware's single responsibility."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        """Check shutdown state and either reject or pass through."""
        shutting_down: bool = getattr(request.app.state, "shutting_down", False)

        if shutting_down and request.url.path != "/health":
            return JSONResponse(
                status_code=503,
                content={...},
            )

        return await call_next(request)
```

**Key patterns to copy:**
- `BaseHTTPMiddleware` subclass with single `dispatch` method
- `getattr(request.app.state, ..., default)` for safe state access (use `getattr(request.state, "target_node", None)` for the logging middleware)
- Docstring references phase decisions (D-01 through D-04)
- `from __future__ import annotations` at top

**Structlog logger pattern** (from `inference_proxy/api/routes.py` line 46):
```python
import structlog

logger = structlog.get_logger()
```

---

### `inference_proxy/api/admin.py` (controller, request-response)

**Analog:** `inference_proxy/api/routes.py` (lines 23-48 for imports/router, lines 284-313 for GET endpoint)

**Imports pattern** (lines 17-48):
```python
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from inference_proxy.config.dependencies import (
    get_node_selector,  # or get_registry for admin
)
```

**Router instantiation** (line 48):
```python
router = APIRouter()
```
For admin, use prefix and tags:
```python
admin_router = APIRouter(prefix="/admin", tags=["admin"])
```

**GET endpoint with DI pattern** (lines 284-313):
```python
@router.get("/v1/models")
async def list_models(
    node_selector: NodeSelector = Depends(get_node_selector),
) -> JSONResponse:
    """Docstring explaining the endpoint."""
    nodes = node_selector._registry.get_all()
    # ... transform nodes into response ...
    return JSONResponse(content={...})
```
For admin, inject `NodeRegistry` directly:
```python
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

**DI provider pattern** (from `inference_proxy/config/dependencies.py` lines 33-40):
```python
def get_registry(request: Request) -> NodeRegistry:
    """Return the node registry from the current application state."""
    return request.app.state.registry  # type: ignore[no-any-return]
```
This already exists -- no new DI provider needed.

---

### `inference_proxy/models/admin.py` (model, transform)

**Analog:** `inference_proxy/models/node.py` (lines 29-35 for frozen model pattern)

**Frozen model pattern** (lines 29-35):
```python
class NodeCapabilities(BaseModel):
    """Hardware and serving capabilities of a node."""

    model_config = ConfigDict(frozen=True)

    max_tokens: int = 4096
    gpu_memory: str = ""
```

**Imports pattern** (lines 1-7):
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
```

**Key patterns to copy:**
- `model_config = ConfigDict(frozen=True)` for immutable response models
- Module-level docstring with decision references
- Simple field declarations with type annotations
- Note: `openai.py` uses `ConfigDict(extra="allow")` for request models, but response/admin models use `ConfigDict(frozen=True)`

---

### `inference_proxy/api/routes.py` (modification: add `starlette_request` parameter)

**Analog:** Self -- the existing route handler pattern (lines 216-247)

**Current handler signature** (lines 216-224):
```python
@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    node_selector: NodeSelector = Depends(get_node_selector),
    proxy: ProxyClient = Depends(get_proxy_client),
    circuit_breaker_registry: CircuitBreakerRegistry = Depends(
        get_circuit_breaker_registry,
    ),
) -> JSONResponse | EventSourceResponse:
```

**Modification:** Add `starlette_request: Request` parameter to `chat_completions` and `text_completions`, then pass it through to `_proxy_non_streaming` and `_stream_completion` so they can set `request.state.target_node` after node selection.

**Target location in `_proxy_non_streaming`** (lines 169-180): After `node = node_selector.select(...)`, before the proxy call:
```python
node = node_selector.select(
    model=model,
    exclude_node_ids=excluded or None,
)
if node is None:
    # ... error handling ...
# NEW: set target_node for logging middleware
if starlette_request is not None:
    starlette_request.state.target_node = node.endpoint
```

**Target location in `_stream_completion`** (lines 335-337): After `node = node_selector.select(model=model)`:
```python
node = node_selector.select(model=model)
if node is None:
    # ... error handling ...
# NEW: set target_node for logging middleware
if starlette_request is not None:
    starlette_request.state.target_node = node.endpoint
```

---

### `inference_proxy/main.py` (modification: add middleware + admin router)

**Analog:** Self -- the existing middleware and router inclusion pattern (lines 179-198)

**Middleware addition pattern** (line 185):
```python
application.add_middleware(ShutdownMiddleware)
```

**Router inclusion pattern** (line 198):
```python
application.include_router(router)
```

**Import pattern** (lines 26-38):
```python
from inference_proxy.api.routes import router
from inference_proxy.resilience.shutdown import ShutdownMiddleware
```

**Modification:** Add two imports and two lines in `create_app()`:
```python
# New imports:
from inference_proxy.api.admin import admin_router
from inference_proxy.api.middleware import RequestLoggingMiddleware

# In create_app(), AFTER ShutdownMiddleware (LIFO -- last added is outermost):
application.add_middleware(ShutdownMiddleware)        # inner (existing)
application.add_middleware(RequestLoggingMiddleware)   # outer (NEW)

application.include_router(router)           # existing proxy routes
application.include_router(admin_router)     # NEW: admin routes
```

---

### `tests/api/test_middleware.py` (test, request-response)

**Analog:** `tests/resilience/test_shutdown.py`

**Test file structure** (lines 1-31):
```python
"""Integration tests for the request logging middleware.

Tests cover:
- bullet list of test scenarios
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node, NodeStatus


def _make_node(
    node_id: str = "node-1",
    endpoint: str = "10.0.1.100:8000",
    status: NodeStatus = NodeStatus.HEALTHY,
    model: str = "llama-3",
) -> Node:
    """Create a test node with sensible defaults."""
    return Node(
        node_id=node_id,
        endpoint=endpoint,
        status=status,
        model=model,
    )
```

**Test class pattern** (lines 34-55):
```python
class TestShutdownMiddlewareRejects503:
    """Descriptive class docstring."""

    def test_post_returns_503_during_shutdown(
        self,
        app: FastAPI,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """Descriptive test docstring."""
        # Arrange: set app state, add nodes
        app.state.shutting_down = True
        test_registry.add(_make_node())

        # Act: make HTTP request
        response = client.post(
            "/v1/chat/completions",
            json={...},
        )

        # Assert: check status and response body
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "shutting_down"
```

**Key patterns to copy:**
- Use existing `conftest.py` fixtures: `app`, `client`, `test_registry`, `node_selector`, `httpx_mock`
- Class-based test organization with descriptive docstrings
- `_make_node()` helper for creating test nodes (or import from conftest if shared)
- Tests use `TestClient` (sync), not async
- Fixtures injected via pytest parameter names matching `conftest.py`

**For log capture testing:** Use `caplog` or a custom structlog capture. Since structlog uses `PrintLoggerFactory`, you can capture via `capsys` or configure a test logger that collects log entries.

---

### `tests/api/test_admin.py` (test, request-response)

**Analog:** `tests/api/test_routes.py` (TestListModels, lines 326-380)

**Test class for GET endpoint** (lines 326-380):
```python
class TestListModels:
    """GET /v1/models returns aggregated model list from registry."""

    def test_list_models_returns_registered_models(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """Two nodes with different models return two model entries."""
        test_registry.add(_make_node(node_id="node-1", model="llama-3"))
        test_registry.add(
            _make_node(node_id="node-2", endpoint="10.0.1.101:8000", model="mistral-7b")
        )

        response = client.get("/v1/models")

        assert response.status_code == 200
        data = response.json()
        # ... assertions on response structure ...

    def test_list_models_empty_registry(
        self,
        client: TestClient,
    ) -> None:
        """Empty registry returns empty model list."""
        response = client.get("/v1/models")

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
```

**Key patterns to copy for admin tests:**
- Same fixture pattern (`client`, `test_registry`) from `conftest.py`
- Test populated registry, empty registry, and field validation
- Use `response.json()` to deserialize and assert on structure
- `_make_node()` helper with test defaults

---

## Shared Patterns

### Structlog Logger
**Source:** `inference_proxy/api/routes.py` line 46
**Apply to:** `inference_proxy/api/middleware.py`, `inference_proxy/api/admin.py`
```python
import structlog

logger = structlog.get_logger()
```

### `from __future__ import annotations`
**Source:** Every source file in the project
**Apply to:** All new files
```python
from __future__ import annotations
```

### Frozen Pydantic BaseModel
**Source:** `inference_proxy/models/node.py` lines 29-35
**Apply to:** `inference_proxy/models/admin.py`
```python
from pydantic import BaseModel, ConfigDict

class AdminNodeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    # fields...
```

### FastAPI Dependency Injection
**Source:** `inference_proxy/config/dependencies.py` lines 33-40
**Apply to:** `inference_proxy/api/admin.py`
```python
def get_registry(request: Request) -> NodeRegistry:
    """Return the node registry from the current application state."""
    return request.app.state.registry  # type: ignore[no-any-return]
```
Already exists -- admin endpoint uses `Depends(get_registry)`.

### Test Fixture Pattern
**Source:** `tests/conftest.py` lines 83-106
**Apply to:** `tests/api/test_middleware.py`, `tests/api/test_admin.py`
```python
@pytest.fixture
def app(
    test_settings: Settings,
    test_registry: NodeRegistry,
    proxy_client: ProxyClient,
    node_selector: NodeSelector,
    circuit_breaker_registry: CircuitBreakerRegistry,
) -> Generator[FastAPI, None, None]:
    """Create a FastAPI app with test settings, registry, and proxy client injected."""
    application = create_app(settings=test_settings)
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.state.registry = test_registry
    # ... more state and overrides ...
    yield application
    application.dependency_overrides.clear()
    get_settings.cache_clear()

@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Return a TestClient bound to the test app."""
    return TestClient(app)
```
Existing fixtures handle all DI wiring. New test files just consume `app`, `client`, `test_registry`, `node_selector`.

### Module Docstring Pattern
**Source:** `inference_proxy/resilience/shutdown.py` lines 1-16
**Apply to:** All new files
```python
"""Module purpose sentence.

Details on what this module does and references to decisions:
Per D-XX: description of the decision.
"""
```

## No Analog Found

No files in this phase lack a close analog. All new files map directly to existing patterns in the codebase.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | -- | -- | -- |

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 26 source files, 15 test files
**Pattern extraction date:** 2026-06-25
