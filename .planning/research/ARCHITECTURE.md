# Architecture Patterns

**Domain:** LLM inference gateway (OpenAI-compatible proxy to vLLM nodes)
**Researched:** 2026-06-10

## Recommended Architecture

The gateway follows a **centralized proxy pattern**: a single FastAPI service sits between clients and a fleet of vLLM inference nodes, using etcd as a live service registry. This is the simplest viable architecture for an internal inference gateway and aligns with how production LLM gateways are structured (vLLM Production Stack, LiteLLM, and similar systems all use this topology).

```
                    Clients
                       |
                       v
              +------------------+
              |  FastAPI Gateway |
              |                  |
              |  +------------+  |       +-------+
              |  | Router     |<-------->| etcd  |
              |  +-----+------+  |       +-------+
              |        |         |
              |  +-----v------+  |
              |  | Proxy Core |  |
              |  +-----+------+  |
              |        |         |
              +--------|---------+
                       |
          +------------+------------+
          |            |            |
     +----v----+  +----v----+  +----v----+
     |  vLLM   |  |  vLLM   |  |  vLLM   |
     | Node A  |  | Node B  |  | Node N  |
     | (Podman)|  | (Podman)|  | (Podman)|
     +---------+  +---------+  +---------+
          |            |            |
          +-----+------+------+-----+
                |             |
           +----v----+   +----v----+
           |   NFS   |   |   GPU   |
           | (Models)|   | (Infer) |
           +---------+   +---------+
```

### Component Boundaries

The gateway decomposes into five internal components and two external dependencies.

| Component | Responsibility | Communicates With | Boundary Type |
|-----------|---------------|-------------------|---------------|
| **API Layer** | Accept OpenAI-compatible HTTP requests, validate structure, route to handlers | Proxy Core, Health Checker | FastAPI router endpoints |
| **Node Registry** | Maintain in-memory list of healthy vLLM nodes, react to etcd watch events | etcd (external), Router, Health Checker | Class/module with async watch loop |
| **Router** | Select which node handles a given request using least-connections + model affinity | Node Registry, Connection Tracker | Pure function / strategy interface |
| **Proxy Core** | Forward requests to selected vLLM node, stream SSE responses back, handle retries | Router, vLLM nodes (external), Connection Tracker | Async function using httpx |
| **Health Checker** | Periodically probe vLLM `/health` endpoints, mark nodes healthy/unhealthy | Node Registry, vLLM nodes (external) | Background asyncio task |
| **Connection Tracker** | Track active request count per node for least-connections routing | Router, Proxy Core | In-memory counter (dict + asyncio lock) |
| **Config** | Load and validate gateway configuration (etcd endpoints, timeouts, retry policy) | All components | Pydantic settings / dataclass |

**External dependencies:**

| External System | Role | Protocol |
|----------------|------|----------|
| **etcd** | Service registry: nodes register themselves; gateway watches for changes | gRPC (via Python client) or HTTP gateway |
| **vLLM nodes** | Serve inference requests via OpenAI-compatible API | HTTP (port 8000) |

### Why These Boundaries

Each component has a single reason to change (SRP), communicates through well-defined interfaces (DIP), and can be tested independently by injecting mock dependencies. The Router is a strategy that can be swapped without modifying the Proxy Core (OCP). The Node Registry abstracts away etcd specifics so the rest of the system depends on an interface, not the etcd client directly (DIP).

---

## Data Flow

### Non-Streaming Request (e.g., `/v1/models`)

```
Client --HTTP POST--> API Layer
                        |
                        v
                    API Layer validates request shape
                        |
                        v
                    Router.select_node(model, request)
                        |
                        +-- queries Node Registry for healthy nodes with matching model
                        +-- queries Connection Tracker for active counts
                        +-- returns node with fewest active connections
                        |
                        v
                    Connection Tracker.increment(node)
                        |
                        v
                    Proxy Core.forward(node, request)
                        |
                        +-- httpx.AsyncClient.post(node.endpoint + path, json=body)
                        +-- on success: return response JSON
                        +-- on failure: Connection Tracker.decrement(node)
                        |              mark node suspect
                        |              retry with Router.select_node (excluding failed node)
                        v
                    Connection Tracker.decrement(node)
                        |
                        v
                    API Layer returns response to client
```

