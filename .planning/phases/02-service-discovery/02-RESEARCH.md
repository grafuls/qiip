# Phase 2: Service Discovery - Research

**Researched:** 2026-06-11
**Domain:** etcd-based service discovery with watch-based live updates
**Confidence:** HIGH

## Summary

Phase 2 implements the service discovery layer that enables the gateway to discover vLLM nodes registered in etcd and track real-time additions/removals via watch. The core library is etcd3gw (v2.7.0, released 2026-06-09), which communicates with etcd via its HTTP/JSON gateway -- avoiding grpcio C extension build issues. etcd3gw is synchronous, so integration with FastAPI's async runtime requires two patterns: `asyncio.to_thread()` for short-lived operations (get/put) and a dedicated `threading.Thread` for the long-lived watch stream.

The phase delivers four modules: an etcd client wrapper (`etcd_client.py`), a node serializer (`serializer.py`), a thread-safe node registry (`registry.py`), and watcher lifecycle management integrated into FastAPI's lifespan. The watch mechanism uses HTTP streaming internally (not long-polling) -- the watcher spawns its own background thread via `futurist.ThreadPoolExecutor` to consume chunked JSON responses. A critical design consideration is that etcd3gw's watcher has **no built-in reconnection logic** -- when the stream breaks, it silently terminates. The implementation must wrap watch in a reconnection loop.

**Primary recommendation:** Use `etcd3gw.Etcd3Client.watch_prefix()` in a dedicated `threading.Thread` with a reconnection loop, a `threading.Event` for shutdown signaling, and `threading.Lock` to protect the shared node dictionary. Mock etcd3gw at the client wrapper boundary for unit tests.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Nodes stored under configurable prefix (default `/nodes/`) with node ID as key suffix: `/nodes/{node-id}`. JSON value contains endpoint, model, capabilities, status per PLAN.md etcd data schema.
- **D-02:** Node ID is derived from the etcd key path (last segment after prefix), not stored redundantly in the JSON value.
- **D-03:** etcd3gw watch runs in a dedicated `threading.Thread` started during FastAPI lifespan startup. Watch is long-polling, so thread-per-watcher is natural.
- **D-04:** Short-lived etcd operations (get, put, lease) wrapped in `asyncio.to_thread()` for non-blocking use in FastAPI handlers and background tasks.
- **D-05:** Initial node list fetch runs synchronously at startup (blocking is acceptable during lifespan init).
- **D-06:** `NodeRegistry` class in `inference_proxy/discovery/registry.py` holds discovered nodes in a `dict[str, Node]` protected by `threading.Lock`.
- **D-07:** Registry is a singleton created during FastAPI lifespan, stored in `app.state`, and exposed via a FastAPI dependency (`get_registry()`).
- **D-08:** Registry provides thread-safe methods: `add(node)`, `remove(node_id)`, `get_all() -> list[Node]`, `get(node_id) -> Node | None`.
- **D-09:** On startup: fetch all nodes from etcd under the configured prefix, populate registry, then start watch thread. If etcd is unavailable, start with empty registry and log warning -- gateway remains responsive but routing will fail until nodes appear.
- **D-10:** On shutdown (via lifespan exit): stop the watch thread cleanly. Use a `threading.Event` to signal the watcher to stop.
- **D-11:** Separate serializer module at `inference_proxy/discovery/serializer.py` per D-15 from Phase 1. Functions: `node_from_etcd(key: str, value: bytes) -> Node` and `node_to_etcd(node: Node) -> tuple[str, bytes]`.
- **D-12:** Serializer handles missing/malformed JSON gracefully -- logs warning and skips the node rather than crashing the gateway.
- **D-13:** Thin wrapper around etcd3gw client at `inference_proxy/discovery/etcd_client.py` that encapsulates connection configuration and provides typed methods for node operations.
- **D-14:** etcd client created from `EtcdSettings` (endpoints, node_prefix) -- no additional config needed beyond what Phase 1 already defined.

