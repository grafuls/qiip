# Phase 3: Request Proxying and Streaming - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 12 new/modified files
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/proxy/__init__.py` | config | -- | `inference_proxy/api/__init__.py` | exact |
| `inference_proxy/proxy/client.py` | service | request-response | `inference_proxy/discovery/etcd_client.py` | role-match |
| `inference_proxy/proxy/node_selector.py` | utility | transform | `inference_proxy/discovery/serializer.py` | role-match |
| `inference_proxy/api/routes.py` | controller | request-response + streaming | `inference_proxy/main.py` (health route) | role-match |
| `inference_proxy/api/errors.py` | utility | transform | `inference_proxy/discovery/serializer.py` | partial-match |
| `inference_proxy/config/settings.py` (modify) | config | -- | `inference_proxy/config/settings.py` | exact (self) |
| `inference_proxy/config/dependencies.py` (modify) | provider | -- | `inference_proxy/config/dependencies.py` | exact (self) |
| `inference_proxy/main.py` (modify) | controller | -- | `inference_proxy/main.py` | exact (self) |
| `tests/proxy/__init__.py` | config | -- | `tests/discovery/__init__.py` | exact |
| `tests/proxy/test_client.py` | test | request-response | `tests/discovery/test_etcd_client.py` | role-match |
| `tests/proxy/test_node_selector.py` | test | transform | `tests/discovery/test_registry.py` | role-match |
| `tests/api/test_routes.py` | test | request-response + streaming | `tests/test_app.py` | role-match |
| `tests/api/test_errors.py` | test | transform | `tests/models/test_openai.py` | partial-match |
| `tests/api/__init__.py` | config | -- | `tests/discovery/__init__.py` | exact |

## Pattern Assignments

### `inference_proxy/proxy/client.py` (service, request-response)

**Analog:** `inference_proxy/discovery/etcd_client.py`

**Imports pattern** (lines 1-9):
```python
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import structlog
from etcd3gw.client import Etcd3Client

from inference_proxy.config.settings import EtcdSettings
```

New file should follow the same structure -- wrap an external library (`httpx.AsyncClient`) behind a typed interface, accept settings via constructor, expose only the operations consumers need:

```python
from __future__ import annotations

import httpx
import structlog
```

**Core wrapper pattern** (lines 26-55) -- constructor accepts settings, wraps external client:
```python
class EtcdClient:
    def __init__(self, settings: EtcdSettings) -> None:
        # ... parse settings ...
        self._client = Etcd3Client(
            host=parsed.hostname,
            port=parsed.port or 2379,
            protocol=parsed.scheme,
        )
        self._prefix = settings.node_prefix

    @property
    def prefix(self) -> str:
        return self._prefix
```

ProxyClient should follow this pattern: constructor wraps a pre-built `httpx.AsyncClient`, exposes typed methods (`forward`, `client` property for SSE). Unlike EtcdClient which builds the client internally, ProxyClient receives a pre-built client (created in lifespan for connection pool lifecycle management).

**Docstring convention** (lines 1-6):
```python
"""Thin wrapper around etcd3gw providing typed node operations.

This module is the **sole consumer** of ``etcd3gw`` in the codebase,
following the Dependency Inversion Principle (DIP): all other modules
depend on this wrapper rather than importing ``etcd3gw`` directly.
"""
```

---

### `inference_proxy/proxy/node_selector.py` (utility, transform)

**Analog:** `inference_proxy/discovery/serializer.py`

Let me read it for the pattern.

**Imports and structure** -- pure function module, no class, stateless transform:
```python
# From serializer.py (inferred structure -- same project, pure function module)
from __future__ import annotations

import structlog

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node

logger = structlog.get_logger()
```

Node selector should be a pure function `select_node(registry: NodeRegistry) -> Node | None` following the serializer pattern of stateless utility functions. Returns `None` when no nodes are available (Phase 3: first available; Phase 4 replaces with strategy).

---

### `inference_proxy/api/routes.py` (controller, request-response + streaming)

**Analog:** `inference_proxy/main.py` (lines 121-131)

**Route definition pattern** (lines 121-131):
```python
application = FastAPI(
    title="QUADS LLM Inference Proxy",
    version="0.1.0",
    lifespan=lifespan,
)

