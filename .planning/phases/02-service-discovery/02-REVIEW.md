---
phase: 02-service-discovery
reviewed: 2026-06-11T18:30:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - inference_proxy/discovery/serializer.py
  - inference_proxy/discovery/registry.py
  - inference_proxy/discovery/etcd_client.py
  - inference_proxy/discovery/watcher.py
  - inference_proxy/config/dependencies.py
  - inference_proxy/main.py
  - tests/discovery/test_serializer.py
  - tests/discovery/test_registry.py
  - tests/discovery/test_etcd_client.py
  - tests/discovery/test_watcher.py
  - tests/conftest.py
  - tests/test_app.py
findings:
  critical: 3
  warning: 5
  info: 2
  total: 10
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-06-11T18:30:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

The service discovery layer is well-structured with clear separation of concerns (serializer, registry, etcd client, watcher). The code demonstrates good defensive practices around bytes/str handling and malformed data. However, there are several correctness issues: the `lru_cache` on `get_settings()` is called directly in the lifespan (bypassing FastAPI DI overrides), `EtcdClient` will crash on an empty endpoints list, and exception context is silently discarded in two critical error paths making production debugging extremely difficult. Thread-safety of the registry also has a gap: `Node` objects are mutable and returned by reference, so external mutation bypasses the lock.

## Critical Issues

### CR-01: `get_settings()` called directly in lifespan bypasses dependency overrides

**File:** `inference_proxy/main.py:80`
**Issue:** The lifespan function calls `get_settings()` directly rather than receiving settings through FastAPI's dependency injection. Because `get_settings()` is decorated with `@lru_cache`, the first call caches the result permanently. The `dependency_overrides[get_settings]` set in `tests/conftest.py:42` only affects FastAPI route-level dependency resolution -- it has zero effect on this direct call. This means:

1. In tests using the `app` fixture from conftest, the lifespan creates a **real** `EtcdClient` pointing at `http://localhost:2379` (the default), not the test settings.
2. The `@lru_cache` is never cleared between tests, so the cached Settings instance persists across the entire test session. If environment variables differ between test runs or test modules, the stale cache produces incorrect behavior.

The tests in `TestLifespanRegistryIntegration` happen to work only because they independently `@patch("inference_proxy.main.EtcdClient")` at the module level, masking this bug. The `conftest.py` `app` fixture avoids the lifespan entirely (no context manager on TestClient), so the issue is latent there. But any future test that triggers the lifespan without patching `EtcdClient` will attempt a real etcd connection.

**Fix:**
```python
# Option A: Accept settings as a parameter to lifespan (requires factory pattern)
def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        configure_logging()
        etcd_client = EtcdClient(resolved_settings.etcd)
        # ... rest of lifespan
    
    application = FastAPI(
        title="QUADS LLM Inference Proxy",
        version="0.1.0",
        lifespan=lifespan,
    )
    return application

# Option B: Clear lru_cache in tests
# In conftest.py:
@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

### CR-02: `EtcdClient.__init__` crashes with `IndexError` on empty endpoints list

**File:** `inference_proxy/discovery/etcd_client.py:34`
**Issue:** `settings.endpoints[0]` is accessed without checking that the list is non-empty. The `EtcdSettings` model defines `endpoints: list[str]` with a default of `["http://localhost:2379"]`, but there is no Pydantic validator preventing an empty list. A user setting `INFERENCE_PROXY_ETCD__ENDPOINTS='[]'` (or passing `endpoints=[]` programmatically) would cause an unhandled `IndexError` during application startup, crashing the gateway with no actionable error message.

**Fix:**
```python
# In inference_proxy/config/settings.py, add validation:
from pydantic import field_validator

class EtcdSettings(BaseModel):
    endpoints: list[str] = ["http://localhost:2379"]
    node_prefix: str = "/nodes/"

    @field_validator("endpoints")
    @classmethod
    def endpoints_must_be_non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one etcd endpoint must be configured")
        return v