### Claude's Discretion
- Internal threading and synchronization details
- etcd3gw API usage patterns and error handling specifics
- Test fixture design for mocking etcd operations
- Watch event parsing and dispatch logic

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DISC-01 | Gateway discovers vLLM nodes registered in etcd under a configurable key prefix | etcd3gw `get_prefix()` returns all key-value pairs under a prefix. `EtcdSettings.node_prefix` already exists in config. Serializer converts etcd responses to `Node` objects. |
| DISC-02 | Gateway watches etcd for real-time node additions and removals without restart | etcd3gw `watch_prefix()` returns a blocking events iterator + cancel callable. Events contain `type` field (absent=PUT, "DELETE"=delete) and `kv` with decoded key/value. Runs in background thread with reconnection loop. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| etcd communication | API / Backend | -- | etcd3gw client talks to etcd HTTP gateway; purely server-side |
| Node registry (in-memory) | API / Backend | -- | Thread-safe dict holding discovered nodes; lives in FastAPI app.state |
| Watch lifecycle | API / Backend | -- | Background thread started/stopped via FastAPI lifespan |
| Node serialization | API / Backend | -- | JSON parsing of etcd values into Pydantic Node models |
| Configuration | API / Backend | -- | EtcdSettings already defined in config layer |

## Standard Stack

### Core (Phase 2 specific)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| etcd3gw | >=2.5.0 (latest: 2.7.0) | etcd client via HTTP gateway | OpenStack-maintained, no grpcio dependency, provides get_prefix/watch_prefix/lease. Latest 2.7.0 released 2026-06-09. [VERIFIED: PyPI registry -- `pip index versions etcd3gw` shows 2.7.0] |

### Already Installed (from Phase 1)
| Library | Version | Purpose | Relevant to Phase 2 |
|---------|---------|---------|---------------------|
| FastAPI | >=0.135 | HTTP framework | Lifespan context manager for watch thread lifecycle |
| Pydantic | >=2.10 | Data validation | Node model already defined |
| pydantic-settings | >=2.14 | Configuration | EtcdSettings already defined |
| structlog | >=26.1.0 | Structured logging | Log etcd events, errors, reconnections |
| pytest | >=8.0 | Testing | Unit tests for registry, serializer, watcher |
| pytest-asyncio | >=1.4 | Async test support | Testing async dependency injection |

### Transitive Dependencies (via etcd3gw)
| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| requests | >=2.20.0 | HTTP client | etcd3gw uses requests for HTTP gateway communication |
| futurist | >=0.16.0 | Thread pool executor | etcd3gw's watcher uses futurist.ThreadPoolExecutor internally |
| pbr | >=2.0 | Build tool | OpenStack packaging requirement |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| etcd3gw | aetcd | Async native, but alpha quality (1.0.0a4), grpcio dep, tiny community |
| etcd3gw | etcetra | Pure asyncio gRPC, but 9 GitHub stars, uncertain maintenance |
| threading.Lock for registry | asyncio.Lock | asyncio.Lock only works within the event loop; watch thread is OS thread, so threading.Lock is required |
| threading.Thread for watcher | asyncio.to_thread wrapping watch | watch_prefix blocks indefinitely; asyncio.to_thread is designed for short-lived calls, not long-lived streams |

**Installation:**
```bash
uv add etcd3gw
```

**Version verification:**
```
$ pip index versions etcd3gw
etcd3gw (2.7.0)
Available versions: 2.7.0, 2.6.0, 2.5.0, ...
```