@application.get("/health")
async def health() -> JSONResponse:
    """Return gateway health status."""
    return JSONResponse(content={"status": "ok"})
```

New routes should use `APIRouter` instead of defining on the app directly. The existing health endpoint will be migrated to the router or the router will be `include_router`-ed alongside it. Key conventions from the existing code:
- Return `JSONResponse` explicitly (not bare dicts)
- Async handler functions
- Single-line docstrings
- Type annotations on return

**Dependency injection pattern** from `config/dependencies.py` (lines 28-35):
```python
def get_registry(request: Request) -> NodeRegistry:
    """Return the node registry from the current application state."""
    return request.app.state.registry  # type: ignore[no-any-return]
```

Route handlers use `Depends(get_registry)` and will similarly use `Depends(get_proxy_client)`.

**Import conventions** from `main.py` (lines 14-30):
```python
from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from inference_proxy.config.dependencies import get_settings
from inference_proxy.config.settings import Settings
from inference_proxy.discovery.registry import NodeRegistry
```

Pattern: stdlib first, then third-party (fastapi, structlog), then local imports. All from the `inference_proxy` package using absolute paths.

---

### `inference_proxy/api/errors.py` (utility, transform)

**Analog:** `inference_proxy/models/openai.py` (lines 167-179) -- the error models this module will consume

**Error model definitions** (lines 167-179):
```python
class ErrorDetail(BaseModel):
    """Error detail matching the OpenAI error schema."""

    message: str
    type: str
    param: str | None = None
    code: str | int | None = None


class ErrorResponse(BaseModel):
    """Error response wrapper matching the OpenAI error schema."""

    error: ErrorDetail
```

The `errors.py` module should be a pure function module (like `serializer.py`) that maps exceptions to `(status_code, ErrorResponse)` tuples. Import and use the existing `ErrorDetail` and `ErrorResponse` models -- do not redefine them.

---

### `inference_proxy/config/settings.py` (modify -- add ProxySettings)

**Analog:** Self -- `inference_proxy/config/settings.py`

**Nested settings pattern** (lines 12-17, 19-31, 34-40):
```python
class GatewaySettings(BaseModel):
    """Gateway server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080


class EtcdSettings(BaseModel):
    """etcd service discovery configuration."""

    endpoints: list[str] = ["http://localhost:2379"]
    node_prefix: str = "/nodes/"

    @field_validator("endpoints")
    @classmethod
    def endpoints_must_be_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one etcd endpoint must be configured")
        return v


class RoutingSettings(BaseModel):
    """Request routing and load balancing configuration."""

    strategy: str = "least_connections"
    health_check_interval: int = 30
    max_retries: int = 3
    timeout: int = 30
```

New `ProxySettings` class should follow the same pattern: inherit `BaseModel` (not `BaseSettings`), provide sensible defaults, single-line docstring. Add to the root `Settings` class as `proxy: ProxySettings = ProxySettings()`.

---

### `inference_proxy/config/dependencies.py` (modify -- add get_proxy_client)

**Analog:** Self -- `inference_proxy/config/dependencies.py`

**Dependency provider pattern** (lines 22-35):
```python
@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()


def get_registry(request: Request) -> NodeRegistry:
    """Return the node registry from the current application state."""
    return request.app.state.registry  # type: ignore[no-any-return]
```

`get_proxy_client` should follow the `get_registry` pattern -- read from `request.app.state.proxy_client`. The proxy client is created in lifespan and stored in `app.state`, just like the registry.

---

### `inference_proxy/main.py` (modify -- lifespan + router)

**Analog:** Self -- `inference_proxy/main.py`

**Lifespan pattern** (lines 80-119):
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 1. Configure logging
    configure_logging(...)
    # 2. Create client and registry
    etcd_client = EtcdClient(resolved_settings.etcd)
    registry = NodeRegistry()
    # 3. Initial load
    _initial_load(etcd_client, registry)
    # 4. Start background thread
    stop_event = threading.Event()
    watch_thread = threading.Thread(...)
    watch_thread.start()
    # 5. Store in app.state
    app.state.registry = registry
    yield
    # 6. Cleanup
    stop_event.set()
    watch_thread.join(timeout=10)
```

Modifications needed:
- After registry setup, create `httpx.AsyncClient` and `ProxyClient`, store in `app.state.proxy_client`
- In shutdown (after yield), call `await http_client.aclose()`
- Include the API router via `application.include_router(router)`

**Router inclusion** -- add after app creation (line 121-125):
```python
application = FastAPI(
    title="QUADS LLM Inference Proxy",
    version="0.1.0",
    lifespan=lifespan,
)
# Add: application.include_router(router)
```

---

### `tests/proxy/test_client.py` (test, request-response)

**Analog:** `tests/discovery/test_registry.py`

**Test file structure** (lines 1-12):
```python
"""Unit tests for the thread-safe NodeRegistry.

