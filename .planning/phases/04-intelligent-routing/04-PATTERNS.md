# Phase 4: Intelligent Routing - Pattern Map

**Mapped:** 2026-06-24
**Files analyzed:** 14 new/modified files
**Analogs found:** 14 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/routing/connection_tracker.py` (NEW) | service | request-response | `inference_proxy/discovery/registry.py` | role-match |
| `inference_proxy/routing/node_selector.py` (NEW) | service | request-response | `inference_proxy/proxy/node_selector.py` | exact |
| `inference_proxy/api/routes.py` (MOD) | controller | request-response | self (existing) | exact |
| `inference_proxy/api/errors.py` (MOD) | utility | transform | self (existing) | exact |
| `inference_proxy/config/dependencies.py` (MOD) | config | request-response | self (existing) | exact |
| `inference_proxy/main.py` (MOD) | config | request-response | self (existing) | exact |
| `inference_proxy/discovery/watcher.py` (MOD) | service | event-driven | self (existing) | exact |
| `inference_proxy/discovery/registry.py` (MOD) | service | CRUD | self (existing) | exact |
| `tests/routing/__init__.py` (NEW) | test | N/A | `tests/proxy/__init__.py` | exact |
| `tests/routing/test_connection_tracker.py` (NEW) | test | request-response | `tests/discovery/test_registry.py` | role-match |
| `tests/routing/test_node_selector.py` (NEW) | test | request-response | `tests/proxy/test_node_selector.py` | exact |
| `tests/api/test_routes.py` (MOD) | test | request-response | self (existing) | exact |
| `tests/api/test_errors.py` (MOD) | test | transform | self (existing) | exact |
| `tests/discovery/test_watcher.py` (MOD) | test | event-driven | self (existing) | exact |

## Pattern Assignments

### `inference_proxy/routing/connection_tracker.py` (NEW - service, request-response)

**Analog:** `inference_proxy/discovery/registry.py` -- thread-safe counter store following the same lock-protected dict pattern.

**Module docstring pattern** (registry.py lines 1-11):
```python
"""Thread-safe in-memory registry of discovered vLLM nodes.

Provides add/remove/get/get_all operations protected by a
``threading.Lock``.  The lock is required because the watch thread
(an OS thread, not a coroutine) mutates the registry while async
handlers read from it.

Per D-06: Nodes held in a ``dict[str, Node]`` protected by
``threading.Lock``.
Per D-08: Thread-safe methods ``add``, ``remove``, ``get``, ``get_all``.
"""
```

**Imports pattern** (registry.py lines 13-16):
```python
from __future__ import annotations

import threading

from inference_proxy.models.node import Node
```

**Core thread-safe dict pattern** (registry.py lines 20-50):
```python
class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._lock = threading.Lock()

    def add(self, node: Node) -> None:
        """Store or replace a node by its ``node_id``."""
        with self._lock:
            self._nodes[node.node_id] = node

    def remove(self, node_id: str) -> None:
        """Remove a node by its ``node_id``.  No-op if absent."""
        with self._lock:
            self._nodes.pop(node_id, None)

    def get(self, node_id: str) -> Node | None:
        """Return the node with the given ``node_id``, or ``None``."""
        with self._lock:
            return self._nodes.get(node_id)
```

**Apply to ConnectionTracker:** Use `dict[str, int]` keyed by `node_id` with `threading.Lock`. Expose `increment(node_id)`, `decrement(node_id)`, `get(node_id) -> int`, `get_all() -> dict[str, int]`, `remove(node_id)`. The context manager for connection tracking (D-02) should be a separate method or standalone contextmanager function that calls increment/decrement.

---

### `inference_proxy/routing/node_selector.py` (NEW - service, request-response)

**Analog:** `inference_proxy/proxy/node_selector.py` -- this is the file being replaced. Copy the import style, logging pattern, and filtering approach; change from pure function to strategy class (D-07).

**Imports pattern** (node_selector.py lines 1-16):
```python
"""Simple node selection for Phase 3 (first available healthy node).
...
"""

