# Phase 7: Request Metrics and Admin API - Pattern Map

**Mapped:** 2026-06-29
**Files analyzed:** 7 (1 new, 4 modified, 2 test files)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/routing/request_metrics.py` | service | request-response (counter) | `inference_proxy/routing/connection_tracker.py` | exact |
| `inference_proxy/models/admin.py` | model | request-response | itself (extend) | exact |
| `inference_proxy/api/admin.py` | controller | request-response | itself (extend) | exact |
| `inference_proxy/config/dependencies.py` | config | request-response | itself (extend) | exact |
| `inference_proxy/main.py` | config | request-response | itself (extend) | exact |
| `inference_proxy/resilience/circuit_breaker.py` | service | request-response | itself (add property) | exact |
| `inference_proxy/api/routes.py` | controller | request-response | itself (add calls) | exact |
| `tests/routing/test_request_metrics.py` | test | unit | `tests/routing/test_connection_tracker.py` | exact |
| `tests/api/test_admin.py` | test | integration | itself (update assertions) | exact |

## Pattern Assignments

### `inference_proxy/routing/request_metrics.py` (NEW - service, counter)

**Analog:** `inference_proxy/routing/connection_tracker.py`

**Imports pattern** (lines 1-13):
```python
from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger()
```

**Core pattern -- class with dict+lock** (lines 25-77):
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

    def get_all(self) -> dict[str, int]:
        """Return a copy of all tracked node connection counts."""
        with self._lock:
            return dict(self._counts)
```

Key conventions to follow:
- Module docstring with decision references
- `from __future__ import annotations` as first import
- `structlog.get_logger()` at module level
- Single `threading.Lock()` protecting all internal dicts
- `dict.get(key, 0)` pattern for default values
- `dict(self._internal)` to return copies from getters
- Debug-level structlog calls outside the lock

---

### `inference_proxy/models/admin.py` (MODIFY - model)

**Analog:** itself

**Current model** (lines 15-28):
```python
class AdminNodeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    endpoint: str
    model: str
    status: str
```

Add two fields: `active_connections: int` and `circuit_breaker_state: str`. Same frozen Pydantic pattern.

---

### `inference_proxy/api/admin.py` (MODIFY - controller)

**Analog:** itself

**Current handler** (lines 20-39):
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

**Imports pattern** (lines 9-16):
```python
from fastapi import APIRouter, Depends

from inference_proxy.config.dependencies import get_registry
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.admin import AdminNodeResponse
```

Modifications:
1. Add `Depends` injections for `NodeSelector` (to access `tracker`) and `CircuitBreakerRegistry`
2. Enrich `AdminNodeResponse` construction with `active_connections` and `circuit_breaker_state`
3. Add new `/admin/metrics` endpoint returning aggregate counters (new Pydantic response model)

---

### `inference_proxy/config/dependencies.py` (MODIFY - config)

**Analog:** itself -- follow the existing `get_*` pattern

**DI provider pattern** (lines 53-61):
```python
def get_circuit_breaker_registry(request: Request) -> CircuitBreakerRegistry:
    """Return the circuit breaker registry from the current application state."""
    return request.app.state.circuit_breaker_registry  # type: ignore[no-any-return]
```

Add `get_request_metrics()` following this exact shape: `request.app.state.request_metrics` with `# type: ignore[no-any-return]`.

---

### `inference_proxy/main.py` (MODIFY - config/lifespan)

**Analog:** itself -- follow the existing wiring pattern

**Lifespan wiring pattern** (lines 145-147):
```python
connection_tracker = ConnectionTracker()
node_selector = NodeSelector(registry, connection_tracker)
app.state.node_selector = node_selector
```

Add `RequestMetrics()` creation and `app.state.request_metrics = request_metrics` following this same pattern -- construct, then store on `app.state`.

---

### `inference_proxy/resilience/circuit_breaker.py` (MODIFY - add state property)

**Analog:** itself -- follow the `is_open` property pattern

**Existing property** (lines 72-74):
```python
@property
def is_open(self) -> bool:
    """Return ``True`` when the breaker is in the OPEN state."""
    with self._lock:
        return self._state == "open"
```

Add a `state` property following the same `@property` + `with self._lock` pattern, returning `self._state` string.

---

### `inference_proxy/api/routes.py` (MODIFY - add counter increments)

**Analog:** itself -- follow the existing `tracker.increment`/`tracker.decrement` call pattern

**Non-streaming increment pattern** (lines 185-186):
```python
tracker.increment(node.node_id)
try:
    response = await proxy.forward("POST", url, body)
```