Tests cover add, upsert, remove, get, get_all operations, copy-on-read
semantics, and concurrent thread safety.
"""

from __future__ import annotations

import threading

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node, NodeStatus
```

**Test class grouping pattern** (lines 20-29):
```python
class TestRegistryAdd:
    """add() stores a node retrievable by get(node_id)."""

    def test_add_stores_node(self) -> None:
        registry = NodeRegistry()
        node = _make_node()

        registry.add(node)

        assert registry.get("node-1") is not None
        assert registry.get("node-1") == node
```

Conventions:
- One test class per behavior/method
- Class docstring describes the behavior being tested
- Helper functions prefixed with `_` at module level (e.g., `_make_node`)
- Arrange-act-assert with blank lines separating sections
- Type annotations on all test methods (`-> None`)
- `from __future__ import annotations` at top

---

### `tests/proxy/test_node_selector.py` (test, transform)

**Analog:** `tests/discovery/test_registry.py`

Same test structure as above. Test `select_node` with:
- Empty registry returns `None`
- Single node returns that node
- Multiple nodes returns one (deterministic for Phase 3)

Helper: reuse `_make_node` pattern:
```python
def _make_node(node_id: str = "node-1", endpoint: str = "http://10.0.1.100:8000") -> Node:
    """Create a minimal Node for testing."""
    return Node(node_id=node_id, endpoint=endpoint)
```

---

### `tests/api/test_routes.py` (test, request-response + streaming)

**Analog:** `tests/test_app.py`

**Integration test pattern with TestClient** (lines 13-19):
```python
def test_health_endpoint(client: TestClient) -> None:
    """GET /health returns 200 with JSON containing 'status' key."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"