from __future__ import annotations

import structlog

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node, NodeStatus

logger = structlog.get_logger()
```

**Core selection logic pattern** (node_selector.py lines 20-47):
```python
def select_node(registry: NodeRegistry) -> Node | None:
    """Return the first healthy node from the registry, or ``None``."""
    nodes = registry.get_all()
    healthy = [n for n in nodes if n.status == NodeStatus.HEALTHY]

    if not healthy:
        logger.warning("no healthy nodes available", total_nodes=len(nodes))
        return None

    selected = healthy[0]
    logger.debug(
        "selected node",
        node_id=selected.node_id,
        endpoint=selected.endpoint,
        healthy_count=len(healthy),
    )
    return selected
```

**Apply to NodeSelector class:** Constructor takes `registry: NodeRegistry` and `tracker: ConnectionTracker`. Method `select(model: str | None = None) -> Node | None`:
1. Filter by `NodeStatus.HEALTHY` (skip DRAINING, UNHEALTHY, UNKNOWN)
2. If `model` is not None, filter by exact string match on `node.model` (D-05)
3. Sort by `tracker.get(node.node_id)` ascending (least connections)
4. Tie-break randomly among equal-count nodes (D-03)
5. Return selected node or None
6. Return value semantics: None when no nodes match (caller distinguishes 404 vs 503)

**DI pattern from ProxyClient** (client.py lines 23-35):
```python
class ProxyClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @property
    def client(self) -> httpx.AsyncClient:
        """Return the underlying httpx.AsyncClient for SSE streaming."""
        return self._client
```

**Apply:** NodeSelector stores `_registry` and `_tracker` via constructor injection. No base class needed -- there is only one strategy in Phase 4.

---

### `inference_proxy/api/routes.py` (MOD - controller, request-response)

**Analog:** self (existing file)

**Current select_node usage** (routes.py lines 46-49):
```python
    node = select_node(registry)
    if node is None:
        status, error_resp = no_nodes_error()
        return JSONResponse(content=error_resp.model_dump(), status_code=status)
```

**Replace with:** `node_selector.select(model=request.model)` where `request.model` comes from the `ChatCompletionRequest`/`CompletionRequest` Pydantic model. The `model` field already exists on both request models.

**Current DI pattern** (routes.py lines 66-69):
```python
@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    registry: NodeRegistry = Depends(get_registry),
    proxy: ProxyClient = Depends(get_proxy_client),
) -> JSONResponse | EventSourceResponse:
```

**Apply:** Add `node_selector: NodeSelector = Depends(get_node_selector)`. Remove `registry` dependency from route handlers since selection is now delegated to NodeSelector. Keep `proxy: ProxyClient` dependency.

**Connection tracking context manager (D-02) pattern -- wrap proxy calls:**
```python
# In _proxy_non_streaming and _stream_completion:
node = node_selector.select(model=body.get("model"))
if node is None:
    # return appropriate error (404 or 503 -- see errors.py changes)
    ...

# Context manager usage around proxy call:
tracker = node_selector.tracker  # or inject separately
tracker.increment(node.node_id)
try:
    response = await proxy.forward("POST", url, body)
    ...
finally:
    tracker.decrement(node.node_id)
