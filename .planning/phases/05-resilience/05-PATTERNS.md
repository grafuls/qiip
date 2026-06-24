# Phase 5: Resilience - Pattern Map

**Mapped:** 2026-06-24
**Files analyzed:** 12 new/modified files
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/resilience/circuit_breaker.py` | service | event-driven | `inference_proxy/routing/connection_tracker.py` | exact |
| `inference_proxy/resilience/circuit_breaker_registry.py` | service | CRUD | `inference_proxy/discovery/registry.py` | exact |
| `inference_proxy/resilience/health_checker.py` | service | batch | `inference_proxy/discovery/watcher.py` | exact |
| `inference_proxy/resilience/shutdown.py` | middleware | request-response | `inference_proxy/api/routes.py` (middleware patterns) | role-match |
| `inference_proxy/config/settings.py` (modify) | config | N/A | self | exact |
| `inference_proxy/config/dependencies.py` (modify) | provider | N/A | self | exact |
| `inference_proxy/main.py` (modify) | config | N/A | self | exact |
| `inference_proxy/api/routes.py` (modify) | controller | request-response | self | exact |
| `tests/resilience/__init__.py` | test | N/A | `tests/routing/__init__.py` | exact |
| `tests/resilience/test_circuit_breaker.py` | test | N/A | `tests/routing/test_connection_tracker.py` | exact |
| `tests/resilience/test_health_checker.py` | test | N/A | `tests/discovery/test_watcher.py` | exact |
| `tests/resilience/test_shutdown.py` | test | N/A | `tests/test_app.py` + `tests/api/test_routes.py` | role-match |

## Pattern Assignments

### `inference_proxy/resilience/circuit_breaker.py` (service, event-driven)

**Analog:** `inference_proxy/routing/connection_tracker.py`

**Imports pattern** (lines 1-8):
```python
from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger()
```

**Core thread-safe state management pattern** (lines 25-77):
```python
class ConnectionTracker:
    """Thread-safe counter of active connections per node.

    All public methods acquire ``self._lock`` before accessing the
    internal dictionary.  ``get_all`` returns a copy so callers
    cannot mutate internal state.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def increment(self, node_id: str) -> None:
        """Increment the active connection count for *node_id*."""
        with self._lock:
            self._counts[node_id] = self._counts.get(node_id, 0) + 1
        logger.debug("connection incremented", node_id=node_id)

    def get(self, node_id: str) -> int:
        """Return the active connection count for *node_id*."""
        with self._lock:
            return self._counts.get(node_id, 0)

    def remove(self, node_id: str) -> None:
        """Remove *node_id* from the tracker entirely."""
        with self._lock:
            self._counts.pop(node_id, None)
        logger.debug("connection counter removed", node_id=node_id)
```

**Adaptation notes:**
- CircuitBreaker tracks `failure_count: int` per node (analogous to `_counts`)
- State enum: CLOSED (normal), OPEN (tripped) -- no half-open per D-08
- `record_failure(node_id)` increments failure count; trips to OPEN after threshold (D-06: 3 consecutive)
- `record_success(node_id)` resets failure count and state to CLOSED
- `is_open(node_id) -> bool` checks if circuit is tripped
- Same `threading.Lock` pattern, same `structlog` logging

---

### `inference_proxy/resilience/circuit_breaker_registry.py` (service, CRUD)

**Analog:** `inference_proxy/discovery/registry.py`

**Imports pattern** (lines 1-5):
```python
from __future__ import annotations

import threading

from inference_proxy.models.node import Node, NodeStatus
```

**Thread-safe registry pattern** (lines 20-65):
```python
class NodeRegistry:
    """Thread-safe registry of discovered vLLM nodes."""

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

**Adaptation notes:**
- `CircuitBreakerRegistry` manages `dict[str, CircuitBreaker]` per node
- `get_or_create(node_id) -> CircuitBreaker` -- lazy init under lock
- `reset(node_id)` -- called by health checker when node recovers
- `remove(node_id)` -- cleanup when node leaves registry
- Same `threading.Lock` + dict pattern as NodeRegistry and ConnectionTracker

---

### `inference_proxy/resilience/health_checker.py` (service, batch)

**Analog:** `inference_proxy/discovery/watcher.py`

**Imports pattern** (lines 1-10):
```python
from __future__ import annotations

import threading

import structlog

from inference_proxy.discovery.registry import NodeRegistry

logger = structlog.get_logger()
```

**Background thread with stop event pattern** (lines 41-82):
```python
def run_watcher(
    etcd_client: EtcdClient,
    registry: NodeRegistry,
    stop_event: threading.Event,
    retry_delay: float = 5.0,
) -> None:
    """Watch for node changes, reconnecting on failure.

    Runs in a dedicated thread.  Stops when *stop_event* is set.
    """
    while not stop_event.is_set():
        try:
            events_iter, cancel = etcd_client.watch_prefix()
            try:
                for event in events_iter:
                    if stop_event.is_set():
                        break
                    # ... handle event ...
            finally:
                cancel()
        except Exception:
            logger.warning(
                "etcd watch disconnected, reconnecting",
                retry_delay=retry_delay,
                exc_info=True,
            )
            if stop_event.wait(timeout=retry_delay):
                break
```

**Adaptation notes:**
- `run_health_checker(registry, circuit_breaker_registry, stop_event, interval, ...)` follows same function signature pattern
- Loop: `while not stop_event.is_set()` with `stop_event.wait(timeout=interval)` for periodic check (not reconnection)
- Each iteration: iterate `registry.get_all()`, probe each node's `/health` endpoint with synchronous `httpx.Client.get()` (sync HTTP from thread)
- Track consecutive failures per node; mark UNHEALTHY after 3 failures (D-03)
- Recover to HEALTHY after 1 success (D-04); reset circuit breaker on recovery
- Use `model_copy(update={"status": NodeStatus.UNHEALTHY})` via registry for status transitions -- same frozen Pydantic pattern as `NodeRegistry.drain()` (line 52-60)

**Registry status transition pattern** (`inference_proxy/discovery/registry.py` lines 47-60):
```python
def drain(self, node_id: str) -> bool:
    """Mark a node as DRAINING."""
    with self._lock:
        node = self._nodes.get(node_id)
        if node is None:
            return False
        self._nodes[node_id] = node.model_copy(
            update={"status": NodeStatus.DRAINING}
        )
        return True
```

---

### `inference_proxy/resilience/shutdown.py` (middleware, request-response)

**Analog:** `inference_proxy/main.py` (app.state pattern) + `inference_proxy/api/routes.py` (request handling)

**App state flag pattern** (`inference_proxy/main.py` lines 119-123):
```python
app.state.registry = registry

connection_tracker = ConnectionTracker()
node_selector = NodeSelector(registry, connection_tracker)
app.state.node_selector = node_selector
```

**Adaptation notes:**
- Middleware function or class that checks `request.app.state.shutting_down`
- Return 503 JSONResponse if flag is set (same pattern as `no_nodes_error()` in errors.py)
- Use `@app.middleware("http")` or Starlette `BaseHTTPMiddleware`
- The lifespan sets `app.state.shutting_down = False` on startup, `True` on shutdown signal

**Error response pattern** (`inference_proxy/api/errors.py` lines 116-128):
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

---

### `inference_proxy/config/settings.py` (modify -- add settings)

**Analog:** self (`inference_proxy/config/settings.py`)

**Sub-model pattern** (lines 34-40):
```python
class RoutingSettings(BaseModel):
    """Request routing and load balancing configuration."""

    strategy: str = "least_connections"
    health_check_interval: int = 30
    max_retries: int = 3
    timeout: int = 30
```

**Root settings integration** (lines 66-87):
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INFERENCE_PROXY_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    gateway: GatewaySettings = GatewaySettings()
    etcd: EtcdSettings = EtcdSettings()
    routing: RoutingSettings = RoutingSettings()
    proxy: ProxySettings = ProxySettings()
    logging: LoggingSettings = LoggingSettings()
```

**Adaptation notes:**
- Add `graceful_shutdown_timeout: int = 30` to `GatewaySettings` (D-10)
- Add `ResilienceSettings(BaseModel)` sub-model with:
  - `health_check_interval: int = 30` (or reuse from RoutingSettings -- CONTEXT says RoutingSettings already has this)
  - `circuit_breaker_threshold: int = 3` (D-06)
  - `health_check_failure_threshold: int = 3` (D-03)
- Add `resilience: ResilienceSettings = ResilienceSettings()` to root Settings
- Note: `RoutingSettings` already has `health_check_interval=30` and `max_retries=3` -- decide whether to reuse or move

---

### `inference_proxy/config/dependencies.py` (modify -- add DI provider)

**Analog:** self (`inference_proxy/config/dependencies.py`)

**DI provider pattern** (lines 42-59):
```python
def get_proxy_client(request: Request) -> ProxyClient:
    """Return the proxy client from the current application state."""
    return request.app.state.proxy_client  # type: ignore[no-any-return]


def get_node_selector(request: Request) -> NodeSelector:
    """Return the node selector from the current application state."""
    return request.app.state.node_selector  # type: ignore[no-any-return]
```

**Adaptation notes:**
- Add `get_circuit_breaker_registry(request: Request) -> CircuitBreakerRegistry` following exact same pattern
- Registry stored in `app.state.circuit_breaker_registry` during lifespan

---

### `inference_proxy/main.py` (modify -- lifespan integration)

**Analog:** self (`inference_proxy/main.py`)

**Lifespan startup pattern** (lines 85-141):
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ... setup ...
    stop_event = threading.Event()
    watch_thread = threading.Thread(
        target=run_watcher,
        args=(etcd_client, registry, stop_event),
        daemon=True,
    )
    watch_thread.start()

    app.state.registry = registry
    # ... more setup ...

    yield

    await http_client.aclose()
    stop_event.set()
    watch_thread.join(timeout=10)
```

**Adaptation notes:**
- Create `CircuitBreakerRegistry()` and store in `app.state.circuit_breaker_registry`
- Start health checker thread: `threading.Thread(target=run_health_checker, args=(..., stop_event), daemon=True)`
- Reuse the same `stop_event` as watcher -- D-11 says health check thread stops immediately on shutdown
- Set `app.state.shutting_down = False` on startup
- On shutdown: set `app.state.shutting_down = True`, then wait for drain timeout before stopping
- Add shutdown middleware to the FastAPI app (after `application = FastAPI(...)`)

---

### `inference_proxy/api/routes.py` (modify -- retry logic + circuit breaker)

**Analog:** self (`inference_proxy/api/routes.py`)

**Non-streaming proxy pattern with error handling** (lines 104-134):
```python
async def _proxy_non_streaming(
    endpoint_path: str,
    body: dict[str, Any],
    node_selector: NodeSelector,
    proxy: ProxyClient,
) -> JSONResponse:
    model = body.get("model")
    node = node_selector.select(model=model)
    if node is None:
        status, error_resp = _select_error(model, node_selector)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)

    url = f"http://{node.endpoint}{endpoint_path}"
    tracker = node_selector.tracker

    tracker.increment(node.node_id)
    try:
        response = await proxy.forward("POST", url, body)
        # ... parse response ...
        return JSONResponse(content=content, status_code=response.status_code)
    except Exception as exc:
        status, error_resp = map_proxy_error(exc)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)
    finally:
        tracker.decrement(node.node_id)
        _maybe_remove_drained(node, node_selector)
        _scan_drained_nodes(node_selector)
```

**Streaming proxy pattern** (lines 215-262):
```python
async def _stream_completion(
    endpoint_path: str,
    body: dict[str, Any],
    node_selector: NodeSelector,
    proxy: ProxyClient,
) -> JSONResponse | EventSourceResponse:
    model = body.get("model")
    node = node_selector.select(model=model)
    if node is None:
        status, error_resp = _select_error(model, node_selector)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)

    url = f"http://{node.endpoint}{endpoint_path}"
    tracker = node_selector.tracker

    tracker.increment(node.node_id)

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            async with aconnect_sse(
                proxy.client, "POST", url, json=body
            ) as event_source:
                event_source.response.raise_for_status()
                async for sse in event_source.aiter_sse():
                    # ... yield events ...
        except Exception as exc:
            logger.error("streaming proxy error", error=str(exc), url=url)
            # ... error SSE ...
        finally:
            tracker.decrement(node.node_id)
            _maybe_remove_drained(node, node_selector)
            _scan_drained_nodes(node_selector)
```

**Route handler DI pattern** (lines 137-158):
```python
@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    node_selector: NodeSelector = Depends(get_node_selector),
    proxy: ProxyClient = Depends(get_proxy_client),
) -> JSONResponse | EventSourceResponse:
```

**Adaptation notes:**
- Add `circuit_breaker_registry` as DI dependency via `Depends(get_circuit_breaker_registry)`
- On proxy success: `circuit_breaker_registry.get_or_create(node.node_id).record_success()`
- On proxy failure (exception or 5xx): `circuit_breaker_registry.get_or_create(node.node_id).record_failure()` -- if tripped, mark node UNHEALTHY in registry (D-07)
- Retry logic: wrap proxy call in retry loop (up to `max_retries`), exclude failed node from next `select()` call
- For streaming: only retry before first byte (pre-connection errors like ConnectError, TimeoutException on connect)
- Pass `exclude_node_ids: set[str]` to `node_selector.select()` for retry exclusion

---

### `tests/resilience/test_circuit_breaker.py` (test)

**Analog:** `tests/routing/test_connection_tracker.py`

**Test class organization pattern** (lines 1-97):
```python
"""Unit tests for the thread-safe ConnectionTracker."""

from __future__ import annotations

from inference_proxy.routing.connection_tracker import ConnectionTracker


class TestIncrement:
    """increment() increases the connection count for a node."""

    def test_increment_sets_count_to_one(self) -> None:
        tracker = ConnectionTracker()

        tracker.increment("node-1")

        assert tracker.get("node-1") == 1


class TestDecrement:
    """decrement() decreases the connection count for a node."""

    def test_decrement_after_increment_returns_zero(self) -> None:
        tracker = ConnectionTracker()
        tracker.increment("node-1")

        tracker.decrement("node-1")

        assert tracker.get("node-1") == 0

    def test_decrement_does_not_go_below_zero(self) -> None:
        tracker = ConnectionTracker()

        tracker.decrement("nonexistent")

        assert tracker.get("nonexistent") == 0
```

**Adaptation notes:**
- One test class per public method: `TestRecordFailure`, `TestRecordSuccess`, `TestIsOpen`, `TestReset`
- Direct instantiation in each test (no fixtures for simple unit tests)
- Test trip threshold: 3 failures trips the breaker
- Test reset on success
- Test `is_open` before and after tripping

---

### `tests/resilience/test_health_checker.py` (test)

**Analog:** `tests/discovery/test_watcher.py`

**Thread-based test pattern** (lines 119-151):
```python
class TestWatchPrefixExceptionReconnects:
    """When watch_prefix raises an exception, watcher reconnects after delay."""

    def test_watch_prefix_exception_reconnects(self) -> None:
        mock_client = MagicMock(spec=EtcdClient)
        mock_client.prefix = "/nodes/"

        call_count = 0

        def watch_side_effect() -> tuple:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("etcd unavailable")
            return iter([]), MagicMock()

        mock_client.watch_prefix.side_effect = watch_side_effect

        registry = NodeRegistry()
        stop_event = threading.Event()

        def stop_after_reconnect() -> None:
            while call_count < 2:
                pass
            stop_event.set()

        stopper = threading.Thread(target=stop_after_reconnect)
        stopper.start()

        run_watcher(mock_client, registry, stop_event, retry_delay=0.01)

        stopper.join(timeout=2)
        assert mock_client.watch_prefix.call_count >= 2
```

**Stop event test pattern** (lines 154-169):
```python
class TestStopEventTerminatesLoop:
    """When stop_event is set, watcher exits the reconnection loop."""

    def test_stop_event_terminates_loop(self) -> None:
        mock_client = MagicMock(spec=EtcdClient)
        mock_client.prefix = "/nodes/"

        stop_event = threading.Event()
        stop_event.set()  # Pre-set: watcher should exit immediately

        registry = NodeRegistry()

        run_watcher(mock_client, registry, stop_event, retry_delay=0.01)

        mock_client.watch_prefix.assert_not_called()
```

**Adaptation notes:**
- Use `MagicMock` for HTTP client to simulate health check responses
- Test: node marked UNHEALTHY after 3 consecutive failures
- Test: node recovers to HEALTHY after 1 success
- Test: stop_event pre-set exits immediately (same pattern as watcher test)
- Test: exception during health check does not crash the thread
- Use `retry_delay=0.01` equivalent (`interval=0.01`) for fast tests

---

### `tests/resilience/test_shutdown.py` (test)

**Analog:** `tests/test_app.py` + `tests/api/test_routes.py`

**App integration test pattern** (`tests/test_app.py` lines 14-37):
```python
def test_health_endpoint(client: TestClient) -> None:
    """GET /health returns 200 with status and nodes_registered count."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["nodes_registered"] == 0
