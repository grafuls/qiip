# Architecture Patterns: SSH Node Provisioning (v1.2)

**Domain:** SSH-based node setup/teardown integrated into existing LLM inference gateway
**Researched:** 2026-07-01
**Overall confidence:** HIGH

## Decision: Embedded, Not Separate Service

**Embed provisioning inside the existing FastAPI gateway.** Do not create a separate service.

**Why:**
- The gateway already owns the NodeRegistry, etcd client, and dashboard -- provisioning needs to read/write all three.
- A separate service would need its own etcd client, its own health state, and an IPC mechanism to talk to the gateway. That is more code than embedding.
- The provisioning workload is light (operators set up a handful of nodes per day, not thousands). It does not justify a separate deployment.
- The existing codebase already runs background threads (watcher, health checker) managed via lifespan. Provisioning is one more background concern (asyncio tasks, not threads).

**Ceiling:** If provisioning volume grows to the point where SSH sessions compete with proxy request handling for CPU/memory, extract to a sidecar. That is unlikely for internal QUADS lab usage.

## Recommended Architecture

```
              +--------------------------------------------+
              |             FastAPI Gateway                 |
              |                                            |
              |  +----------+  +----------+  +-----------+ |
              |  | /v1/*    |  | /admin/* |  | /dashboard| |
              |  | (proxy)  |  | (fleet)  |  | (UI)      | |
              |  +----------+  +----+-----+  +-----+-----+ |
              |                     |              |        |
              |         +-----------v--------------v---+    |
              |         |  NEW: /admin/nodes/setup     |    |
              |         |  NEW: /admin/nodes/{id} DEL  |    |
              |         |  NEW: /admin/provisioning/*   |    |
              |         +-----------+------------------+    |
              |                     |                       |
              |         +-----------v------------------+    |
              |         | ProvisioningManager           |    |
              |         | (in-memory task registry)     |    |
              |         +--+---------------------+-----+    |
              |            |                     |          |
              |   +--------v--------+  +---------v-------+ |
              |   | NodeProvisioner |  | NodeTeardown    | |
              |   | (asyncio.Task)  |  | (asyncio.Task)  | |
              |   +--------+--------+  +---------+-------+ |
              |            |                     |          |
              |   +--------v--------+            |          |
              |   | asyncssh conn   |            |          |
              |   | (per-host)      |            |          |
              |   +-----------------+            |          |
              |                                  |          |
              |  +------------+  +----------+    |          |
              |  | NodeRegistry|  | EtcdClient|<--+          |
              |  +------------+  +----------+              |
              +--------------------------------------------+
```

### New Components

| Component | Responsibility | Lives In | Communicates With |
|-----------|---------------|----------|-------------------|
| **ProvisioningManager** | Track in-progress setup/teardown tasks, enforce one-task-per-host | `inference_proxy/provisioning/manager.py` | Admin API, NodeProvisioner, NodeTeardown |
| **NodeProvisioner** | Run SSH setup sequence on a single host (connect, run setup.sh, poll /health, register in etcd) | `inference_proxy/provisioning/provisioner.py` | asyncssh, EtcdClient, NodeRegistry |
| **NodeTeardown** | Stop container, deregister from etcd | `inference_proxy/provisioning/teardown.py` | asyncssh, EtcdClient, NodeRegistry |
| **ProvisioningSettings** | SSH key paths, setup script path, timeouts, container image | `inference_proxy/config/settings.py` (add nested model) | Settings |
| **Provisioning models** | TaskStatus enum, ProvisioningTask Pydantic model, API request/response models | `inference_proxy/models/provisioning.py` | Admin API, ProvisioningManager |
| **Admin provisioning routes** | POST /admin/nodes/setup, DELETE /admin/nodes/{id}, GET /admin/provisioning/tasks | `inference_proxy/api/admin.py` (extend existing router) | ProvisioningManager |

### Modified Components

| Component | Change | Why |
|-----------|--------|-----|
| `settings.py` | Add `ProvisioningSettings` nested model | SSH key path, timeouts, container config |
| `admin.py` | Add 3-4 new endpoints on existing `admin_router` | Same `/admin` namespace, same DI pattern |
| `dependencies.py` | Add `get_provisioning_manager()` | Follow existing DI pattern |
| `main.py` lifespan | Create ProvisioningManager, store in `app.state` | Follow existing lifespan pattern |
| `dashboard.html` | Add setup/teardown buttons, task status display | JS fetches new `/admin/provisioning/*` endpoints |

---

## Handling Long-Running SSH Operations

Node setup can take minutes (driver install, container build, vLLM startup). This is the central design challenge.

### Approach: asyncio.create_task + In-Memory Task Registry

**Why not threads?** The existing codebase uses threads for the watcher and health checker because those wrap a synchronous library (etcd3gw, httpx sync client). AsyncSSH is natively async -- it runs on the asyncio event loop without blocking. No threads needed.

**Why not Celery/RQ?** YAGNI. The gateway provisions a handful of nodes per day on an internal network. Adding Redis + Celery for this is a new deployment dependency for no gain. The in-memory approach is sufficient.