```

**Error branching for model-aware routing (D-04, D-06):**
When `node_selector.select(model=...)` returns None, the route must distinguish:
- No nodes serve the model at all -> 404 model_not_found
- Nodes exist for the model but all are unhealthy/draining -> 503 model_unavailable
- No nodes registered at all -> 503 no_nodes (existing)

This requires the selector to communicate *why* it returned None, or the route handler queries the registry directly. The cleanest approach: `NodeSelector.select()` returns `Node | None`, and a separate method `NodeSelector.has_model(model) -> bool` checks existence. Or return a result object. Claude's discretion per context.

**List models endpoint** (routes.py lines 109-135) -- DRAINING node filtering:
Per Claude's discretion in CONTEXT.md, decide whether DRAINING nodes appear in `/v1/models`. The current implementation iterates all nodes. If DRAINING nodes should be excluded, add a status filter.

---

### `inference_proxy/api/errors.py` (MOD - utility, transform)

**Analog:** self (existing file)

**Existing error factory pattern** (errors.py lines 74-86):
```python
def no_nodes_error() -> tuple[int, ErrorResponse]:
    """Return a 503 error response for when no inference nodes are available."""
    return 503, ErrorResponse(
        error=ErrorDetail(
            message="No inference nodes available",
            type="server_error",
            code="no_nodes",
        )
    )
```

**Apply -- add two new factories following same pattern:**

```python
def model_not_found_error(model: str) -> tuple[int, ErrorResponse]:
    """Return a 404 error when the requested model is not served by any node (D-04)."""
    return 404, ErrorResponse(
        error=ErrorDetail(
            message=f"The model '{model}' does not exist",
            type="invalid_request_error",
            code="model_not_found",
        )
    )

def model_unavailable_error(model: str) -> tuple[int, ErrorResponse]:
    """Return a 503 error when model exists but all nodes are unhealthy/draining (D-06)."""
    return 503, ErrorResponse(
        error=ErrorDetail(
            message=f"The model '{model}' is temporarily unavailable",
            type="server_error",
            code="model_unavailable",
        )
    )
```

Note: D-04 specifies the exact OpenAI error schema: `{"error": {"type": "invalid_request_error", "message": "model not found"}}`. The `ErrorDetail` and `ErrorResponse` Pydantic models (from `models/openai.py` lines 167-179) already support this shape.

---

### `inference_proxy/config/dependencies.py` (MOD - config, request-response)

**Analog:** self (existing file)

**Existing DI function pattern** (dependencies.py lines 31-48):
```python
def get_registry(request: Request) -> NodeRegistry:
    """Return the node registry from the current application state."""
    return request.app.state.registry  # type: ignore[no-any-return]


def get_proxy_client(request: Request) -> ProxyClient:
    """Return the proxy client from the current application state."""
    return request.app.state.proxy_client  # type: ignore[no-any-return]
```

**Apply -- add `get_node_selector` following identical pattern:**

```python
from inference_proxy.routing.node_selector import NodeSelector

def get_node_selector(request: Request) -> NodeSelector:
    """Return the node selector from the current application state.

    The node selector is created during lifespan startup and stored in
    ``app.state.node_selector``.  This dependency makes it available to
    FastAPI route handlers via ``Depends(get_node_selector)``.
    """
    return request.app.state.node_selector  # type: ignore[no-any-return]
```

---

### `inference_proxy/main.py` (MOD - config, request-response)

**Analog:** self (existing file)

**Lifespan app.state storage pattern** (main.py lines 117-133):
```python
        app.state.registry = registry

        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(...),
            limits=httpx.Limits(...),
        )
        proxy_client = ProxyClient(http_client)
        app.state.proxy_client = proxy_client
```

**Apply -- after registry creation, before yield:**
```python
        from inference_proxy.routing.connection_tracker import ConnectionTracker
        from inference_proxy.routing.node_selector import NodeSelector

        connection_tracker = ConnectionTracker()
        node_selector = NodeSelector(registry, connection_tracker)
        app.state.node_selector = node_selector
```

---

### `inference_proxy/discovery/watcher.py` (MOD - service, event-driven)

**Analog:** self (existing file)

**Current DELETE handling** (watcher.py lines 112-115):
```python
    if event_type == "DELETE":
        node_id = key.removeprefix(prefix)
        registry.remove(node_id)
        logger.info("node removed", node_id=node_id)