```

### CR-03: `EtcdClient.__init__` silently produces wrong connection parameters for scheme-less endpoints

**File:** `inference_proxy/discovery/etcd_client.py:34-39`
**Issue:** `urlparse()` does not handle scheme-less URLs correctly. If a user configures an endpoint like `"etcd.internal:2379"` (a reasonable input), `urlparse` parses it as:
- `hostname` = `None` (falls back to `"localhost"`)
- `port` = `None` (falls back to `2379`)
- `scheme` = `"etcd.internal"` (the hostname is misinterpreted as the scheme)

The constructor would then connect to `localhost:2379` with protocol `"etcd.internal"`, which would either fail cryptically or connect to the wrong server entirely. This is a correctness bug because the fallback to `"localhost"` silently connects to a different server than intended.

**Fix:**
```python
def __init__(self, settings: EtcdSettings) -> None:
    endpoint = settings.endpoints[0]
    parsed = urlparse(endpoint)
    
    # urlparse requires a scheme to parse correctly
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(
            f"Invalid etcd endpoint URL: '{endpoint}'. "
            f"Must include scheme (e.g., 'http://etcd.internal:2379')"
        )
    
    self._client = Etcd3Client(
        host=parsed.hostname,
        port=parsed.port or 2379,
        protocol=parsed.scheme,
    )
    self._prefix = settings.node_prefix
```

## Warnings

### WR-01: Exception context discarded in `_initial_load` -- production debugging blind spot

**File:** `inference_proxy/main.py:57-60`
**Issue:** The `except Exception:` block catches all exceptions but does not log the exception itself. The warning message says "etcd unavailable at startup" but the actual exception (which could be a `TypeError`, `KeyError`, or any programming error -- not just connection failures) is silently discarded. In production, operators would see "etcd unavailable" but have no way to distinguish between a network issue and a bug in the code.

**Fix:**
```python
except Exception:
    logger.warning(
        "etcd unavailable at startup, starting with empty registry",
        exc_info=True,
    )
```

### WR-02: Exception context discarded in watcher reconnection loop

**File:** `inference_proxy/discovery/watcher.py:67-71`
**Issue:** Same pattern as WR-01. The `except Exception:` block logs "etcd watch disconnected, reconnecting" but discards the actual exception. This means any bug inside the watcher (e.g., a `KeyError` in `_handle_event` that propagates up, or a `TypeError` from unexpected data) would be silently retried in a loop forever, with the log showing only "disconnected, reconnecting" every 5 seconds.

Additionally, because `_handle_event` is called inside the `try` block (line 64), any exception in event handling (not just connection errors) will trigger the reconnection logic. A malformed event that causes a `KeyError` on `event["kv"]` would disconnect and reconnect the entire watch stream instead of just skipping that event.

**Fix:**
```python
# Log exception details
except Exception:
    logger.warning(
        "etcd watch disconnected, reconnecting",
        retry_delay=retry_delay,
        exc_info=True,
    )

# And move _handle_event exception handling to be per-event:
for event in events_iter:
    if stop_event.is_set():
        break
    try:
        _handle_event(event, registry, etcd_client.prefix)
    except Exception:
        logger.warning(
            "failed to handle watch event, skipping",
            event=event,
            exc_info=True,
        )
```

### WR-03: `NodeRegistry` returns mutable Node references -- lock protection bypassed

**File:** `inference_proxy/discovery/registry.py:43-45`
**Issue:** `get()` returns a direct reference to the `Node` object stored in the internal dictionary. Since `Node` is a Pydantic v2 model without `frozen=True`, the returned object is mutable. Any caller (potentially in a different async context or thread) that modifies the returned Node mutates the registry's internal state without acquiring the lock. While current code does not mutate Nodes after creation, this is a latent thread-safety violation that will surface as soon as any consumer modifies a Node (e.g., updating `active_connections` or `status`).

`get_all()` has the same issue -- it copies the list but shares Node references.

**Fix:**
```python
# Option A: Make Node immutable
class Node(BaseModel):
    model_config = ConfigDict(frozen=True)
    # ... fields

