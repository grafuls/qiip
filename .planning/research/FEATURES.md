# Feature Landscape

**Domain:** QUADS REST API integration for GPU host discovery and unified node management UI
**Researched:** 2026-07-15
**Sources:** QUADS OpenAPI spec (swagger.yaml), server models.py, blueprints (hosts.py, available.py, schedules.py), quads_api.py -- all from github.com/redhat-performance/quads `latest` branch

## QUADS API Reference (Verified Against Source)

**Confidence: HIGH** -- read directly from swagger.yaml and implementation source code.

### Base URL

`https://<quads-host>/api/v3/`

### Authentication

QUADS uses Basic Auth for login, returns a Bearer token. **Read-only GET endpoints are unauthenticated** in the blueprints -- only POST/PATCH/DELETE have `@check_access` decorators. This means host listing and availability checks work without auth for our read-only integration.

### Endpoints We Need

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `GET /hosts/` | GET | List all hosts with filters | No |
| `GET /hosts/{hostname}/` | GET | Single host detail (includes processors, memory, disks, interfaces) | No |
| `GET /hosts/{hostname}/processors/` | GET | Host processor list (CPU + GPU) | No |
| `GET /available/` | GET | List hostnames available for scheduling | No |
| `GET /available/{hostname}/` | GET | Check if specific host is available | No |
| `GET /schedules/current/` | GET | Current active schedules (who owns what) | No |

### Host Response Shape (from models.py `as_dict()`)

```json
{
  "id": 12,
  "name": "host.example.com",
  "model": "R640",
  "host_type": "vendor",
  "build": true,
  "validated": true,
  "switch_config_applied": true,
  "broken": false,
  "retired": false,
  "last_build": "2022-02-02T00:00:00",
  "can_self_schedule": false,
  "created_at": "2022-01-01T00:00:00",
  "rack": "A1",
  "uloc": "U01",
  "blade": null,
  "bootmode": "Uefi",
  "cloud": {
    "id": 1,
    "name": "cloud01",
    "last_redefined": "2022-01-01T00:00:00"
  },
  "default_cloud": {
    "id": 1,
    "name": "cloud01",
    "last_redefined": "2022-01-01T00:00:00"
  },
  "interfaces": [
    {
      "id": 1,
      "name": "em1",
      "bios_id": "nic1",
      "mac_address": "aa:00:bb:11:cc:22",
      "switch_ip": "10.1.1.18",
      "switch_port": "xt-0-0/1",
      "speed": 1000,
      "vendor": "Intel",
      "pxe_boot": true,
      "maintenance": false
    }
  ],
  "disks": [
    {"id": 1, "disk_type": "nvme", "size_gb": 2000, "count": 10}
  ],
  "memory": [
    {"id": 1, "handle": "MMD", "size_gb": 64}
  ],
  "processors": [
    {
      "id": 1,
      "handle": "GPU0",
      "vendor": "NVIDIA",
      "product": "A100",
      "cores": 6912,
      "threads": 6912,
      "processor_type": "GPU"
    }
  ]
}
```

### Host Query Filters (GET /hosts/)

Supported query params (from swagger + `filter_hosts_dict`):
- `name` -- hostname filter
- `model` -- hardware model (e.g., "R640", "DGX")
- `host_type` -- type classification
- `build` -- boolean
- `validated` -- boolean
- `broken` -- boolean
- `retired` -- boolean
- `cloud` -- filter by current cloud assignment name

### Processor Model (GPU Detection)

The `Processor` model has a `processor_type` enum with values `"CPU"` and `"GPU"`. This is the field to filter on for GPU hosts. Each processor record includes:
- `vendor` (e.g., "NVIDIA")
- `product` (e.g., "A100", "H100")
- `cores` / `threads`
- `processor_type` -- the discriminator: `"CPU"` or `"GPU"`

**GPU detection strategy:** Fetch hosts with full detail, check `processors` array for any entry where `processor_type == "GPU"`.

### Availability Endpoint Behavior

`GET /available/` returns **a flat list of hostname strings** (not full host objects):
```json
["host01.example.com", "host02.example.com"]
```

`GET /available/{hostname}/` returns:
```json
{"host01.example.com": "True"}
```

Parameters: `start` (datetime), `end` (datetime), `cloud` (string).
Default start/end is `datetime.now()` if not provided -- effectively "available right now."

### Determining "Idle" Hosts

A host is considered available/idle in QUADS when:
1. It has no active schedule overlapping the queried time range
2. It is not `broken` or `retired`
3. The `default_cloud` concept: hosts return to their default cloud (typically "cloud01" = spare pool) when unscheduled

### Cloud / Assignment Model