```

**Apply -- drain coordination (D-10, D-11):**
Instead of immediate `registry.remove()`, set node to DRAINING status. The node stays in the registry until its connection count reaches 0, at which point it is removed.

Two options per Claude's discretion:
1. Watcher calls `registry.drain(node_id)` which sets `DRAINING` via `model_copy(update={"status": NodeStatus.DRAINING})` and calls `registry.add()` to replace.
2. Watcher directly does the status transition.

Option 1 is cleaner -- keeps the watcher's concern limited to event dispatch.

**Registry drain method pattern** (following existing `add`/`remove`):
```python
def drain(self, node_id: str) -> bool:
    """Mark a node as DRAINING. Returns True if node was found."""
    with self._lock:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        self._nodes[node_id] = node.model_copy(update={"status": NodeStatus.DRAINING})
        return True
```

**model_copy pattern** -- frozen Pydantic models use `model_copy(update={...})` for immutable state transitions (per CONTEXT.md "Established Patterns"):
```python
# From inference_proxy/models/node.py -- frozen model:
class Node(BaseModel):
    model_config = ConfigDict(frozen=True)
    # ...
    status: NodeStatus = NodeStatus.UNKNOWN

# Usage:
draining_node = node.model_copy(update={"status": NodeStatus.DRAINING})
```

---

### `inference_proxy/discovery/registry.py` (MOD - service, CRUD)

**Analog:** self (existing file)

**Apply:** Add `drain(node_id: str) -> bool` method following the existing `add`/`remove` pattern with `self._lock`. See watcher section above for the method body. This keeps drain logic inside the registry (Single Responsibility -- the registry owns node state transitions).

---

### `tests/routing/test_connection_tracker.py` (NEW - test)

**Analog:** `tests/discovery/test_registry.py`

**Test structure pattern** (test_registry.py uses class-based tests):
```python
# From tests/discovery/test_registry.py (inferred from project patterns):
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node

class TestRegistryAdd:
    def test_add_stores_node(self) -> None:
        registry = NodeRegistry()
        node = Node(node_id="n1", endpoint="http://10.0.1.100:8000")
        registry.add(node)
        assert registry.get("n1") is not None
```

**Test helper pattern** (test_node_selector.py lines 14-21):
```python
def _make_node(
    node_id: str = "node-1",
    endpoint: str = "http://10.0.1.100:8000",
    status: NodeStatus = NodeStatus.HEALTHY,
) -> Node:
    """Create a minimal Node for testing."""
    return Node(node_id=node_id, endpoint=endpoint, status=status)
```

**Apply:** Test increment/decrement/get/remove operations. Test thread safety if appropriate. Test that decrement does not go below 0. Test remove cleans up counter.

---

### `tests/routing/test_node_selector.py` (NEW - test)

**Analog:** `tests/proxy/test_node_selector.py` -- exact match, replacing the old pure function tests with class-based selector tests.

**Full test file pattern** (test_node_selector.py lines 1-82):
```python
"""Unit tests for the node selection function."""

from __future__ import annotations

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node, NodeStatus
from inference_proxy.proxy.node_selector import select_node


def _make_node(
    node_id: str = "node-1",
    endpoint: str = "http://10.0.1.100:8000",
    status: NodeStatus = NodeStatus.HEALTHY,
) -> Node:
    """Create a minimal Node for testing."""
    return Node(node_id=node_id, endpoint=endpoint, status=status)


class TestSelectNode:
    """select_node returns the first healthy node or None."""

    def test_empty_registry_returns_none(self) -> None:
        registry = NodeRegistry()
        result = select_node(registry)
        assert result is None

    def test_single_healthy_node_returns_it(self) -> None:
        registry = NodeRegistry()
        node = _make_node()
        registry.add(node)
        result = select_node(registry)
        assert result is not None
        assert result.node_id == "node-1"
