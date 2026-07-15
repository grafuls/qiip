# Architecture: QUADS API Integration (v1.3)

**Domain:** QUADS REST API integration into existing LLM inference gateway
**Researched:** 2026-07-15
**Overall confidence:** HIGH

## Decision: QUADS Client as a New Service Layer, Not an Extension of Provisioner

Add a `QUADSClient` in a new `inference_proxy/quads/` package. Do NOT bolt QUADS calls onto `NodeProvisioner` -- the provisioner orchestrates SSH setup sequences; the QUADS client discovers what hosts exist in the lab. Different responsibilities, different change frequencies.

The unified node list is a **read-side merge** in the admin API layer. The QUADS client provides "what hosts exist," the NodeRegistry provides "what nodes are running." The admin endpoint merges them. No new data store needed.

**Why not extend NodeProvisioner?** The provisioner already has a clear job: run SSH sequences and register nodes in etcd. Adding QUADS polling and host discovery to it violates SRP and creates a class that changes for two unrelated reasons (QUADS API changes vs SSH setup changes).

**Why not a separate microservice?** Same reasoning as v1.2 -- the gateway already owns the NodeRegistry, dashboard, and admin API. A separate service would need IPC just to produce a merged view. YAGNI.

## Architecture Overview

```
              +----------------------------------------------------+
              |               FastAPI Gateway                      |
              |                                                    |
              |  +----------+  +-----------+  +------------------+ |
              |  | /v1/*    |  | /admin/*  |  | /dashboard       | |
              |  | (proxy)  |  | (fleet)   |  | (UI)             | |
              |  +----------+  +-----+-----+  +--------+---------+ |
              |                      |                 |           |
              |          +-----------v-----------------v------+    |
              |          | /admin/nodes  (MODIFIED)            |    |
              |          |   Merges QUADS hosts + etcd nodes   |    |
              |          +-----+-------------------+-----------+    |
              |                |                   |               |
              |     +----------v------+  +---------v-----------+   |
              |     | QUADSClient     |  | NodeRegistry        |   |
              |     | (HTTP to QUADS) |  | (etcd-backed)       |   |
              |     +----------+------+  +---------------------+   |
              |                |                                   |
              |     +----------v------+                            |
              |     | QUADSPoller     |                            |
              |     | (background     |                            |
              |     |  asyncio.Task)  |                            |
              |     +-----------------+                            |
              |                                                    |
              |  Existing unchanged:                               |
              |  +------------+ +----------+ +------------------+  |
              |  | Watcher    | | HealthChk| | NodeProvisioner  |  |
              |  | (thread)   | | (thread) | | (asyncio tasks)  |  |
              |  +------------+ +----------+ +------------------+  |
              +----------------------------------------------------+
                     |                              |
              +------v------+              +--------v--------+
              | etcd        |              | QUADS API       |
              | /nodes/*    |              | /api/v3/hosts   |
              +-------------+              | /api/v3/available|
                                           +-----------------+
```

## New Components

| Component | Responsibility | Lives In | Communicates With |
|-----------|---------------|----------|-------------------|
| **QUADSClient** | HTTP calls to QUADS REST API. Get hosts, check availability, filter by cloud. Stateless. | `inference_proxy/quads/client.py` | QUADS API server (external) |
| **QUADSPoller** | Background asyncio.Task that periodically calls QUADSClient and caches results in-memory | `inference_proxy/quads/poller.py` | QUADSClient |
| **QUADSHost** | Pydantic model for a QUADS host (name, model, cloud, broken, retired, etc.) | `inference_proxy/models/quads.py` | QUADSClient, admin API, dashboard |
| **QUADSSettings** | QUADS API URL, poll interval, cloud filter, auth token | `inference_proxy/config/settings.py` (add nested model) | Settings |
| **UnifiedNodeResponse** | Admin response model merging QUADS host info + etcd node info | `inference_proxy/models/admin.py` (extend) | Admin API, dashboard |

### Modified Components