- **Cloud**: Named allocation group (e.g., "cloud01" through "cloudNN"). `cloud01` is conventionally the spare pool.
- **Assignment**: Links a cloud to an owner, ticket, description. Has `active`, `provisioned`, `validated` flags.
- **Schedule**: Time-boxed binding of a host to an assignment with `start`/`end` dates.
- A host's `cloud` field shows its current cloud assignment. If `cloud.name == default_cloud.name`, the host is in its spare pool (idle).

## Table Stakes

Features users expect for this milestone. Missing = milestone feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| QUADS API client module | Foundation for everything else -- fetches host data | Low | httpx AsyncClient, 3-4 endpoints. Read-only, no auth needed for GETs. |
| Periodic background polling of QUADS | Keep host list fresh without manual refresh | Low | asyncio task on interval, same pattern as health checker. Store results in memory. |
| Unified node list merging QUADS hosts + etcd nodes | The whole point of v1.3 -- one table showing all systems | Med | Merge logic: match by hostname between QUADS data and etcd-registered nodes. |
| GPU indicator per host | Must show which QUADS hosts have GPUs (only GPU hosts are useful for vLLM) | Low | Filter `processors` for `processor_type == "GPU"`. Show vendor+product. |
| Inline "Setup" button for available hosts | Replace the separate setup form | Low | Button in Actions column, calls existing `POST /admin/nodes/setup`. |
| Inline "Teardown" button for provisioned nodes | Already exists per-node, just ensure it appears in unified list | Low | Already implemented. Carry forward into new table layout. |
| Host availability status from QUADS | Show whether each host is available or currently assigned | Low | Cross-reference `/available/` response with host list. |
| Remove separate setup form | Explicit in milestone scope -- everything through node list | Low | Delete the `<section class="card">` setup form from dashboard.html. |
| QUADS base URL configuration | Configurable QUADS server endpoint | Low | Add `QuadsSettings` to `Settings` with `base_url`, `poll_interval`. |

## Differentiators

Features that set the dashboard apart. Not strictly required but high value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| State-based action buttons | Button changes based on host state: Available->Setup, Healthy->Teardown, Unhealthy->Teardown, Provisioning->disabled | Low | Switch on merged status in JS render function. Already partially done for teardown button disabling. |
| Host hardware summary in table | Show GPU model, memory total, model name inline | Low | Condense processor/memory data into short string like "2x A100, 512GB". |
| Visual status grouping or sorting | Sort nodes by state (available first, then provisioning, healthy, unhealthy) | Low | Client-side sort in JS before rendering. |
| QUADS cloud/assignment info tooltip | Show who owns a scheduled host (owner, ticket) | Med | Requires additional `/schedules/current/` call to get assignment details. |
| Filter/search in node list | Filter by hostname, model, status, GPU type | Low | Client-side JS filter on the already-fetched data. |
| Connection drain indicator | Show "draining (3 active)" during teardown | Low | Already have active_connections data. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Write operations to QUADS API | We are a consumer of QUADS data, not a QUADS admin tool. Writing schedules/assignments would create ownership confusion. | Read-only integration. Setup/teardown is our SSH provisioner, not QUADS scheduling. |
| Full QUADS dashboard clone | QUADS has its own web UI. Duplicating cloud management, schedule editing, etc. is scope creep. | Show only what's needed: host name, availability, GPU info, hardware model. |
| Auth token management for QUADS | GET endpoints don't require auth. Adding login/token refresh adds complexity for no gain. | Use unauthenticated GET requests. If auth is required in deployment, add basic auth header config. |
| Real-time QUADS sync (WebSocket/SSE) | QUADS is a Flask app with no push mechanism. Polling is the only option. | Poll on configurable interval (default 60s). QUADS data changes slowly (schedules change hourly/daily). |
| Auto-provisioning of available hosts | Automatically setting up every idle GPU host is dangerous -- could grab hosts assigned to others. | Manual "Setup" button. Future auto-scaling is explicitly out of scope. |
| Per-host detail page | Over-engineering for an ops dashboard. | Show essential info inline in the table. Tooltip or expandable row for extras if needed. |
| Caching QUADS responses in etcd | Adds write load to etcd for data that's already in memory. | In-memory cache in the QUADS client, refreshed by the background poller. |

## Feature Dependencies

```
QuadsSettings config  -->  QUADS API client module
QUADS API client      -->  Background poller (fetches on interval)
Background poller     -->  In-memory QUADS host cache
QUADS host cache      -->  Unified node list merge logic
etcd NodeRegistry     -->  Unified node list merge logic  (already exists)
Merge logic           -->  Admin API endpoint (GET /admin/nodes returns merged list)
Admin API endpoint    -->  Dashboard JS render (unified table)
Dashboard JS render   -->  Inline action buttons (state-based)
Remove setup form     -->  (independent, do after inline buttons work)
```