### Streaming Request (SSE, e.g., `/v1/chat/completions` with `stream: true`)

```
Client --HTTP POST--> API Layer
                        |
                        v
                    Same routing as above
                        |
                        v
                    Connection Tracker.increment(node)
                        |
                        v
                    Proxy Core.stream(node, request)
                        |
                        +-- httpx.AsyncClient.stream("POST", node.endpoint + path, json=body)
                        +-- yield chunks via response.aiter_lines()
                        +-- wrap in StreamingResponse(media_type="text/event-stream")
                        +-- on client disconnect: close upstream, decrement counter
                        v
                    Connection Tracker.decrement(node)
                        |
                        v
                    StreamingResponse completes
```

**Critical detail for SSE proxy:** The `StreamingResponse` must use `media_type="text/event-stream; charset=utf-8"`, not `application/json`. This is a documented bug in naive vLLM proxy implementations where hardcoded JSON content-type breaks SSE semantics for OpenAI SDK clients.

### Node Discovery Flow (Background)

```
Gateway starts
    |
    v
Node Registry connects to etcd
    |
    +-- reads all keys under /nodes/ prefix (initial snapshot)
    +-- starts watch on /nodes/ prefix
    |
    v
Watch loop (runs forever):
    |
    +-- PUT event: add/update node in in-memory registry
    +-- DELETE event: remove node from in-memory registry
    +-- Connection error: reconnect with backoff
```

### Health Check Flow (Background)

```
Health Checker starts (periodic, e.g., every 10s)
    |
    v
For each node in Node Registry:
    |
    +-- GET node.endpoint/health (timeout: 5s)
    +-- Success: mark healthy, reset failure counter
    +-- Failure: increment failure counter
    |     +-- if failures >= threshold (e.g., 3): mark unhealthy
    |     +-- unhealthy nodes excluded from routing
    +-- Node returns healthy after cooldown: mark healthy again
```

---

## Internal Component Design

### API Layer

The API Layer is a set of FastAPI route handlers. It owns request validation and response formatting but delegates all routing and proxying to other components.

**Endpoints to implement (matching OpenAI API contract):**

| Endpoint | Method | Streaming | Purpose |
|----------|--------|-----------|---------|
| `/v1/chat/completions` | POST | Yes (optional) | Chat inference |
| `/v1/completions` | POST | Yes (optional) | Text completion |
| `/v1/models` | GET | No | List available models |
| `/health` | GET | No | Gateway health |
| `/healthz` | GET | No | Liveness probe (alias) |

Each endpoint handler follows the same pattern: validate, route, proxy, return. The streaming vs. non-streaming split is determined by the `stream` field in the request body.

### Node Registry

Maintains an in-memory `dict[str, NodeInfo]` mapping node IDs to their metadata (endpoint URL, model name, capabilities, health status). Populated on startup from etcd, kept current via etcd watch.

```python
# Conceptual interface (not implementation)
class NodeRegistry(Protocol):
    async def get_healthy_nodes(self, model: str | None = None) -> list[NodeInfo]: ...
    async def mark_unhealthy(self, node_id: str) -> None: ...
    async def mark_healthy(self, node_id: str) -> None: ...
    # Watch loop is internal implementation detail
```

**etcd key structure** (from PLAN.md):
```
/nodes/{node-id} -> JSON { endpoint, status, model, last_heartbeat, capabilities }
```

**etcd client choice:** The Python etcd3 async ecosystem is fragmented. Options:

| Library | Status | Notes |
|---------|--------|-------|
| `etcetra` | Active (asyncio native, pure gRPC) | Best async option; watch + lease support |
| `aetcd` | Maintained fork of etcd3aio | Good docs, asyncio native |
| `async-etcd3gw` | Active (HTTP gateway based) | Simpler setup, no gRPC dependency |
| `etcd3` (sync) | Stable but sync-only | Would need `run_in_executor` wrapping |