| Component | Change | Why |
|-----------|--------|-----|
| `settings.py` | Add `QUADSSettings` nested model | QUADS API URL, poll interval, spare pool cloud name |
| `admin.py` | Modify `GET /admin/nodes` to merge QUADS + etcd data | Unified node list is the core v1.3 deliverable |
| `dependencies.py` | Add `get_quads_poller()` | Follow existing DI pattern |
| `main.py` lifespan | Create QUADSClient, QUADSPoller, store in `app.state` | Follow existing lifespan pattern |
| `dashboard.html` | Replace setup form with inline actions per node, show QUADS hosts as "available" rows | v1.3 UI redesign |
| `models/admin.py` | Add `UnifiedNodeResponse` model | Merged view needs a richer response model |

## Data Flow: Unified Node List

This is the central design question. Two data sources produce one merged view.

### Source 1: QUADS API (all lab hosts)

```
QUADS API /api/v3/hosts  -->  QUADSClient.get_hosts()
QUADS API /api/v3/available  -->  QUADSClient.get_available()
```

Returns: hostname, model, cloud assignment, broken/retired flags. The `/available` endpoint returns hostnames of hosts not currently scheduled (in the spare pool).

### Source 2: etcd NodeRegistry (provisioned nodes)

```
etcd /nodes/*  -->  NodeRegistry.get_all()
```

Returns: node_id (hostname), endpoint, model, status (HEALTHY/UNHEALTHY/PROVISIONING/DRAINING).

### Merge Logic

The merge happens at request time in the admin endpoint. No persistent merged store.

```python
def merge_node_list(
    quads_hosts: list[QUADSHost],
    registry_nodes: list[Node],
    provisioning_tasks: list[ProvisioningState],
) -> list[UnifiedNodeResponse]:
    """Merge QUADS hosts with etcd-registered nodes.

    Priority: etcd node data wins over QUADS data for provisioned hosts.
    QUADS hosts not in etcd appear as "available".
    etcd nodes not in QUADS appear as-is (manually registered).
    """
    etcd_by_hostname: dict[str, Node] = {n.node_id: n for n in registry_nodes}
    provisioning_by_hostname: dict[str, ProvisioningState] = {
        t.hostname: t for t in provisioning_tasks
    }

    result = []
    seen_hostnames: set[str] = set()

    for host in quads_hosts:
        seen_hostnames.add(host.name)
        node = etcd_by_hostname.get(host.name)
        task = provisioning_by_hostname.get(host.name)

        if node is not None:
            # Provisioned -- use etcd status, enrich with QUADS metadata
            result.append(UnifiedNodeResponse(
                hostname=host.name,
                source="etcd",
                status=node.status.value,
                model=node.model or host.model,
                cloud=host.cloud,
                endpoint=node.endpoint,
                # ... circuit breaker, connections, etc.
            ))
        elif task is not None and task.current_step not in ("complete", "failed"):
            # Currently provisioning
            result.append(UnifiedNodeResponse(
                hostname=host.name,
                source="provisioning",
                status="provisioning",
                provisioning_step=task.current_step,
                model=host.model,
                cloud=host.cloud,
            ))
        else:
            # Available in QUADS, not provisioned
            result.append(UnifiedNodeResponse(
                hostname=host.name,
                source="quads",
                status="available" if host.available else "assigned",
                model=host.model,
                cloud=host.cloud,
                broken=host.broken,
                retired=host.retired,
            ))

    # etcd nodes not in QUADS (manually registered or QUADS unavailable)
    for node_id, node in etcd_by_hostname.items():
        if node_id not in seen_hostnames:
            result.append(UnifiedNodeResponse(
                hostname=node_id,
                source="etcd",
                status=node.status.value,
                model=node.model,
                endpoint=node.endpoint,
            ))

    return result
```

### Node States in the Unified View

| State | Source | Available Actions | UI Treatment |
|-------|--------|-------------------|-------------|
| `available` | QUADS (in spare pool, not provisioned) | Setup | Green "Available" badge, Setup button |
| `assigned` | QUADS (scheduled to a cloud, not spare pool) | None | Grey "Assigned" badge, no actions |
| `provisioning` | etcd (PROVISIONING status) or in-flight task | Cancel (future) | Yellow "Provisioning" badge + step name |
| `healthy` | etcd (HEALTHY) | Teardown | Green "Healthy" badge, Teardown button |
| `unhealthy` | etcd (UNHEALTHY) | Teardown, Retry | Red "Unhealthy" badge, Teardown button |
| `draining` | etcd (DRAINING) | None (in progress) | Orange "Draining" badge |
| `broken` | QUADS (broken=true) | None | Red "Broken" badge |
| `retired` | QUADS (retired=true) | None | Grey "Retired" badge |