```

**Fixture usage** -- uses `client` fixture from `conftest.py` (lines 49-51):
```python
@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Return a TestClient bound to the test app."""
    return TestClient(app)
```

**Mock pattern** (lines 59-75):
```python
@patch("inference_proxy.main.run_watcher")
@patch("inference_proxy.main.EtcdClient")
def test_lifespan_creates_registry(
    self,
    mock_etcd_cls: MagicMock,
    mock_run_watcher: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_client.get_prefix.return_value = []
    mock_client.prefix = "/nodes/"
    mock_etcd_cls.return_value = mock_client
```

For API route tests, use `dependency_overrides` (from conftest.py lines 39-46):
```python
application = create_app(settings=test_settings)
application.dependency_overrides[get_settings] = lambda: test_settings
application.state.registry = test_registry
```

New route tests will need to:
- Override `get_proxy_client` to inject a mock ProxyClient
- Use `pytest-httpx`'s `HTTPXMock` / `IteratorStream` for SSE stream mocking
- Follow `asyncio_mode = "auto"` (from `pyproject.toml`)

---

### `tests/api/test_errors.py` (test, transform)

**Analog:** `tests/models/test_openai.py`

Tests for pure functions that map exceptions to error responses. Follow the same pattern as model tests: no fixtures needed, direct instantiation, assert on output structure.

---

## Shared Patterns

### Structured Logging
**Source:** `inference_proxy/discovery/watcher.py` (line 38), `inference_proxy/discovery/etcd_client.py` (line 18), `inference_proxy/main.py` (line 33)
**Apply to:** All new service and route files (`proxy/client.py`, `api/routes.py`, `api/errors.py`)
```python
import structlog

logger = structlog.get_logger()
```

Usage convention -- keyword arguments for structured context:
```python
logger.info("initial node load complete", node_count=count)
logger.warning(
    "etcd unavailable at startup, starting with empty registry",
    exc_info=True,
)
```

### Import Conventions
**Source:** All existing modules
**Apply to:** All new files
```python
from __future__ import annotations  # Always first line after docstring
```

Import order (enforced by ruff `I` rule):
1. `from __future__ import annotations`
2. stdlib imports
3. third-party imports (fastapi, httpx, structlog, pydantic)
4. local imports (`from inference_proxy.xxx import yyy`)

### Dependency Injection via app.state
**Source:** `inference_proxy/config/dependencies.py` (lines 28-35), `inference_proxy/main.py` (line 114)
**Apply to:** `proxy/client.py` (stored in app.state), `api/routes.py` (consumed via Depends), `config/dependencies.py` (new provider function)

Pattern:
1. Object created in lifespan, stored in `app.state.xxx`
2. `get_xxx(request: Request) -> Type` function in `dependencies.py`
3. Route handlers use `Depends(get_xxx)`
4. Tests use `app.dependency_overrides[get_xxx]`

### Pydantic Model Usage
**Source:** `inference_proxy/models/openai.py` (lines 28-44)
**Apply to:** `api/routes.py` (request validation), `api/errors.py` (error responses)

Request models use `extra='allow'` and `Field` constraints:
```python
class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    stream: bool = False
```

Error models for response construction:
```python
ErrorResponse(error=ErrorDetail(
    message="...",
    type="upstream_error",
    code="backend_unavailable",
))
```

### Test Helper Pattern
**Source:** `tests/discovery/test_registry.py` (lines 14-16)
**Apply to:** All new test files

```python
def _make_node(node_id: str = "node-1", endpoint: str = "http://10.0.1.100:8000") -> Node:
    """Create a minimal Node for testing."""
    return Node(node_id=node_id, endpoint=endpoint)
```

### conftest.py Fixture Pattern
**Source:** `tests/conftest.py` (lines 1-51)
**Apply to:** New fixtures needed for proxy tests

Existing fixtures available:
- `test_settings` -- Settings with test-safe defaults
- `test_registry` -- Empty NodeRegistry
- `app` -- FastAPI app with overrides
- `client` -- TestClient bound to app

New fixtures needed in `conftest.py`:
- `proxy_client` or `mock_http_client` -- mock ProxyClient for route tests
- Store in `app.state.proxy_client` and add `dependency_overrides[get_proxy_client]`

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | -- | -- | All Phase 3 files have analogs in the existing codebase |

Every new file has a close analog. The streaming SSE proxy pattern (consume + re-emit) is new to the codebase, but the route handler structure, dependency injection, service wrapper, and test patterns all have direct precedents.

## Notes on SSE-Specific Patterns

The SSE streaming proxy pattern is new to this codebase. No existing file demonstrates SSE consumption or emission. The planner should use the RESEARCH.md patterns (Pattern 2: Streaming SSE Proxy) as the primary reference for:

- `httpx_sse.aconnect_sse` for upstream consumption
- `fastapi.sse.EventSourceResponse` + `ServerSentEvent(raw_data=...)` for downstream emission
- `pytest_httpx.IteratorStream` for SSE test mocking

All other patterns (imports, DI, error handling, test structure) follow existing codebase conventions documented above.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 17 source files, 13 test files
**Pattern extraction date:** 2026-06-11