**Recommendation:** Use `aetcd` or `etcetra` for native asyncio watch support. If gRPC dependency management proves painful, fall back to `async-etcd3gw` which uses the HTTP gateway. The watch mechanism is critical -- polling etcd on a timer is inferior because it misses events and adds latency. Confidence: MEDIUM (ecosystem is fragmented; validate library choice with a spike).

### Router (Load Balancer)

The Router is a **strategy** that selects a node for a given request. The v1 strategy is least-connections with model affinity filtering.

```python
# Conceptual interface
class RoutingStrategy(Protocol):
    def select(
        self,
        healthy_nodes: list[NodeInfo],
        active_connections: dict[str, int],
        request_model: str,
    ) -> NodeInfo | None: ...
```

**Least-connections algorithm:**

1. Filter `healthy_nodes` to those serving the requested model
2. From filtered set, pick the node with the lowest value in `active_connections`
3. Break ties arbitrarily (or by node ID for determinism)
4. Return `None` if no nodes available (caller raises 503)

**Why least-connections over round-robin:** LLM inference requests have highly variable duration -- a 10-token response completes in milliseconds while a 4096-token generation takes seconds. Round-robin sends the same number of requests to each node regardless of how long prior requests take, leading to uneven load. Least-connections naturally routes to the node that finishes work fastest. This is the correct default for inference workloads.

**Future evolution (not v1):** KV-cache-aware routing via consistent hashing. This routes requests with similar prefixes to the same node, maximizing KV cache reuse and reducing time-to-first-token. The vLLM Router (Rust-based) and llm-d both implement this pattern. The strategy interface makes it possible to add this later without modifying existing code.

### Connection Tracker

A simple in-memory counter per node. Must be concurrency-safe since multiple requests are in-flight simultaneously in the asyncio event loop.

```python
# Conceptual structure
class ConnectionTracker:
    _counts: dict[str, int]  # node_id -> active connections

    def increment(self, node_id: str) -> None: ...
    def decrement(self, node_id: str) -> None: ...
    def get_counts(self) -> dict[str, int]: ...
```

**Concurrency note:** Within a single asyncio event loop (single process), dict operations are atomic between `await` points. An `asyncio.Lock` is technically unnecessary for simple increment/decrement if no `await` occurs between read and write. However, wrapping in a lock is defensive and has negligible overhead. If the gateway runs multi-process (multiple Uvicorn workers), each process has its own counter -- this is acceptable because each process independently tracks its own connections.

### Proxy Core

The Proxy Core owns the `httpx.AsyncClient` and handles both streaming and non-streaming forwarding.

**Key design decisions:**

1. **Single `httpx.AsyncClient` per process lifetime** -- created in FastAPI lifespan, closed on shutdown. Shares connection pool across all requests. Configure with `httpx.Limits(max_connections=100, max_keepalive_connections=20)` and appropriate timeouts.

2. **Streaming proxy pattern:**
   ```python
   async def stream_proxy(client, node, request_body):
       async with client.stream("POST", f"{node.endpoint}/v1/chat/completions",
                                json=request_body) as upstream:
           async def generate():
               async for line in upstream.aiter_lines():
                   yield line + "\n"
           return StreamingResponse(
               generate(),
               media_type="text/event-stream; charset=utf-8",
               headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
           )
   ```

3. **Retry logic:** On connection error or 5xx from vLLM node:
   - Decrement connection count on failed node
   - Exclude failed node from candidate set
   - Re-invoke Router to select a different node
   - Maximum 2 retries (3 total attempts)
   - **Never retry streaming requests that have already started sending chunks** -- the client has received partial data and retrying would produce garbled output
   - Only retry on connection-level failures, not on HTTP 4xx (client errors)

4. **Client disconnect handling:** Check `request.is_disconnected()` or catch `asyncio.CancelledError` to stop reading from upstream and close the connection cleanly. This prevents zombie connections to vLLM nodes when clients abort.

### Health Checker

Runs as a background `asyncio.Task` started in the FastAPI lifespan. Probes each registered node at a configurable interval.

**Design:**
- Probe endpoint: `GET {node.endpoint}/health` (vLLM provides this natively)
- Timeout per probe: 5 seconds
- Failure threshold: 3 consecutive failures before marking unhealthy
- Recovery: Node marked healthy again after 1 successful probe
- Probes run concurrently via `asyncio.gather` for all nodes