# Option B: Return copies from registry
def get(self, node_id: str) -> Node | None:
    with self._lock:
        node = self._nodes.get(node_id)
        return node.model_copy() if node is not None else None
```

### WR-04: `_handle_event` does not guard against missing `"kv"` key

**File:** `inference_proxy/discovery/watcher.py:89`
**Issue:** `event["kv"]` is accessed without a `.get()` check or try/except. While the etcd3gw `Event` TypedDict specifies `kv` as a required field, the watcher receives raw `dict` objects. If etcd3gw ever emits a progress notification or a malformed event without a `kv` key, this line raises `KeyError`, which propagates to the outer `except Exception` block and triggers an unnecessary full reconnection (per WR-02).

**Fix:**
```python
def _handle_event(event: dict, registry: NodeRegistry, prefix: str) -> None:
    kv = event.get("kv")
    if kv is None:
        logger.debug("skipping event without kv", event_type=event.get("type"))
        return
    key = kv.get("key")
    if key is None:
        logger.warning("skipping event with missing key")
        return
    # ... rest of handler
```

### WR-05: Only first etcd endpoint is used -- `endpoints` list is misleading

**File:** `inference_proxy/discovery/etcd_client.py:34`
**Issue:** The `EtcdSettings.endpoints` field is typed as `list[str]`, implying support for multiple endpoints (common in etcd clusters for failover). However, `EtcdClient.__init__` only reads `settings.endpoints[0]` and silently ignores all subsequent endpoints. If a user configures multiple endpoints expecting failover behavior, the gateway will only connect to the first one with no indication that the others are unused.

**Fix:**
```python
# Either: document that only one endpoint is supported and change the type
class EtcdSettings(BaseModel):
    endpoint: str = "http://localhost:2379"  # singular
    node_prefix: str = "/nodes/"

# Or: log a warning when multiple endpoints are provided
def __init__(self, settings: EtcdSettings) -> None:
    if len(settings.endpoints) > 1:
        logger.warning(
            "multiple etcd endpoints configured but only the first is used",
            endpoint=settings.endpoints[0],
            ignored=settings.endpoints[1:],
        )
    # ...
```

## Info

### IN-01: `EtcdClient` return type annotations are imprecise

**File:** `inference_proxy/discovery/etcd_client.py:47-64`
**Issue:** `get_prefix()` is annotated as returning `list[tuple[bytes, dict[str, Any]]]` but the actual etcd3gw return type is `list[tuple[bytes, KeyValue]]` where `KeyValue` is a `TypedDict`. `watch_prefix()` is annotated as `tuple[Any, Any]` -- completely untyped. These loose annotations weaken static analysis and make it harder for downstream code to catch type errors.

**Fix:**
```python
from etcd3gw.types import Event, KeyValue
from collections.abc import Iterator, Callable

def get_prefix(self) -> list[tuple[bytes, KeyValue]]:
    ...

def watch_prefix(self) -> tuple[Iterator[Event], Callable[[], None]]:
    ...
```

### IN-02: Test fixture `app` sets registry without triggering lifespan -- tests validate setup, not behavior

**File:** `tests/conftest.py:39-45`
**Issue:** The `app` fixture creates a FastAPI application and manually assigns `application.state.registry = test_registry` without triggering the lifespan (no `with TestClient(app)` context manager). The `test_app_state_has_registry` test (test_app.py:48-50) then asserts the registry exists -- but it is asserting what the fixture explicitly set up, not what the application lifespan would produce. This test provides false confidence that the lifespan correctly initializes the registry. The `TestLifespanRegistryIntegration` tests correctly use `with TestClient(app)` to test the actual lifespan, so coverage exists, but the conftest-based test is misleading.

**Fix:** Add a comment to `test_app_state_has_registry` clarifying it tests DI override wiring, not lifespan behavior. Or remove it in favor of the existing `TestLifespanRegistryIntegration` tests.

---

_Reviewed: 2026-06-11T18:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