```

**Fixture-based DI override pattern** (`tests/conftest.py` lines 76-98):
```python
@pytest.fixture
def app(
    test_settings: Settings,
    test_registry: NodeRegistry,
    proxy_client: ProxyClient,
    node_selector: NodeSelector,
) -> Generator[FastAPI, None, None]:
    application = create_app(settings=test_settings)
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.state.registry = test_registry
    application.state.proxy_client = proxy_client
    application.state.node_selector = node_selector
    application.dependency_overrides[get_proxy_client] = lambda: proxy_client
    application.dependency_overrides[get_node_selector] = lambda: node_selector
    yield application
    application.dependency_overrides.clear()
    get_settings.cache_clear()
```

**Adaptation notes:**
- Test: requests return 503 when `app.state.shutting_down = True`
- Test: requests pass through normally when `app.state.shutting_down = False`
- Test: in-flight requests complete during shutdown
- Use existing `client` and `app` fixtures from conftest.py
- Set `app.state.shutting_down = True` directly in tests

---

## Shared Patterns

### Thread-Safe State Management
**Source:** `inference_proxy/routing/connection_tracker.py` (lines 25-77)
**Apply to:** `circuit_breaker.py`, `circuit_breaker_registry.py`
```python
class ThreadSafeContainer:
    def __init__(self) -> None:
        self._data: dict[str, SomeType] = {}
        self._lock = threading.Lock()

    def mutate(self, key: str) -> None:
        with self._lock:
            # ... modify self._data ...
        logger.debug("operation completed", key=key)

    def read(self, key: str) -> SomeType | None:
        with self._lock:
            return self._data.get(key)