**Relationship to etcd:** Health Checker updates the Node Registry's in-memory state (healthy/unhealthy). It does NOT write health status back to etcd -- the control plane (out of scope for v1) owns etcd writes. The gateway is a read-only consumer of etcd data plus its own health observations.

**Circuit breaker integration (simple version):** When a node is marked unhealthy by the Health Checker, it enters a cooldown period. The Router excludes cooled-down nodes. When the cooldown TTL expires, the Health Checker re-probes. This is functionally equivalent to a circuit breaker with CLOSED -> OPEN -> HALF-OPEN states, but implemented simply via the health check loop rather than a separate circuit breaker library.

---

## Patterns to Follow

### Pattern 1: Strategy Pattern for Routing

**What:** Define a `RoutingStrategy` protocol/ABC. Implement `LeastConnectionsStrategy` as the default. The Router holds a reference to the strategy and delegates selection.

**When:** Always -- this is the primary extension point for the gateway.

**Why:** The PLAN.md already lists four routing strategies (round-robin, least-connections, response-time, model-affinity). Making this pluggable from day one costs almost nothing and avoids the `if/elif` chain anti-pattern.

```python
from typing import Protocol

class RoutingStrategy(Protocol):
    def select(
        self,
        nodes: list[NodeInfo],
        connections: dict[str, int],
        model: str,
    ) -> NodeInfo | None: ...

class LeastConnectionsStrategy:
    def select(self, nodes, connections, model):
        candidates = [n for n in nodes if n.model == model and n.healthy]
        if not candidates:
            return None
        return min(candidates, key=lambda n: connections.get(n.id, 0))
```

### Pattern 2: Lifespan-Managed Resources

**What:** Use FastAPI's `@asynccontextmanager` lifespan to initialize and tear down shared resources: httpx client, etcd watcher, health check task.

**When:** For any resource that should live for the process lifetime.

**Why:** Prevents per-request overhead (connection pool creation), ensures clean shutdown, and is the officially recommended FastAPI pattern.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.http_client = httpx.AsyncClient(limits=..., timeout=...)
    app.state.registry = NodeRegistry(etcd_endpoints=...)
    await app.state.registry.start_watching()
    app.state.health_task = asyncio.create_task(health_check_loop(app.state.registry))

    yield

    # Shutdown
    app.state.health_task.cancel()
    await app.state.registry.stop_watching()
    await app.state.http_client.aclose()
```

### Pattern 3: Dependency Injection via FastAPI Depends

**What:** Inject the Node Registry, Router, and httpx client into route handlers via `Depends()`.

**When:** Every route handler that needs access to shared state.

**Why:** Makes handlers testable (inject mocks), keeps handlers thin, enforces DIP.

```python
async def get_registry(request: Request) -> NodeRegistry:
    return request.app.state.registry

@app.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    registry: NodeRegistry = Depends(get_registry),
    # ...
):
    ...
```

### Pattern 4: Background Watch Loop with Reconnection

**What:** The etcd watch runs as a long-lived async generator. On disconnection, reconnect with exponential backoff starting from the last known revision.

**When:** The Node Registry's etcd integration.

**Why:** etcd watch connections can drop (network blip, etcd restart). Without reconnection logic, the gateway silently stops receiving node updates and routes to stale data.

```python
async def watch_nodes(self):
    revision = 0
    while True:
        try:
            async for event in self.etcd.watch_prefix("/nodes/", start_revision=revision):
                revision = event.mod_revision + 1
                if event.type == PUT:
                    self._update_node(event.key, event.value)
                elif event.type == DELETE:
                    self._remove_node(event.key)
        except ConnectionError:
            await asyncio.sleep(min(2 ** self._retry_count, 30))
            self._retry_count += 1
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Creating httpx.AsyncClient Per Request

**What:** Instantiating a new `httpx.AsyncClient()` inside each request handler.

**Why bad:** Destroys connection pooling. Each request opens a new TCP connection to the vLLM node, with full TLS handshake overhead (if TLS is used). Under load, this exhausts file descriptors and dramatically increases latency.

**Instead:** Create one `AsyncClient` in the lifespan, share it via `app.state`.