## QUADSClient Design

### HTTP Client

Use `httpx.AsyncClient` -- already in the stack, no new dependency. The QUADS API is standard REST/JSON.

```python
class QUADSClient:
    """Async client for the QUADS REST API (v3).

    Stateless. All methods are async and return parsed Pydantic models.
    """

    def __init__(self, settings: QUADSSettings) -> None:
        self._base_url = settings.api_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
            # ponytail: auth token header if QUADS v3 RBAC is enabled
            headers={"Authorization": f"Bearer {settings.token}"} if settings.token else {},
        )

    async def get_hosts(self, **filters: str) -> list[QUADSHost]:
        """GET /api/v3/hosts with optional filters."""
        response = await self._client.get("/api/v3/hosts", params=filters)
        response.raise_for_status()
        return [QUADSHost.model_validate(h) for h in response.json()]

    async def get_available(
        self, start: str | None = None, end: str | None = None
    ) -> set[str]:
        """GET /api/v3/available -- returns set of available hostnames."""
        params: dict[str, str] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        response = await self._client.get("/api/v3/available", params=params)
        response.raise_for_status()
        return set(response.json())  # API returns list of hostname strings

    async def close(self) -> None:
        await self._client.aclose()
```

**Key detail:** The QUADS `/api/v3/available` endpoint returns a list of hostname strings (not full host objects). The client must call `get_hosts()` separately for full metadata, then cross-reference with `get_available()` to mark which hosts are available. This matches how the QUADS Python client itself works (`filter_available` makes N+1 calls).

### Optimization: Single Call Strategy

Instead of calling both `/hosts` and `/available`, call `/hosts` once (gets all hosts with their cloud assignment), then determine availability by checking if the host's current cloud equals the spare pool cloud (typically `cloud01`). This avoids the N+1 problem in the QUADS client.

```python
async def get_hosts_with_availability(self, spare_pool_cloud: str = "cloud01") -> list[QUADSHost]:
    """Get all hosts and infer availability from cloud assignment."""
    hosts = await self.get_hosts()
    available = await self.get_available()
    for host in hosts:
        host.available = host.name in available
    return hosts
```

This keeps it to 2 API calls per poll cycle regardless of host count.

## QUADSPoller Design

### Why a Poller Instead of On-Demand Calls

The dashboard polls `/admin/nodes` every N seconds. If each poll triggered QUADS API calls, the gateway would make 2 HTTP requests to QUADS per dashboard poll. With multiple dashboard tabs open, this multiplies. A background poller decouples QUADS fetch frequency from dashboard request frequency.

### Implementation

```python
class QUADSPoller:
    """Background poller that caches QUADS host data in memory.

    Runs as an asyncio.Task started in lifespan. Caches the latest
    successful response. On QUADS API failure, serves stale data.
    """

    def __init__(self, client: QUADSClient, settings: QUADSSettings) -> None:
        self._client = client
        self._interval = settings.poll_interval
        self._hosts: list[QUADSHost] = []
        self._last_fetch: datetime | None = None
        self._task: asyncio.Task[None] | None = None

    def get_hosts(self) -> list[QUADSHost]:
        """Return cached QUADS hosts. Non-async, thread-safe read."""
        return list(self._hosts)  # shallow copy

    async def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _poll_loop(self) -> None:
        while True:
            try:
                hosts = await self._client.get_hosts_with_availability()
                self._hosts = hosts
                self._last_fetch = datetime.now(timezone.utc)
            except Exception:
                logger.warning("quads_poll_failed", exc_info=True)
                # Serve stale data on failure -- better than empty
            await asyncio.sleep(self._interval)
```

### Coordination with Existing Background Tasks

| Background Task | Runs As | Interval | Shares State With |
|----------------|---------|----------|-------------------|
| etcd watcher | `threading.Thread` | Continuous (blocking watch) | NodeRegistry (thread-safe) |
| Health checker | `threading.Thread` | 30s (configurable) | NodeRegistry, CircuitBreakerRegistry |
| **QUADS poller** | `asyncio.Task` | 60s (configurable) | Internal cache only |