```

### Background Thread Pattern
**Source:** `inference_proxy/discovery/watcher.py` (lines 41-82)
**Apply to:** `health_checker.py`
```python
def run_background_task(
    dependencies: ...,
    stop_event: threading.Event,
    interval: float = 30.0,
) -> None:
    """Runs in a dedicated thread. Stops when stop_event is set."""
    while not stop_event.is_set():
        try:
            # ... do periodic work ...
            pass
        except Exception:
            logger.warning("task failed", exc_info=True)
        # Wait for interval or stop signal
        if stop_event.wait(timeout=interval):
            break
```

### Lifespan Integration
**Source:** `inference_proxy/main.py` (lines 85-145)
**Apply to:** `main.py` modifications
```python
stop_event = threading.Event()
thread = threading.Thread(
    target=run_background_task,
    args=(dependencies, stop_event),
    daemon=True,
)
thread.start()
app.state.some_resource = resource

yield

stop_event.set()
thread.join(timeout=10)
```

### DI Provider Pattern
**Source:** `inference_proxy/config/dependencies.py` (lines 42-59)
**Apply to:** `dependencies.py` modifications
```python
def get_resource(request: Request) -> ResourceType:
    """Return the resource from the current application state."""
    return request.app.state.resource  # type: ignore[no-any-return]