**Why not FastAPI BackgroundTasks?** `BackgroundTasks` is fire-and-forget. We need progress tracking, error capture, and task listing for the dashboard. `asyncio.create_task` gives us handles to track.

### Pattern: ProvisioningManager

```python
class ProvisioningManager:
    """Track provisioning tasks. One per app, created in lifespan."""

    def __init__(self) -> None:
        self._tasks: dict[str, ProvisioningTask] = {}  # task_id -> task state
        self._active_hosts: dict[str, str] = {}  # hostname -> task_id (prevent duplicates)
        self._lock = asyncio.Lock()

    async def start_setup(self, hostname: str, model: str, ...) -> str:
        """Start a setup task. Returns task_id. Raises if host already provisioning."""
        async with self._lock:
            if hostname in self._active_hosts:
                raise ValueError(f"Host {hostname} already has active task")
            task_id = ...  # uuid4
            task = ProvisioningTask(id=task_id, hostname=hostname, status=TaskStatus.PENDING, ...)
            self._tasks[task_id] = task
            self._active_hosts[hostname] = task_id
        # Launch the actual work as a background task
        asyncio.create_task(self._run_setup(task_id, hostname, model, ...))
        return task_id

    async def _run_setup(self, task_id: str, hostname: str, ...) -> None:
        """The actual SSH setup sequence. Updates task status as it progresses."""
        try:
            self._update_status(task_id, TaskStatus.CONNECTING)
            async with asyncssh.connect(hostname, ...) as conn:
                self._update_status(task_id, TaskStatus.RUNNING_SETUP)
                result = await conn.run('/path/to/setup.sh', check=True, timeout=600)
                self._update_status(task_id, TaskStatus.STARTING_VLLM)
                # ... start container, poll health ...
                self._update_status(task_id, TaskStatus.REGISTERING)
                # ... register in etcd ...
                self._update_status(task_id, TaskStatus.COMPLETED)
        except Exception as exc:
            self._update_status(task_id, TaskStatus.FAILED, error=str(exc))
        finally:
            async with self._lock:
                self._active_hosts.pop(hostname, None)

    def get_task(self, task_id: str) -> ProvisioningTask | None: ...
    def get_all_tasks(self) -> list[ProvisioningTask]: ...
```

**Key properties:**
- One task per host enforced (prevents double-provisioning).
- Status transitions are synchronous dict writes -- no race conditions within a single asyncio loop because status updates happen between `await` points.
- Task history persists in memory for the lifetime of the gateway process (sufficient -- operators can see recent tasks on the dashboard).
- `asyncio.Lock` only guards the host-dedup check, not the SSH operations themselves.

### Task Status State Machine

```
PENDING -> CONNECTING -> RUNNING_SETUP -> STARTING_VLLM -> POLLING_HEALTH -> REGISTERING -> COMPLETED
                \            \                \                \                \
                 +----------->+--------------->+--------------->+--------------->+-> FAILED
```

Each status transition is a log event with structlog. The dashboard polls `/admin/provisioning/tasks` to get current status.

---

## SSH Library: asyncssh

**Use asyncssh because it is native asyncio.** The gateway is already async-first. Paramiko would require wrapping every call in `asyncio.to_thread()` -- more code, worse concurrency, and the threading overhead is unnecessary for I/O-bound SSH operations.

| Criterion | asyncssh | paramiko + to_thread |
|-----------|----------|---------------------|
| Async native | Yes | No (wrapped) |
| Streaming output | `create_process` + async readline | Blocking recv() in thread |
| Timeout support | Built-in `timeout=` parameter | Manual threading.Timer |
| Connection pooling | Reuse `SSHClientConnection` | Manual |
| License | EPL 2.0 OR GPL 2.0+ | LGPL |
| Maturity | Active since 2013, v2.24.0 | Active since 2003 |

**Confidence:** HIGH (PyPI-verified API, active maintenance, well-documented)

### SSH Connection Pattern

```python
async with asyncssh.connect(
    hostname,
    username='root',
    client_keys=[settings.provisioning.ssh_key_path],
    known_hosts=None,  # ponytail: internal network only, add known_hosts when external
    connect_timeout=30,
    keepalive_interval=60,
) as conn:
    result = await conn.run(command, check=True, timeout=timeout)
```

**known_hosts=None** is acceptable here because PROJECT.md explicitly states "internal network only, no external-facing endpoints in v1." Add known_hosts validation when/if external access is added.

### Streaming Setup Output for Progress

For long-running setup scripts, use `conn.create_process()` to read stdout line-by-line and update task log:

```python
async with conn.create_process(setup_command) as process:
    async for line in process.stdout:
        task.append_log(line.rstrip())
        # ponytail: log lines stored in-memory, capped at ~1000 lines
```

This lets the dashboard show real-time output from the setup script without waiting for completion.

---

## Integration with Existing Components

### NodeRegistry Integration