### Anti-Pattern 2: Polling etcd Instead of Watching

**What:** Using a timer to periodically read all keys from etcd.

**Why bad:** Misses events between polls (node added, then immediately removed). Adds unnecessary load on etcd. Introduces latency between actual state change and gateway awareness. Does not scale -- polling N keys every M seconds is O(N) per poll.

**Instead:** Use etcd's watch API with prefix watching. React to events in real-time. Fall back to a full re-read only on watch reconnection to catch any missed events.

### Anti-Pattern 3: Retrying Partially-Streamed Responses

**What:** When a vLLM node fails mid-stream, attempting to retry the request on another node and continue streaming.

**Why bad:** The client has already received partial SSE data. Retrying produces a new response that starts from the beginning, resulting in duplicate or garbled output. OpenAI SDK clients parse SSE events sequentially and will break.

**Instead:** If the connection fails before any data is sent to the client, retry on another node. If chunks have already been sent, propagate the error to the client (send an SSE error event or close the connection). The client application is responsible for retry at the application level.

### Anti-Pattern 4: Monolithic Gateway Class

**What:** A single class that handles routing, health checking, etcd communication, request proxying, and connection tracking.

**Why bad:** Violates SRP. Every change to any subsystem risks breaking others. Untestable without standing up the entire stack.

**Instead:** Separate components with clear interfaces as described in the component boundaries above. Each can be unit-tested with mocks.

### Anti-Pattern 5: Synchronous etcd Client in Async Context

**What:** Using the synchronous `etcd3` client inside async FastAPI handlers.

**Why bad:** Blocks the event loop during etcd calls. Every etcd read/watch blocks all other request processing. Under load, this creates a bottleneck that defeats the purpose of async.

**Instead:** Use an async-native etcd client (`aetcd`, `etcetra`, or `async-etcd3gw`). If forced to use the sync client, wrap calls in `asyncio.get_event_loop().run_in_executor()`, but this is strictly inferior.

---

## Build Order (Component Dependencies)

Components must be built in an order that respects their dependencies. Each layer depends on the one below it.

```
Layer 0 (no dependencies):
    Config
    Connection Tracker
    NodeInfo model / data structures

Layer 1 (depends on Layer 0):
    Node Registry (depends on: Config for etcd endpoints, NodeInfo model)
    Routing Strategy (depends on: NodeInfo model, Connection Tracker interface)

Layer 2 (depends on Layers 0-1):
    Health Checker (depends on: Node Registry, Config for intervals/thresholds)
    Proxy Core (depends on: Connection Tracker, httpx client)

Layer 3 (depends on Layers 0-2):
    API Layer (depends on: Router, Proxy Core, Node Registry)

Layer 4 (integration):
    Lifespan wiring (connects all components)
    End-to-end tests
```

### Suggested Build Sequence

**Phase 1: Foundation** -- Build Layers 0-1. This gives you data models, config loading, a working Node Registry with etcd watch, and the routing strategy. These can be fully unit-tested without any HTTP concerns.

**Phase 2: Proxy Core** -- Build the httpx-based forwarding for both streaming and non-streaming requests. Test against a mock HTTP server or a real vLLM instance. This is where SSE streaming correctness is validated.

**Phase 3: API Surface** -- Wire FastAPI endpoints, connect Proxy Core to Router, add the lifespan. This produces a functional gateway that can proxy requests.

**Phase 4: Resilience** -- Add Health Checker, retry logic, circuit breaker behavior, and graceful degradation. This hardens the gateway for production use.

**Phase 5: Observability** -- Add structured logging, request tracing, and metrics endpoints. Not strictly required for functionality but essential for operations.

### Rationale for This Order

- Layers 0-1 are pure logic with no I/O dependencies, making them fast to build and test.
- The Proxy Core (Layer 2) is the highest-risk component due to SSE streaming complexity. Getting it right early reduces integration surprises.
- The API Layer (Layer 3) is mostly glue code once the lower layers work.
- Resilience (Layer 4) is important but separable -- a gateway without health checks still works (it just lacks failover). Building resilience last means you have a working baseline to compare against.

---

## Scalability Considerations