The CLAUDE.md specifies `>=2.5.0`. The latest is 2.7.0 (released 2026-06-09). The `>=2.5.0` floor is correct -- no breaking changes between 2.5.0 and 2.7.0. [CITED: https://pypi.org/project/etcd3gw/]

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| etcd3gw | PyPI | ~8 yrs (since 0.0.1) | OpenStack ecosystem | opendev.org/openstack/etcd3gw | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck returned [OK] for etcd3gw. Verified via `slopcheck install etcd3gw`.*

## Architecture Patterns

### System Architecture Diagram

```
                    FastAPI Application
                    ┌─────────────────────────────────────────────┐
                    │                                             │
  HTTP Request ───> │  async handler                              │
                    │    │                                        │
                    │    ├─ Depends(get_registry)                 │
                    │    │    │                                   │
                    │    │    ▼                                   │
                    │    │  NodeRegistry ◄────────────┐           │
                    │    │  (dict + Lock)             │           │
                    │    │    │                       │           │
                    │    │    ▼                       │ add/remove│
                    │    │  get_all() / get()         │           │
                    │    │                            │           │
                    │    │                   ┌────────┴────────┐  │
                    │    │                   │  Watch Thread   │  │
                    │    │                   │  (threading)    │  │
                    │    │                   │                 │  │
                    │    │                   │  watch_prefix() │  │
                    │    │                   │  ──► events ──► │  │
                    │    │                   │  parse + update │  │
                    │    │                   │  registry       │  │
                    │    │                   │                 │  │
                    │    │                   │  reconnect on   │  │
                    │    │                   │  failure        │  │
                    │    │                   └─────────────────┘  │
                    │                                             │
                    │  lifespan()                                 │
                    │    startup: fetch_all ──► populate registry │
                    │             start watch thread              │
                    │    shutdown: stop_event.set()               │
                    │              thread.join()                  │
                    └──────────────────┬──────────────────────────┘
                                       │
                           EtcdClient wrapper
                           (asyncio.to_thread for short ops)
                                       │
                                       ▼
                              ┌─────────────────┐
                              │   etcd cluster   │
                              │  /nodes/{id}     │
                              │   JSON values    │
                              └─────────────────┘
```

### Recommended Project Structure

```
inference_proxy/
├── discovery/
│   ├── __init__.py          # Empty (stub from Phase 1)
│   ├── etcd_client.py       # D-13: Thin wrapper around etcd3gw
│   ├── registry.py          # D-06: Thread-safe NodeRegistry
│   ├── serializer.py        # D-11: node_from_etcd / node_to_etcd
│   └── watcher.py           # Watch thread with reconnection loop
├── config/
│   ├── dependencies.py      # Add get_registry() dependency
│   └── settings.py          # EtcdSettings already exists
└── main.py                  # Extend lifespan for registry + watcher

tests/
├── discovery/
│   ├── __init__.py
│   ├── test_etcd_client.py  # Mock etcd3gw.Etcd3Client
│   ├── test_registry.py     # Thread-safe registry operations
│   ├── test_serializer.py   # JSON parsing edge cases
│   └── test_watcher.py      # Watch event dispatch, reconnection
└── conftest.py              # Add registry fixtures
```

### Pattern 1: etcd Client Wrapper (Dependency Inversion)

**What:** Thin wrapper that isolates etcd3gw from the rest of the codebase.
**When to use:** All etcd operations go through this wrapper. No other module imports `etcd3gw` directly.
**Why:** Follows Dependency Inversion Principle (CLAUDE.md SOLID requirement). Makes testing possible without etcd. Encapsulates connection parsing (EtcdSettings has `endpoints: list[str]`, but etcd3gw's `Etcd3Client` takes `host: str, port: int, protocol: str`).

```python
# Source: etcd3gw official docs (https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.client.html)
# [CITED: https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.client.html]

from urllib.parse import urlparse

from etcd3gw.client import Etcd3Client

from inference_proxy.config.settings import EtcdSettings


class EtcdClient:
    """Thin wrapper around etcd3gw providing typed node operations."""

    def __init__(self, settings: EtcdSettings) -> None:
        parsed = urlparse(settings.endpoints[0])
        self._client = Etcd3Client(
            host=parsed.hostname or "localhost",
            port=parsed.port or 2379,
            protocol=parsed.scheme or "http",
        )
        self._prefix = settings.node_prefix

    def get_prefix(self) -> list[tuple[bytes, dict]]:
        """Get all nodes under the configured prefix."""
        return self._client.get_prefix(self._prefix)

    def watch_prefix(self) -> tuple:
        """Watch for node changes under the configured prefix.

        Returns (events_iterator, cancel_fn).
        The iterator blocks on a queue.Queue internally.
        """
        return self._client.watch_prefix(self._prefix)
```

### Pattern 2: Thread-Safe Node Registry

**What:** In-memory dict protected by `threading.Lock` with a focused interface.
**When to use:** All node lookups from async handlers and all mutations from the watch thread.
**Why:** The watch thread is an OS thread, not a coroutine. `asyncio.Lock` cannot protect against OS thread access. `threading.Lock` is correct here. Keep the lock scope minimal -- copy-on-read for `get_all()`.

```python
# [ASSUMED] - standard threading.Lock pattern for Python registries

import threading

from inference_proxy.models.node import Node


class NodeRegistry:
    """Thread-safe registry of discovered vLLM nodes."""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._lock = threading.Lock()

    def add(self, node: Node) -> None:
        with self._lock:
            self._nodes[node.node_id] = node

    def remove(self, node_id: str) -> None:
        with self._lock:
            self._nodes.pop(node_id, None)

    def get(self, node_id: str) -> Node | None:
        with self._lock:
            return self._nodes.get(node_id)

    def get_all(self) -> list[Node]:
        with self._lock:
            return list(self._nodes.values())
```

### Pattern 3: Watch Thread with Reconnection Loop

**What:** Background thread that runs `watch_prefix()` in a loop, reconnecting on failure.
**When to use:** Started during FastAPI lifespan startup, stopped on shutdown.
**Why:** etcd3gw's watcher has NO built-in reconnection. When the HTTP stream breaks (network error, etcd restart), the events iterator silently terminates. Without a reconnection loop, the gateway would stop receiving node updates permanently after the first disconnection.

```python
# [ASSUMED] - reconnection pattern based on etcd3gw watcher internals

import threading
import time

import structlog

logger = structlog.get_logger()


def run_watcher(
    etcd_client: "EtcdClient",
    registry: "NodeRegistry",
    stop_event: threading.Event,
    retry_delay: float = 5.0,
) -> None:
    """Watch for node changes, reconnecting on failure.

    Runs in a dedicated thread. Stops when stop_event is set.
    """
    while not stop_event.is_set():
        try:
            events_iter, cancel = etcd_client.watch_prefix()
            try:
                for event in events_iter:
                    if stop_event.is_set():
                        break
                    _handle_event(event, registry, etcd_client.prefix)
            finally:
                cancel()
        except Exception:
            logger.warning("etcd watch disconnected, reconnecting",
                           retry_delay=retry_delay)
            if not stop_event.wait(timeout=retry_delay):
                continue  # retry
```

### Pattern 4: Serializer with Graceful Error Handling

**What:** Pure functions converting between etcd key/value pairs and Node domain objects.
**When to use:** On every node fetched from etcd (initial load and watch events).
**Why:** Separates serialization from the domain model (SRP from CLAUDE.md SOLID). Malformed JSON in etcd should never crash the gateway.

```python
# [ASSUMED] - based on PLAN.md etcd data schema and Node model

import json

import structlog

from inference_proxy.models.node import Node

logger = structlog.get_logger()


def node_from_etcd(key: str, value: bytes, prefix: str) -> Node | None:
    """Parse an etcd key-value pair into a Node.

    Args:
        key: The etcd key (e.g., "/nodes/node-abc").
        value: The raw JSON bytes from etcd.
        prefix: The configured node prefix (e.g., "/nodes/").

    Returns:
        A Node instance, or None if parsing fails.
    """
    try:
        node_id = key.removeprefix(prefix)
        data = json.loads(value)
        return Node(node_id=node_id, **data)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("skipping malformed node", key=key, error=str(exc))
        return None
```

### Pattern 5: Lifespan Integration

**What:** Extend the existing FastAPI lifespan to initialize registry and manage watch thread.
**When to use:** Application startup/shutdown.
**Why:** FastAPI lifespan is the correct place for resource lifecycle. Everything before `yield` runs at startup, everything after runs at shutdown.

```python
# Source: FastAPI lifespan docs
# [CITED: https://fastapi.tiangolo.com/advanced/events/]

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()

    settings = get_settings()
    etcd_client = EtcdClient(settings.etcd)
    registry = NodeRegistry()

    # D-05: Sync initial fetch is acceptable during startup
    _initial_load(etcd_client, registry)

    # D-03: Start watch thread
    stop_event = threading.Event()
    watch_thread = threading.Thread(
        target=run_watcher,
        args=(etcd_client, registry, stop_event),
        daemon=True,
    )
    watch_thread.start()

    # Store in app.state for dependency injection
    app.state.registry = registry

    yield

    # D-10: Graceful shutdown
    stop_event.set()
    watch_thread.join(timeout=10)
```

### Pattern 6: etcd Event Type Dispatch

**What:** Parse the event `type` field to determine PUT vs DELETE.
**When to use:** Inside the watch event handler.
**Why:** etcd3gw's `Event` TypedDict has `type` as an optional field. For PUT events, `type` is absent (proto3 JSON omits the default enum value of 0). For DELETE events, `type` is `"DELETE"`. The `kv.value` field is absent on DELETE events.

```python
# Source: etcd3gw types.py
# [CITED: https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/types.py]

def _handle_event(event: dict, registry: NodeRegistry, prefix: str) -> None:
    """Dispatch a watch event to the appropriate registry operation."""
    kv = event["kv"]
    key = kv["key"]  # already decoded by etcd3gw

    if isinstance(key, bytes):
        key = key.decode("utf-8")

    event_type = event.get("type", "PUT")  # absent = PUT

    if event_type == "DELETE":
        node_id = key.removeprefix(prefix)
        registry.remove(node_id)
    else:
        value = kv.get("value", b"")
        if isinstance(value, bytes):
            node = node_from_etcd(key, value, prefix)
        else:
            node = node_from_etcd(key, value.encode("utf-8"), prefix)
        if node is not None:
            registry.add(node)
```

### Anti-Patterns to Avoid

- **Using `asyncio.Lock` for registry protection:** The watch thread is an OS thread, not a coroutine. `asyncio.Lock` only works within the event loop and will not protect against concurrent OS thread access. Use `threading.Lock`. [CITED: https://docs.python.org/3/library/asyncio-sync.html]

- **Importing etcd3gw directly in multiple modules:** Creates tight coupling. Only `etcd_client.py` should import `etcd3gw`. All other modules depend on the wrapper abstraction. This is Dependency Inversion (CLAUDE.md SOLID requirement).

- **Blocking the event loop with sync etcd calls:** `etcd3gw.Etcd3Client.get_prefix()` is synchronous. Calling it directly in an async handler blocks the entire event loop. Use `asyncio.to_thread()` for any etcd calls from async context (except during lifespan startup where blocking is acceptable per D-05).

- **Trusting etcd3gw's watcher to stay connected:** The watcher has zero reconnection logic. If the HTTP stream breaks, the events iterator simply stops yielding. Without a reconnection loop, the gateway silently stops tracking node changes. Always wrap watch in a reconnection loop.

- **Holding the lock during I/O:** Never call etcd operations while holding the registry lock. Acquire the lock, do the dict operation, release the lock. Keep critical sections minimal.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| etcd HTTP gateway communication | Custom HTTP+base64 encoding | etcd3gw | Handles base64 key/value encoding, watch stream parsing, lease management. The HTTP gateway protocol has subtle encoding rules (latin-1 vs utf-8 for base64). |
| Range end calculation for prefix queries | Manual byte manipulation | etcd3gw's `get_prefix()` / `watch_prefix()` | `_increment_last_byte()` is a well-tested utility. Hand-rolling it risks off-by-one errors on multi-byte characters. |
| Thread pool for watcher | Custom thread management | etcd3gw internal (futurist.ThreadPoolExecutor) | The watcher already spawns its own background thread. The outer reconnection loop just needs a simple `threading.Thread`. |

**Key insight:** etcd3gw handles all the low-level HTTP gateway protocol details (base64 encoding/decoding, chunked streaming, event parsing). Our code only needs to handle: (1) wrapping the client for testability, (2) converting events to domain objects, (3) reconnection logic, and (4) thread-safe registry access.

## Common Pitfalls

### Pitfall 1: Silent Watch Disconnection
**What goes wrong:** The etcd watch stream breaks (etcd restart, network blip, timeout) and the events iterator stops yielding. The gateway continues running but never receives node updates again.
**Why it happens:** etcd3gw's `watch.Watcher` has no reconnection logic. When `iter_content` on the HTTP stream ends, the background thread exits silently.
**How to avoid:** Wrap `watch_prefix()` in a `while not stop_event.is_set()` loop with try/except. On any exception or iterator exhaustion, log a warning and retry after a configurable delay.
**Warning signs:** Gateway stops detecting new nodes added to etcd. Check logs for "etcd watch disconnected" messages.

### Pitfall 2: Key Encoding Confusion
**What goes wrong:** Keys returned by `get_prefix()` and watch events look different because of encoding paths.
**Why it happens:** `get_prefix()` returns `list[tuple[bytes, KeyValue]]` where the first element is the decoded value bytes and the second is a KeyValue dict with string keys. Watch events return decoded key/value as either `str` or `bytes` depending on the etcd3gw version. The key in `kv["key"]` from a watch event is already decoded from base64 by etcd3gw.
**How to avoid:** Always handle both `str` and `bytes` for keys and values. Use defensive decoding: `key.decode("utf-8") if isinstance(key, bytes) else key`.
**Warning signs:** Node IDs contain base64 characters or unexpected prefixes. Test with actual etcd to verify encoding behavior.

### Pitfall 3: Event Type Field Absence
**What goes wrong:** Code checks `event["type"] == "PUT"` but the field is absent for PUT events, causing a KeyError.
**Why it happens:** The etcd gRPC gateway uses proto3 JSON serialization, which omits fields set to their default enum value (0 = PUT). So PUT events have no `type` field; only DELETE events have `type: "DELETE"`.
**How to avoid:** Use `event.get("type", "PUT")` or check `event.get("type") == "DELETE"`.
**Warning signs:** KeyError exceptions in watch event handler. Nodes never get added despite PUT events firing.

### Pitfall 4: Lock Deadlock Between Thread and Event Loop
**What goes wrong:** Using `asyncio.Lock` for the registry and then accessing it from the watch thread causes silent failures or deadlocks.
**Why it happens:** `asyncio.Lock` only works within the asyncio event loop. The watch thread is a plain OS thread. Mixing `asyncio.Lock` and `threading.Lock` is a documented anti-pattern.
**How to avoid:** Use `threading.Lock` exclusively for the registry. It is safe to acquire a `threading.Lock` from both OS threads and asyncio coroutines (since coroutines run on the event loop's OS thread). The lock is never held across an `await` point, so no deadlock risk.
**Warning signs:** Registry appears empty despite nodes being in etcd. Hang on shutdown.

### Pitfall 5: Startup Failure Cascade
**What goes wrong:** etcd is unavailable at gateway startup, and the gateway crashes or enters a broken state.
**Why it happens:** The initial `get_prefix()` call raises `requests.exceptions.ConnectionError` if etcd is unreachable.
**How to avoid:** Per D-09, catch connection errors during initial load and start with an empty registry. Log a warning. The watch thread's reconnection loop will pick up nodes once etcd becomes available.
**Warning signs:** Gateway fails to start in environments where etcd starts after the gateway. Check for unhandled `ConnectionError` in lifespan.

### Pitfall 6: get_prefix Return Format
**What goes wrong:** Code assumes `get_prefix()` returns `list[tuple[bytes, dict]]` but actual format differs.
**Why it happens:** `get_prefix()` returns `list[tuple[bytes, KeyValue]]` where each tuple is `(value_bytes, metadata_dict)`. The metadata_dict contains the key under `metadata["key"]` (as bytes), not as the first tuple element. The first tuple element is the value bytes, not the key.
**How to avoid:** Access key from `metadata["key"]` and value from the first tuple element. Example: `for value, metadata in client.get_prefix("/nodes/"): key = metadata["key"]`.
**Warning signs:** Node IDs are binary garbage instead of readable strings. Keys look like raw JSON.

## Code Examples

Verified patterns from official sources:

### Creating an etcd3gw Client
```python
# Source: etcd3gw official docs
# [CITED: https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.client.html]

from etcd3gw.client import Etcd3Client

# Basic connection
client = Etcd3Client(host="localhost", port=2379, protocol="http")

# With timeout
client = Etcd3Client(host="etcd.internal", port=2379, timeout=30)
```

### Fetching All Nodes Under a Prefix
```python
# Source: etcd3gw official docs
# [CITED: https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.client.html]

# get_prefix always returns metadata (value, KeyValue tuples)
results = client.get_prefix("/nodes/")
for value_bytes, metadata in results:
    key = metadata["key"]  # bytes, e.g. b"/nodes/node-abc"
    # value_bytes is the raw value, e.g. b'{"endpoint": "http://10.0.1.100:8000", ...}'
```

### Watching a Prefix for Changes
```python
# Source: etcd3gw official docs + types.py
# [CITED: https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.client.html]
# [CITED: https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/types.py]

events_iter, cancel = client.watch_prefix("/nodes/")

# events_iter blocks on a queue.Queue internally
for event in events_iter:
    kv = event["kv"]
    key = kv["key"]        # bytes or str, already decoded from base64
    event_type = event.get("type")  # None for PUT, "DELETE" for delete
    if event_type == "DELETE":
        print(f"Node removed: {key}")
    else:
        value = kv.get("value", b"")  # absent on DELETE
        print(f"Node added/updated: {key} = {value}")

# To stop watching:
cancel()  # unblocks the iterator, closes the HTTP stream
```

### Putting and Getting Keys
```python
# Source: etcd3gw official docs
# [CITED: https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.client.html]

# Put a key
client.put("/nodes/node-abc", '{"endpoint": "http://10.0.1.100:8000"}')

# Get a single key (returns list of value bytes)
values = client.get("/nodes/node-abc")  # [b'{"endpoint": ...}']

# Delete a key
client.delete("/nodes/node-abc")  # returns True if deleted
```

### Creating a Lease with TTL
```python
# Source: etcd3gw official docs
# [CITED: https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.lease.html]

# Create a lease with 60-second TTL
lease = client.lease(ttl=60)

# Put a key with the lease attached
client.put("/nodes/node-abc", '{"endpoint": "..."}', lease=lease)

# Refresh the lease (keepalive)
new_ttl = lease.refresh()  # returns -1 if lease expired

# Get lease TTL
ttl = lease.ttl()

# Revoke the lease (all attached keys are deleted)
lease.revoke()
```

### Mocking etcd3gw in Tests
```python
# Source: etcd3gw test suite patterns
# [CITED: https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/tests/test_client.py]

from unittest.mock import MagicMock, patch


def test_initial_load(registry, mock_etcd_client):
    """Test that initial node fetch populates the registry."""
    # Mock the wrapper's get_prefix to return pre-built data
    mock_etcd_client.get_prefix.return_value = [
        (b'{"endpoint": "http://10.0.1.100:8000", "model": "llama"}',
         {"key": b"/nodes/node-1"}),
    ]
    # ... call the function under test
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-etcd3 (kragniz) with gRPC | etcd3gw with HTTP gateway | ~2022 (python-etcd3 abandoned) | No grpcio C extension needed. Simpler builds. |
| FastAPI `@app.on_event("startup")` | FastAPI lifespan context manager | FastAPI 0.93+ | Startup and shutdown in one function. Cleaner resource management. |
| etcd3gw 2.5.0 | etcd3gw 2.7.0 | June 2026 | Bug fixes including watch_prefix_once double-encoding fix. |

**Deprecated/outdated:**
- `@app.on_event("startup")` / `@app.on_event("shutdown")`: Deprecated in favor of lifespan. Still works but not recommended. [CITED: https://fastapi.tiangolo.com/advanced/events/]
- `python-etcd3` (kragniz): Abandoned. Do not use. [CITED: CLAUDE.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `threading.Lock` is safe to acquire from asyncio coroutines (since they run on a single OS thread and the lock is never held across await) | Architecture Patterns / Anti-Patterns | If wrong, could cause deadlock; but this is well-documented Python behavior -- risk is LOW |
| A2 | The reconnection loop pattern (while+try/except around watch_prefix) is sufficient for production reliability | Architecture Patterns / Pattern 3 | If watch_prefix leaks resources on repeated reconnections, could cause memory issues; mitigated by cancel() in finally |
| A3 | `get_prefix()` returns tuples of `(value_bytes, metadata_dict)` where metadata contains `key` | Code Examples / Pitfall 6 | If return format differs in 2.7.0, serializer will fail; mitigated by integration testing |

## Open Questions

1. **etcd3gw 2.7.0 changelog**
   - What we know: Version jumped from 2.5.0 to 2.7.0 between Jan and June 2026. The CLAUDE.md was written when 2.5.0 was latest.
   - What's unclear: Exact changes in 2.6.0 and 2.7.0. No changelog found on GitHub or OpenDev.
   - Recommendation: Use `>=2.5.0` as the floor (already in CLAUDE.md). Test against whatever version uv resolves. No known breaking changes.

2. **Watch event key/value encoding in latest etcd3gw**
   - What we know: The watch module decodes base64 internally. A double-encoding bug was fixed in `watch_prefix_once`. Keys in events are decoded to bytes or str.
   - What's unclear: Whether 2.7.0 returns `str` or `bytes` for `kv["key"]` in watch events.
   - Recommendation: Handle both `str` and `bytes` defensively in the serializer. Write tests that verify both code paths.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Yes (via uv) | 3.12.9 | -- |
| uv | Package management | Yes | 0.6.5 | -- |
| etcd3gw | etcd communication | Not installed yet | 2.7.0 (PyPI) | `uv add etcd3gw` |
| etcd server | Integration tests | No | -- | podman (available: v5.8.2) can run etcd container |
| podman | etcd container for tests | Yes | 5.8.2 | -- |

**Missing dependencies with no fallback:**
- None -- all blockers have solutions

**Missing dependencies with fallback:**
- etcd server not installed locally. For integration tests, use `podman run -d -p 2379:2379 quay.io/coreos/etcd:latest`. However, Phase 2 unit tests should mock etcd3gw -- integration tests are optional.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4.x |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/discovery/ -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DISC-01 | Initial node fetch from etcd populates registry | unit | `uv run pytest tests/discovery/test_etcd_client.py -x` | No -- Wave 0 |
| DISC-01 | Serializer parses valid JSON into Node | unit | `uv run pytest tests/discovery/test_serializer.py -x` | No -- Wave 0 |
| DISC-01 | Serializer handles malformed JSON gracefully | unit | `uv run pytest tests/discovery/test_serializer.py -x` | No -- Wave 0 |
| DISC-02 | Watch events dispatch to registry (PUT adds, DELETE removes) | unit | `uv run pytest tests/discovery/test_watcher.py -x` | No -- Wave 0 |
| DISC-02 | Watch reconnects after disconnection | unit | `uv run pytest tests/discovery/test_watcher.py -x` | No -- Wave 0 |
| DISC-01+02 | Registry thread-safety under concurrent access | unit | `uv run pytest tests/discovery/test_registry.py -x` | No -- Wave 0 |
| DISC-01+02 | Lifespan starts and stops watcher cleanly | unit | `uv run pytest tests/test_app.py -x` | Partially (smoke test exists) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/discovery/ -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/discovery/__init__.py` -- package init
- [ ] `tests/discovery/test_etcd_client.py` -- covers DISC-01
- [ ] `tests/discovery/test_serializer.py` -- covers DISC-01
- [ ] `tests/discovery/test_registry.py` -- covers DISC-01+02
- [ ] `tests/discovery/test_watcher.py` -- covers DISC-02
- [ ] Framework install: `uv add etcd3gw` -- not yet in project dependencies

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Internal network only (v1 constraint) |
| V3 Session Management | No | Stateless proxy, no sessions |
| V4 Access Control | No | No authorization in v1 |
| V5 Input Validation | Yes | Pydantic validation on Node deserialization; malformed JSON rejected gracefully |
| V6 Cryptography | No | No encryption needed for internal etcd communication in v1 |

### Known Threat Patterns for etcd Communication

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed JSON in etcd values | Tampering | Pydantic validation + try/except in serializer (D-12) |
| etcd unavailability | Denial of Service | Graceful degradation: empty registry + reconnection loop (D-09) |
| Stale node data after etcd partition | Information Disclosure (stale routing) | Watch reconnection loop detects and recovers from partitions |

## Project Constraints (from CLAUDE.md)

- **SOLID Principles required:** All code must follow SRP, OCP, LSP, ISP, DIP. The etcd client wrapper follows DIP (depend on abstraction, not concrete etcd3gw). Serializer follows SRP (separate from Node model). Registry follows ISP (focused interface: add/remove/get/get_all).
- **Tech stack locked:** Python, FastAPI, httpx, etcd3gw. No alternatives to evaluate.
- **Internal network only:** No TLS/auth needed for etcd connection in v1.
- **Dependency Injection via Depends():** Registry exposed via `get_registry()` dependency, following the `get_settings()` pattern from Phase 1.
- **hatchling build backend:** `inference_proxy` is importable via `uv run`.
- **structlog for logging:** All log output (watch events, errors, reconnections) uses structlog.
- **pytest with asyncio_mode="auto":** No manual `@pytest.mark.asyncio` needed.

## Sources

### Primary (HIGH confidence)
- etcd3gw official API docs: client module -- [https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.client.html](https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.client.html) -- full client API with method signatures
- etcd3gw types.py source -- [https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/types.py](https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/types.py) -- Event TypedDict, KeyValue TypedDict
- etcd3gw watch.py source -- [https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/watch.py](https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/watch.py) -- Watcher implementation (HTTP streaming, no reconnection)
- etcd3gw utils.py source -- [https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/utils.py](https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/utils.py) -- base64 encode/decode, _increment_last_byte
- etcd3gw client.py source -- [https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/client.py](https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/client.py) -- watch implementation (queue.Queue + threading.Event)
- etcd3gw lease docs -- [https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.lease.html](https://docs.openstack.org/etcd3gw/latest/api/etcd3gw.lease.html) -- Lease TTL, refresh, revoke
- etcd3gw PyPI -- [https://pypi.org/project/etcd3gw/](https://pypi.org/project/etcd3gw/) -- version 2.7.0, released 2026-06-09
- etcd3gw test suite -- [https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/tests/test_etcd3gw.py](https://opendev.org/openstack/etcd3gw/src/branch/master/etcd3gw/tests/test_etcd3gw.py) -- watch test patterns, mock approaches
- FastAPI lifespan docs -- [https://fastapi.tiangolo.com/advanced/events/](https://fastapi.tiangolo.com/advanced/events/) -- lifespan context manager pattern
- Python asyncio sync primitives -- [https://docs.python.org/3/library/asyncio-sync.html](https://docs.python.org/3/library/asyncio-sync.html) -- asyncio.Lock is NOT thread-safe

### Secondary (MEDIUM confidence)
- FastAPI background thread patterns -- [https://www.shiporkill.com/blog/fastapi-lifespan-pattern](https://www.shiporkill.com/blog/fastapi-lifespan-pattern) -- threading.Thread in lifespan pattern
- Python thread safety -- [https://docs.python.org/3/library/threadsafety.html](https://docs.python.org/3/library/threadsafety.html) -- dict operations, compound operations not atomic

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- etcd3gw is the only viable option per CLAUDE.md, version verified on PyPI
- Architecture: HIGH -- patterns derived from etcd3gw source code analysis (watch.py, client.py, types.py)
- Pitfalls: HIGH -- derived from actual source code (no reconnection in watcher, proto3 JSON event format, encoding behaviors)

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (etcd3gw is stable, slow-moving OpenStack project)