```

**Apply:** Same structure but test `NodeSelector` class. Required test scenarios:
- Empty registry returns None
- Single healthy node returns it
- Multiple nodes: selects least connections
- Tie-breaking: random among equal counts (test with mock or verify "in" set)
- Model filtering: exact match only (D-05)
- Model None: selects among all healthy nodes (D-09)
- Skips DRAINING nodes
- Skips UNHEALTHY/UNKNOWN nodes
- Model not found (no nodes serve model): returns None
- Model exists but all unhealthy: returns None (test distinguishes from above via separate `has_model` or similar)

---

### `tests/api/test_routes.py` (MOD - test, request-response)

**Analog:** self (existing file)

**Test fixture injection pattern** (test_routes.py lines 47-53):
```python
    def test_chat_completion_proxies_to_vllm(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
        httpx_mock: HTTPXMock,
    ) -> None:
```

**Apply:** Tests will need to inject `NodeSelector` (or override `get_node_selector` dependency) instead of relying on direct `select_node` calls. Update conftest.py to provide `node_selector` fixture. Add tests for:
- 404 when model not found
- 503 when model temporarily unavailable
- Connection tracking increments/decrements around proxy calls

**conftest.py update pattern** (conftest.py lines 54-68):
```python
@pytest.fixture
def app(
    test_settings: Settings,
    test_registry: NodeRegistry,
    proxy_client: ProxyClient,
) -> Generator[FastAPI, None, None]:
    application = create_app(settings=test_settings)
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.state.registry = test_registry
    application.state.proxy_client = proxy_client
    application.dependency_overrides[get_proxy_client] = lambda: proxy_client
    yield application
    application.dependency_overrides.clear()
    get_settings.cache_clear()
```

**Apply:** Add `connection_tracker` and `node_selector` fixtures, store `node_selector` in `app.state.node_selector`, add override for `get_node_selector`.

---

### `tests/api/test_errors.py` (MOD - test, transform)

**Analog:** self (existing file)

**Existing error test pattern** (test_errors.py lines 68-77):
```python
class TestNoNodesError:
    """no_nodes_error returns a 503 with no_nodes code."""

    def test_returns_503(self) -> None:
        status, response = no_nodes_error()

        assert status == 503
        assert response.error.code == "no_nodes"
        assert "No inference nodes available" in response.error.message
        assert response.error.type == "server_error"
```

**Apply -- add tests for two new error factories:**
```python
class TestModelNotFoundError:
    """model_not_found_error returns a 404 with model_not_found code."""

    def test_returns_404(self) -> None:
        status, response = model_not_found_error("llama-3")

        assert status == 404
        assert response.error.code == "model_not_found"
        assert response.error.type == "invalid_request_error"
        assert "llama-3" in response.error.message

class TestModelUnavailableError:
    """model_unavailable_error returns a 503 with model_unavailable code."""

    def test_returns_503(self) -> None:
        status, response = model_unavailable_error("llama-3")

        assert status == 503
        assert response.error.code == "model_unavailable"
        assert response.error.type == "server_error"
        assert "llama-3" in response.error.message
```

---

### `tests/discovery/test_watcher.py` (MOD - test, event-driven)

**Analog:** self (existing file)

**Current DELETE test pattern** (test_watcher.py lines 45-61):
```python
class TestDeleteEventRemovesNode:
    """DELETE event (type='DELETE') calls registry.remove with node_id."""

    def test_delete_event_removes_node(self) -> None:
        registry = NodeRegistry()
        prefix = "/nodes/"
        registry.add(Node(node_id="node-1", endpoint="http://10.0.1.100:8000"))

        event = {
            "kv": {"key": "/nodes/node-1"},
            "type": "DELETE",
        }

        _handle_event(event, registry, prefix)

        assert registry.get("node-1") is None