**Streaming increment pattern** (lines 359):
```python
tracker.increment(node.node_id)
```

Counter increments go adjacent to these existing `tracker.increment` calls. Per D-03: `record_request(node_id, model)` once before the retry loop; `record_node_attempt(node_id)` on retry attempts only.

---

### `tests/routing/test_request_metrics.py` (NEW - unit test)

**Analog:** `tests/routing/test_connection_tracker.py`

**Test class structure** (lines 1-98):
```python
from __future__ import annotations

from inference_proxy.routing.connection_tracker import ConnectionTracker


class TestIncrement:
    """increment() increases the connection count for a node."""

    def test_increment_sets_count_to_one(self) -> None:
        tracker = ConnectionTracker()

        tracker.increment("node-1")

        assert tracker.get("node-1") == 1
```

Key conventions:
- `from __future__ import annotations` first
- Import the class under test directly
- Group tests by method into classes with docstring
- Descriptive method names: `test_<method>_<behavior>`
- Arrange/Act/Assert with blank line separation
- No fixtures needed -- just instantiate the class directly
- No `@pytest.mark.asyncio` needed (sync class, no async)

---

### `tests/api/test_admin.py` (MODIFY - update assertions)

**Analog:** itself

**Test that needs updating** (lines 58-76):
```python
def test_each_node_has_exactly_four_fields(
    self,
    client: TestClient,
    test_registry: NodeRegistry,
) -> None:
    """Each node in the response contains exactly node_id, endpoint, model, status."""
    test_registry.add(_make_node())

    response = client.get("/admin/nodes")
    data = response.json()

    assert len(data) == 1
    node = data[0]
    assert set(node.keys()) == {"node_id", "endpoint", "model", "status"}
    # Must NOT contain operational data
    assert "last_heartbeat" not in node
    assert "capabilities" not in node
    assert "active_connections" not in node
```

This test must change to assert 6 fields including `active_connections` and `circuit_breaker_state`. Remove the `assert "active_connections" not in node` line.

**Test fixture pattern from conftest.py** (lines 84-106):
```python
@pytest.fixture
def app(
    test_settings: Settings,
    test_registry: NodeRegistry,
    proxy_client: ProxyClient,
    node_selector: NodeSelector,
    circuit_breaker_registry: CircuitBreakerRegistry,
) -> Generator[FastAPI, None, None]:
    application = create_app(settings=test_settings)
    application.dependency_overrides[get_settings] = lambda: test_settings
    application.state.registry = test_registry
    # ... more state and overrides ...
    yield application
    application.dependency_overrides.clear()
```

New `request_metrics` fixture and `app.state.request_metrics` wiring will follow this same pattern in conftest.py.

---

## Shared Patterns

### Thread-safe dict+lock
**Source:** `inference_proxy/routing/connection_tracker.py` (entire file)
**Apply to:** `inference_proxy/routing/request_metrics.py`
```python
class ConnectionTracker:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def increment(self, node_id: str) -> None:
        with self._lock:
            self._counts[node_id] = self._counts.get(node_id, 0) + 1
```

### Dependency injection via app.state
**Source:** `inference_proxy/config/dependencies.py` (lines 53-61)
**Apply to:** New `get_request_metrics()` provider
```python
def get_circuit_breaker_registry(request: Request) -> CircuitBreakerRegistry:
    return request.app.state.circuit_breaker_registry  # type: ignore[no-any-return]
```

### Lifespan wiring
**Source:** `inference_proxy/main.py` (lines 125-147)
**Apply to:** `RequestMetrics` instantiation in lifespan
```python
connection_tracker = ConnectionTracker()
node_selector = NodeSelector(registry, connection_tracker)
app.state.node_selector = node_selector
```

### Pydantic frozen model
**Source:** `inference_proxy/models/admin.py` (lines 15-28)
**Apply to:** Extended `AdminNodeResponse`, new `AdminMetricsResponse`
```python
class AdminNodeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
```

### Test conftest DI override
**Source:** `tests/conftest.py` (lines 84-106)
**Apply to:** Adding `request_metrics` fixture and wiring into app fixture
```python
application.state.circuit_breaker_registry = circuit_breaker_registry
application.dependency_overrides[get_circuit_breaker_registry] = (
    lambda: circuit_breaker_registry
)
```

## No Analog Found

No files lack an analog. Every new/modified file has an exact match in the existing codebase.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 12 (6 source analogs, 2 test analogs, 4 context/config files)
**Pattern extraction date:** 2026-06-29