| Concern | At 10 users | At 100 users | At 1000+ users |
|---------|-------------|--------------|-----------------|
| **Connection pool** | Default httpx limits sufficient | Tune `max_connections` per vLLM node | Consider per-node connection limits |
| **Gateway instances** | Single process, single worker | Single process, 2-4 Uvicorn workers | Multiple gateway instances behind NGINX |
| **etcd load** | Negligible (watch is long-lived) | Still negligible | Still negligible -- watch is O(events), not O(clients) |
| **Node registry consistency** | Single process = always consistent | Multi-worker = each worker has own copy (acceptable) | Multi-instance = each instance has own copy (acceptable, etcd ensures eventual consistency) |
| **Connection tracking accuracy** | Perfect (single process) | Per-worker (slightly imbalanced routing) | Per-instance (use external metrics for better accuracy) |
| **Streaming memory** | Minimal (httpx streams without buffering) | Monitor per-connection memory | Set maximum concurrent streams |

**Key insight:** For this project's scope (internal network, likely <100 concurrent users), a single-process gateway with 2-4 Uvicorn workers is sufficient. The architecture supports horizontal scaling (multiple gateway instances behind NGINX) without code changes -- each instance independently watches etcd and maintains its own state.

---

## Sources

### Architecture Patterns
- [AI Gateway Architecture: Components (DeepInspect)](https://www.deepinspect.ai/blog/ai-gateway-architecture) - HIGH confidence
- [LLM Gateway Architecture (AWS Labs)](https://awslabs.github.io/generative-ai-atlas/topics/3_0_architecture_and_design_patterns/3_1_system_and_application_design_patterns_for_genai/3_1_1_foundation_architecture_components/3_1_1_4_llm_gateway/index.html) - HIGH confidence
- [vLLM Production Stack Architecture (DeepWiki)](https://deepwiki.com/vllm-project/production-stack/2-architecture) - HIGH confidence

### vLLM Router & Load Balancing
- [vLLM Router Release Blog](https://blog.vllm.ai/2025/12/13/vllm-router-release.html) - HIGH confidence
- [KV Cache Utilization-Aware Load Balancing (BentoML)](https://bentoml.com/llm/inference-optimization/kv-cache-utilization-aware-load-balancing) - HIGH confidence
- [Load Balancing and Scaling LLM Serving (DigitalOcean)](https://www.digitalocean.com/blog/load-balancing-scaling-llm-serving) - MEDIUM confidence
- [LLM Load Balancing at Scale: CHWBL (KubeAI)](https://www.kubeai.org/blog/2025/02/26/llm-load-balancing-at-scale-chwbl/) - HIGH confidence

### FastAPI + httpx Streaming
- [FastAPI SSE Documentation](https://fastapi.tiangolo.com/tutorial/server-sent-events/) - HIGH confidence (official)
- [httpx Async Streaming Documentation](https://www.python-httpx.org/async) - HIGH confidence (official, verified via Context7)
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/testing-events) - HIGH confidence (official, verified via Context7)
- [vLLM SSE Content-Type Bug Fix (PR #6985)](https://github.com/vllm-project/vllm-ascend/pull/6985) - HIGH confidence

### etcd Python Clients
- [etcd Official Discussion on Python Clients](https://github.com/etcd-io/etcd/discussions/18211) - HIGH confidence
- [etcetra (async gRPC client)](https://github.com/lablup/etcetra) - MEDIUM confidence
- [aetcd (asyncio etcd3 client)](https://github.com/martyanov/aetcd) - MEDIUM confidence

### Resilience Patterns
- [Circuit Breakers for LLM APIs (n1n.ai)](https://explore.n1n.ai/blog/circuit-breakers-llm-api-sre-reliability-patterns-2026-02-15) - MEDIUM confidence
- [Retries, Fallbacks, and Circuit Breakers (Portkey)](https://portkey.ai/blog/retries-fallbacks-and-circuit-breakers-in-llm-apps/) - MEDIUM confidence
- [LiteLLM Health Monitoring (Cooldown Pattern)](https://leeroopedia.com/index.php/Principle:BerriAI_Litellm_Health_Monitoring) - MEDIUM confidence