```

**Apply:** Change test to verify DELETE events set DRAINING status instead of removing. Add new test class:
```python
class TestDeleteEventDrainsNode:
    """DELETE event sets node to DRAINING status instead of removing (D-10)."""

    def test_delete_event_sets_draining(self) -> None:
        registry = NodeRegistry()
        prefix = "/nodes/"
        registry.add(Node(node_id="node-1", endpoint="http://10.0.1.100:8000",
                          status=NodeStatus.HEALTHY))

        event = {
            "kv": {"key": "/nodes/node-1"},
            "type": "DELETE",
        }

        _handle_event(event, registry, prefix)

        node = registry.get("node-1")
        assert node is not None
        assert node.status == NodeStatus.DRAINING
```

---

## Shared Patterns

### Structured Logging
**Source:** All modules use `structlog.get_logger()`
**Apply to:** All new source files (connection_tracker, node_selector)
```python
import structlog

logger = structlog.get_logger()

# Usage: keyword arguments, not positional
logger.debug("selected node", node_id=selected.node_id, connections=count)
logger.warning("no healthy nodes available", total_nodes=len(nodes))
logger.info("node draining", node_id=node_id)
```

### Dependency Injection via FastAPI Depends
**Source:** `inference_proxy/config/dependencies.py` lines 31-48
**Apply to:** `NodeSelector` injection into route handlers
```python
# In dependencies.py:
def get_node_selector(request: Request) -> NodeSelector:
    return request.app.state.node_selector  # type: ignore[no-any-return]

# In routes.py:
async def chat_completions(
    request: ChatCompletionRequest,
    node_selector: NodeSelector = Depends(get_node_selector),
    proxy: ProxyClient = Depends(get_proxy_client),
) -> JSONResponse | EventSourceResponse:
```

### Frozen Pydantic Model Updates
**Source:** `inference_proxy/models/node.py` lines 38-63
**Apply to:** Drain status transitions in registry
```python
# Node is frozen (ConfigDict(frozen=True)), so use model_copy:
draining_node = node.model_copy(update={"status": NodeStatus.DRAINING})
registry.add(draining_node)  # replace in registry
```

### Thread-Safe Mutable State
**Source:** `inference_proxy/discovery/registry.py` lines 20-50
**Apply to:** `ConnectionTracker` -- same `threading.Lock` + dict pattern
```python
class ConnectionTracker:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def increment(self, node_id: str) -> None:
        with self._lock:
            self._counts[node_id] = self._counts.get(node_id, 0) + 1

    def decrement(self, node_id: str) -> None:
        with self._lock:
            current = self._counts.get(node_id, 0)
            if current > 0:
                self._counts[node_id] = current - 1
```

### OpenAI Error Response Schema
**Source:** `inference_proxy/models/openai.py` lines 167-179 + `inference_proxy/api/errors.py`
**Apply to:** New error factories (model_not_found, model_unavailable)
```python
# Schema from models/openai.py:
class ErrorDetail(BaseModel):
    message: str
    type: str
    param: str | None = None
    code: str | int | None = None

class ErrorResponse(BaseModel):
    error: ErrorDetail

# Factory pattern from errors.py:
def model_not_found_error(model: str) -> tuple[int, ErrorResponse]:
    return 404, ErrorResponse(
        error=ErrorDetail(
            message=f"The model '{model}' does not exist",
            type="invalid_request_error",
            code="model_not_found",
        )
    )
```

### Test Helper Pattern
**Source:** `tests/proxy/test_node_selector.py` lines 14-21, `tests/api/test_routes.py` lines 24-36
**Apply to:** All new test files
```python
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

### Test Class Structure
**Source:** All test files in the project
**Apply to:** All new test files
```python
# Class-per-behavior, not class-per-method
class TestSelectNodeWithModel:
    """NodeSelector.select filters by model name."""

    def test_exact_match_returns_node(self) -> None:
        ...

    def test_no_match_returns_none(self) -> None:
        ...
```

### `from __future__ import annotations`
**Source:** Every source module in the project
**Apply to:** All new files -- this is used consistently across the entire codebase for PEP 604 union syntax in annotations.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | -- | -- | All files have strong analogs in the existing codebase |

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 31 (all Python source and test files)
**Pattern extraction date:** 2026-06-24