## Unified Node List: Merged Data Model

Each row in the unified table represents a host. The merge key is hostname.

```
Source A: QUADS API  -- knows about ALL lab hosts (available or assigned)
Source B: etcd registry -- knows about hosts WE have provisioned with vLLM

Cases:
1. In QUADS, NOT in etcd         -> "available" (or "assigned" if QUADS says scheduled)
2. In QUADS AND in etcd          -> show etcd status (healthy/unhealthy/provisioning/draining)
3. NOT in QUADS, in etcd         -> "provisioned" (manually added, not in QUADS inventory)
4. In QUADS, broken/retired      -> show but grey out, no actions
```

### Suggested Merged Response Shape

```json
{
  "hostname": "host01.example.com",
  "source": "quads+etcd",
  "quads_status": "available",
  "node_status": "healthy",
  "model_hw": "R640",
  "gpu": "2x NVIDIA A100",
  "gpu_count": 2,
  "memory_gb": 512,
  "cloud": "cloud01",
  "vllm_model": "meta-llama/Llama-3-70b",
  "active_connections": 3,
  "circuit_breaker_state": "closed",
  "actions": ["teardown"]
}
```

## Inline Action Button UI Patterns

Standard ops dashboard patterns for inline actions:

| Host State | Available Actions | Button Style |
|------------|-------------------|--------------|
| Available (idle, has GPU) | Setup | Primary (blue/green) |
| Available (idle, no GPU) | -- (greyed out "No GPU") | Disabled |
| Assigned (scheduled to someone else) | -- (disabled, tooltip "Assigned to X") | Disabled |
| Provisioning | -- (disabled, show spinner or "Provisioning...") | Disabled with loading indicator |
| Healthy | Teardown | Danger (red/outline) |
| Unhealthy | Teardown, Retry Setup | Danger + Warning |
| Draining | -- (disabled, "Draining...") | Disabled |
| Broken/Retired | -- (disabled) | Greyed out |

**UI pattern:** Single Actions column with contextual button(s). Disabled buttons show tooltip explaining why. This is the standard pattern in Kubernetes dashboards, Foreman, and MAAS.

## MVP Recommendation

Prioritize:
1. **QUADS client + config + poller** -- foundation, no UI impact yet, testable in isolation
2. **Merge logic + admin API update** -- backend delivers unified list
3. **Dashboard table rewrite** -- render unified list with inline buttons
4. **Remove setup form** -- cleanup after inline buttons work

Defer:
- Cloud/assignment tooltip details: requires extra API call, low priority information
- Filter/search: useful but not blocking, add when table has enough rows to need it
- Host hardware summary beyond GPU: nice to have, model name in QUADS is sufficient

## Complexity Assessment

| Component | Estimated Size | Risk |
|-----------|---------------|------|
| QUADS client module | ~80-120 LOC | Low -- straightforward httpx GET calls |
| Background poller | ~40-60 LOC | Low -- same pattern as health checker thread |
| Merge logic | ~60-100 LOC | Med -- matching hostnames, handling edge cases (case sensitivity, FQDN vs short name) |
| Admin API changes | ~30-50 LOC | Low -- extend existing endpoint |
| Dashboard HTML/JS changes | ~100-150 LOC | Med -- table restructure, state-based buttons |
| Config additions | ~15-20 LOC | Low -- QuadsSettings model |
| Tests | ~200-300 LOC | Med -- mock QUADS responses, test merge logic |

**Total estimate:** ~525-850 new LOC, comparable in scope to v1.1 (dashboard) rather than v1.2 (SSH provisioning).

## Sources

- QUADS swagger.yaml: `src/quads/server/swagger.yaml` in github.com/redhat-performance/quads (OpenAPI 3.0.0, version 3.0.0)
- QUADS models.py: `src/quads/server/models.py` -- SQLAlchemy models defining Host, Processor, Schedule, Assignment, Cloud
- QUADS hosts.py blueprint: `src/quads/server/blueprints/hosts.py` -- confirms GET /hosts/ is unauthenticated
- QUADS available.py blueprint: `src/quads/server/blueprints/available.py` -- returns list of hostname strings
- QUADS quads_api.py: `src/quads/quads_api.py` -- reference Python client using requests (sync)
- QUADS HostDao: `src/quads/server/dao/host.py` -- query filter implementation
- Existing inference-proxy: dashboard.html, dashboard.js, admin.py, models/admin.py, config/settings.py