The QUADS poller does NOT write to NodeRegistry. It maintains its own cache. This means:
- No lock contention with the watcher or health checker.
- No risk of QUADS data overwriting etcd-sourced data.
- The merge happens at read time in the admin endpoint, not at write time.

**Why asyncio.Task, not threading.Thread?** The QUADS client uses httpx.AsyncClient (async). No need for a thread. This is different from the etcd watcher and health checker, which use threads because etcd3gw and the health check httpx.Client are synchronous.

### Failure Modes

| Failure | Behavior | Recovery |
|---------|----------|----------|
| QUADS API unreachable | Serve stale cached data. Log warning. | Next successful poll refreshes cache. |
| QUADS API returns error | Same as unreachable -- stale data. | Automatic on next poll. |
| Gateway restart | Cache starts empty. First poll fills it. | Automatic within one poll interval. |
| QUADS returns empty list | Cache becomes empty. Dashboard shows only etcd nodes. | Normal -- QUADS may have no hosts. |

## Settings Addition

```python
class QUADSSettings(BaseModel):
    """QUADS API integration configuration."""

    api_url: str = "http://quads.example.com:8080"
    poll_interval: int = Field(default=60, ge=10)  # seconds
    spare_pool_cloud: str = "cloud01"  # hosts in this cloud are "available"
    token: str = ""  # QUADS v3 auth token, empty = no auth
    enabled: bool = True  # disable QUADS integration entirely
```

Added to root `Settings`:
```python
quads: QUADSSettings = QUADSSettings()
```

Env var example: `INFERENCE_PROXY_QUADS__API_URL=http://quads.lab:8080`

## Lifespan Changes

```python
# In main.py lifespan, after existing setup:

if resolved_settings.quads.enabled:
    quads_http_client = httpx.AsyncClient(...)
    quads_client = QUADSClient(resolved_settings.quads)
    quads_poller = QUADSPoller(quads_client, resolved_settings.quads)
    await quads_poller.start()
    app.state.quads_poller = quads_poller
else:
    app.state.quads_poller = None

# In shutdown:
if app.state.quads_poller:
    await app.state.quads_poller.stop()
    await quads_client.close()
```

## Admin API Changes

The existing `GET /admin/nodes` returns `list[AdminNodeResponse]` with only etcd-registered nodes. This changes to return `list[UnifiedNodeResponse]` with merged QUADS + etcd data.

```python
@admin_router.get("/admin/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
    quads_poller: QUADSPoller | None = Depends(get_quads_poller),
    node_selector: NodeSelector = Depends(get_node_selector),
    cb_registry: CircuitBreakerRegistry = Depends(get_circuit_breaker_registry),
    provisioner: NodeProvisioner = Depends(get_provisioner),
) -> list[UnifiedNodeResponse]:
    quads_hosts = quads_poller.get_hosts() if quads_poller else []
    registry_nodes = registry.get_all()
    # ... merge and return
```

**Backward compatibility note:** The response schema changes from `AdminNodeResponse` to `UnifiedNodeResponse`. Since the only consumer is the dashboard JS, and we are modifying that too, this is not a breaking change for external clients (there are none -- internal network only).

## Dashboard UI Changes

### Remove
- The standalone "Provision Node" form (`<section class="card">` with hostname input)

### Modify
- Node table gains a "Source" column (QUADS / etcd / both)
- Status column shows the unified state (available, assigned, healthy, unhealthy, etc.)
- Actions column shows state-appropriate buttons:
  - Available: "Setup" button (calls `POST /admin/nodes/setup`)
  - Healthy: "Teardown" button (calls `DELETE /admin/nodes/{id}`)
  - Unhealthy: "Teardown" button
  - Provisioning: step progress text, no action buttons
  - Assigned/Broken/Retired: no action buttons

### JS Changes
- Fetch loop already calls `/admin/nodes` -- no new endpoint needed
- Node row rendering function gains state-based action button logic
- Toast notifications already exist from v1.2 -- reuse for setup/teardown feedback

## File Layout