After successful setup, the provisioner registers the new node in etcd. The existing watcher thread will pick up the PUT event and add the node to the in-memory NodeRegistry automatically. **Do not add the node to NodeRegistry directly** -- let it flow through etcd so all gateway instances (if scaled) see it.

```
Provisioner completes setup
    |
    v
Provisioner writes to etcd: PUT /nodes/{node-id} -> {endpoint, model, ...}
    |
    v
Existing watcher thread detects PUT event
    |
    v
Watcher calls registry.add(node)
    |
    v
Node is now routable
```

For teardown, the reverse: provisioner DELETEs the etcd key, watcher detects it, calls registry.remove().

### EtcdClient Extension

The existing `EtcdClient` may need `put()` and `delete()` if not already present. These are synchronous (etcd3gw is sync). Wrap in `asyncio.to_thread()` when called from async context, following the existing pattern.

### Dashboard Integration

The dashboard currently polls `/admin/nodes` for the fleet table. Add:

1. **Setup form:** hostname input. POST to `/admin/nodes/setup`.
2. **Task list:** Poll `/admin/provisioning/tasks` alongside the node list. Show status, elapsed time, last log line.
3. **Teardown button:** On each node row, a "Teardown" button that calls DELETE `/admin/nodes/{node_id}`.

Follow the existing pattern: Jinja2 renders the HTML shell, vanilla JS does the fetching and DOM updates. No new frontend dependencies.

### DI Integration

Follow the exact pattern of existing dependencies:

```python
# In dependencies.py
def get_provisioning_manager(request: Request) -> ProvisioningManager:
    return request.app.state.provisioning_manager

# In main.py lifespan
provisioning_manager = ProvisioningManager(etcd_client, settings.provisioning)
app.state.provisioning_manager = provisioning_manager
```

---

## API Design

### POST /admin/nodes/setup

Starts an async provisioning task. Returns immediately with a task ID.

**Request:**
```json
{
    "hostname": "gpu-server-42.lab.example.com"
}
```

**Response (202 Accepted):**
```json
{
    "task_id": "abc-123",
    "status": "pending",
    "hostname": "gpu-server-42.lab.example.com"
}
```

**Why 202?** The operation is not complete when the response is sent. 202 Accepted is the correct HTTP status for async operations.

### GET /admin/provisioning/tasks

Returns all provisioning tasks (recent history).

### GET /admin/provisioning/tasks/{task_id}

Returns a single task with full log output.

### DELETE /admin/nodes/{node_id}

Starts an async teardown task. Returns 202 with task ID.

---

## File Layout

```
inference_proxy/
    provisioning/
        __init__.py
        manager.py          # ProvisioningManager (task registry)
        provisioner.py       # NodeProvisioner (SSH setup logic)
        teardown.py          # NodeTeardown (SSH teardown logic)
    models/
        provisioning.py      # TaskStatus, ProvisioningTask, request/response models
    config/
        settings.py          # Add ProvisioningSettings (modify existing)
        dependencies.py      # Add get_provisioning_manager (modify existing)
    api/
        admin.py             # Add provisioning endpoints (modify existing)
    templates/
        dashboard.html       # Add setup/teardown UI (modify existing)
    main.py                  # Add ProvisioningManager to lifespan (modify existing)
```

New files: 4 (manager, provisioner, teardown, models). Modified files: 5 (settings, dependencies, admin, dashboard, main).

---

## Anti-Patterns to Avoid

### Anti-Pattern: Blocking SSH in the Event Loop
**What:** Using paramiko or subprocess.run() for SSH in an async handler.
**Why bad:** Blocks the entire event loop. All proxy requests stall during SSH operations.
**Instead:** Use asyncssh (native async) or wrap sync calls in asyncio.to_thread().

### Anti-Pattern: Direct NodeRegistry Mutation from Provisioner
**What:** Calling `registry.add(node)` directly after setup completes.
**Why bad:** Bypasses etcd. If the gateway restarts, the node is lost. If multiple gateways exist, only one knows about the node.
**Instead:** Write to etcd, let the watcher propagate to all registries.

### Anti-Pattern: Unbounded Task History
**What:** Keeping all provisioning tasks in memory forever.
**Why bad:** Memory leak over weeks/months of operation.
**Instead:** Cap task history (e.g., keep last 100 tasks, or prune tasks older than 24 hours).

### Anti-Pattern: No Host Deduplication
**What:** Allowing two setup tasks for the same hostname simultaneously.
**Why bad:** Both try to install drivers, start containers, register in etcd. Race conditions, wasted resources, corrupted state.
**Instead:** ProvisioningManager maintains hostname-to-task mapping, rejects duplicates.

---

## Sources

- [AsyncSSH documentation](https://asyncssh.readthedocs.io/) - HIGH confidence
- [AsyncSSH PyPI](https://pypi.org/project/asyncssh/) - HIGH confidence
- [AsyncSSH GitHub](https://github.com/ronf/asyncssh) - HIGH confidence
- [AsyncSSH vs Paramiko comparison](https://elegantnetwork.github.io/posts/comparing-ssh/) - MEDIUM confidence