```

### Frozen Pydantic Model Status Transition
**Source:** `inference_proxy/discovery/registry.py` (lines 47-60)
**Apply to:** `health_checker.py` when marking nodes HEALTHY/UNHEALTHY
```python
# Nodes are frozen -- use model_copy for status changes
self._nodes[node_id] = node.model_copy(
    update={"status": NodeStatus.UNHEALTHY}
)
```

### Test Organization
**Source:** `tests/routing/test_connection_tracker.py` (entire file)
**Apply to:** All new test files
- One test class per public method or behavior group
- Class docstring describes the behavior being tested
- Method names use `test_<specific_scenario>` format
- Direct instantiation for unit tests; fixtures for integration tests
- `from __future__ import annotations` at top

### conftest.py Extension Pattern
**Source:** `tests/conftest.py` (lines 30-98)
**Apply to:** conftest.py modifications for circuit breaker fixtures
```python
@pytest.fixture
def circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Return a fresh CircuitBreakerRegistry for testing."""
    return CircuitBreakerRegistry()
```
Then wire into `app` fixture with `application.state.circuit_breaker_registry = circuit_breaker_registry` and `application.dependency_overrides[get_circuit_breaker_registry] = lambda: circuit_breaker_registry`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | -- | -- | All files have strong analogs in the existing codebase |

Every new file maps directly to an existing pattern. The resilience module mirrors the `routing/` and `discovery/` module patterns exactly.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 12 source files, 10 test files
**Pattern extraction date:** 2026-06-24