```
inference_proxy/
    quads/                       # NEW package
        __init__.py
        client.py                # QUADSClient (async HTTP to QUADS API)
        poller.py                # QUADSPoller (background cache)
    models/
        quads.py                 # NEW: QUADSHost Pydantic model
        admin.py                 # MODIFY: add UnifiedNodeResponse
    config/
        settings.py              # MODIFY: add QUADSSettings
        dependencies.py          # MODIFY: add get_quads_poller()
    api/
        admin.py                 # MODIFY: merge logic in GET /admin/nodes
        merge.py                 # NEW: merge_node_list() function
    templates/
        dashboard.html           # MODIFY: unified table, inline actions
    main.py                      # MODIFY: create QUADSClient/Poller in lifespan
```

New files: 4 (`client.py`, `poller.py`, `quads.py`, `merge.py`).
Modified files: 5 (`settings.py`, `dependencies.py`, `admin.py`, `dashboard.html`, `main.py`).

## Anti-Patterns to Avoid

### Anti-Pattern: Writing QUADS Data to etcd or NodeRegistry
**What:** Syncing QUADS hosts into etcd so the watcher picks them up.
**Why bad:** etcd is the source of truth for provisioned nodes. Mixing QUADS discovery data into it conflates "what exists" with "what is running." Creates ghost nodes that the health checker tries to probe.
**Instead:** Keep QUADS data in a separate in-memory cache. Merge at read time.

### Anti-Pattern: Calling QUADS API on Every Dashboard Poll
**What:** Making HTTP calls to QUADS inside the `/admin/nodes` handler.
**Why bad:** Couples dashboard latency to QUADS API latency. Multiple dashboard tabs multiply QUADS API load. QUADS outage makes the entire node list fail.
**Instead:** Background poller with cached results. Dashboard reads from cache.

### Anti-Pattern: Making QUADSClient Synchronous
**What:** Using `requests` or sync httpx for QUADS API calls.
**Why bad:** Would need `asyncio.to_thread()` wrapping (like etcd3gw). httpx.AsyncClient is already in the stack and the poller runs on the event loop.
**Instead:** Use httpx.AsyncClient natively. The poller is an asyncio.Task, not a thread.

### Anti-Pattern: Tight Coupling Between Merge Logic and Admin Route
**What:** Putting all merge logic inline in the route handler.
**Why bad:** Merge logic is testable business logic. Inline in the handler makes it harder to test without HTTP fixtures.
**Instead:** Extract `merge_node_list()` into `api/merge.py`. Pure function, easy to unit test.

## Build Order (Suggested Phase Structure)

Based on dependency analysis:

1. **QUADSClient + QUADSHost model + QUADSSettings** -- Foundation. No integration with existing code yet. Fully testable in isolation with httpx mocking.

2. **QUADSPoller + lifespan wiring** -- Depends on QUADSClient. Adds background polling. Dashboard still shows old data at this point.

3. **UnifiedNodeResponse model + merge function** -- Pure data transformation. Testable without HTTP. Depends on QUADSHost existing.

4. **Admin API modification** -- Wire merge into `GET /admin/nodes`. Depends on poller and merge function. Existing dashboard JS breaks at this point (schema changed).

5. **Dashboard UI update** -- Remove setup form, add inline actions, update table rendering for unified response. Fix the JS to match new schema. This is the user-visible deliverable.

Each phase can be tested and committed independently. Phase 4-5 should ship together to avoid a broken dashboard window.

## Sources

- [QUADS API documentation](https://github.com/redhat-performance/quads/blob/master/docs/quads-api.md) - HIGH confidence
- [QUADS server blueprints (hosts)](https://github.com/redhat-performance/quads/blob/latest/src/quads/server/blueprints/hosts.py) - HIGH confidence
- [QUADS server blueprints (available)](https://github.com/redhat-performance/quads/blob/latest/src/quads/server/blueprints/available.py) - HIGH confidence
- [QUADS Python client (quads_api.py)](https://github.com/redhat-performance/quads/blob/latest/src/quads/quads_api.py) - HIGH confidence
- [QUADS 2.2 release (GPU awareness)](https://github.com/redhat-performance/quads/releases/tag/v2.2.4) - MEDIUM confidence
- Existing codebase: `inference_proxy/` source files - HIGH confidence
