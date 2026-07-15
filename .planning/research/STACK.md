# Technology Stack

**Project:** QUADS LLM Inference Proxy -- v1.3 QUADS Integration
**Researched:** 2026-07-15
**Overall Confidence:** HIGH
**Scope:** Stack additions for QUADS REST API integration, periodic host polling, and unified node list UI. Existing stack (FastAPI, httpx, etcd3gw, asyncssh, structlog, Pydantic v2, Jinja2) is validated and NOT re-evaluated here.

## New Dependencies for v1.3

**None.**

Zero new runtime or dev dependencies are needed. The existing stack covers every requirement for this milestone.

## Why No New Dependencies

The QUADS REST API is a standard Flask/JSON REST service. Our existing httpx client handles HTTP calls. Pydantic handles response modeling. The background polling pattern already exists (health checker thread). The dashboard already uses Jinja2 + vanilla JS.

### QUADS API Surface (what we actually call)

The QUADS server exposes a Flask REST API at `/api/v3/`. Key endpoints we need:

| Endpoint | Method | Auth Required | Returns | Purpose |
|----------|--------|---------------|---------|---------|
| `/api/v3/hosts` | GET | No | `list[HostDict]` | List all hosts with model, cloud, processors, broken/retired flags |
| `/api/v3/hosts?model={model}` | GET | No | `list[HostDict]` | Filter hosts by hardware model |
| `/api/v3/hosts/{hostname}` | GET | No | `HostDict` | Single host details |
| `/api/v3/available` | GET | No | `list[str]` | List hostnames currently available (no active schedule) |

All GET endpoints are unauthenticated. Write operations use `@check_access(["admin"])` with Basic/Bearer auth, but we only need reads. This means no auth library needed.

Source: QUADS server source at `github.com/redhat-performance/quads`, specifically:
- `src/quads/server/blueprints/hosts.py` -- GET endpoints have no `@check_access` decorator
- `src/quads/server/blueprints/available.py` -- GET endpoints have no `@check_access` decorator
- `src/quads/server/config.py` -- `API_VERSION = "v3"`

### QUADS Host JSON Shape

From the QUADS `Host` SQLAlchemy model and its `Serialize.as_dict()` method, hosts serialize to:

```json
{
  "id": 1,
  "name": "host01.example.com",
  "model": "R750xa",
  "host_type": "scalelab",
  "build": false,
  "validated": true,
  "broken": false,
  "retired": false,
  "rack": "b01",
  "cloud": {"id": 1, "name": "cloud01", ...},
  "default_cloud": {"id": 2, "name": "cloud02", ...},
  "processors": [
    {"id": 1, "handle": "GPU0", "vendor": "NVIDIA", "product": "A100", "cores": null, "threads": null, "processor_type": "GPU"},
    {"id": 2, "handle": "CPU0", "vendor": "Intel", "product": "Xeon 8380", "cores": 40, "threads": 80, "processor_type": "CPU"}
  ],
  "interfaces": [...],
  "memory": [...],
  "disks": [...],
  "last_build": "Mon, 01 Jul 2026 00:00:00 GMT",
  "created_at": "Mon, 01 Jan 2026 00:00:00 GMT"
}
```

GPU hosts are identified by having at least one processor with `processor_type == "GPU"`.

## Existing Stack Coverage

| v1.3 Requirement | Covered By | How | Confidence |
|-------------------|------------|-----|------------|
| HTTP client for QUADS API | **httpx** (already installed) | `httpx.Client` (sync) for polling thread, same pattern as health checker's `httpx.Client(timeout=5.0)` | HIGH |
| QUADS host data models | **Pydantic v2** (already installed) | New `QuadsHost` model in `models/` -- parse JSON response, extract GPU info, map to unified node state | HIGH |
| Background host polling | **threading.Thread** (stdlib) | Same pattern as `run_health_checker` and `run_watcher` -- dedicated thread with `stop_event.wait(timeout=interval)` | HIGH |
| Configuration (QUADS URL, poll interval) | **pydantic-settings** (already installed) | New `QuadsSettings` sub-model: `base_url`, `poll_interval`, `enabled` | HIGH |
| Unified node list UI | **Jinja2 + vanilla JS** (already installed) | Extend existing dashboard template. New `/admin/quads/hosts` JSON endpoint for JS polling | HIGH |
| Structured logging | **structlog** (already installed) | Log QUADS API calls with host counts, errors, poll timing | HIGH |

### httpx usage: sync Client in thread (matching existing pattern)

The codebase uses `httpx.Client` (synchronous) in background threads already:

```python
# From resilience/health_checker.py line 72:
client = httpx.Client(timeout=_PROBE_TIMEOUT)
```

The QUADS poller follows the exact same pattern -- a `threading.Thread` with a sync `httpx.Client` making periodic GET requests. No new async HTTP client needed; no `asyncio.to_thread()` wrapping needed.

```python
# ponytail: same pattern as health_checker.py
def run_quads_poller(
    quads_client: QuadsClient,
    registry: QuadsHostRegistry,  # or whatever holds the QUADS host list
    stop_event: threading.Event,
    interval: float = 300.0,
) -> None:
    while not stop_event.is_set():
        hosts = quads_client.get_hosts()
        available = quads_client.get_available()
        registry.update(hosts, available)
        if stop_event.wait(timeout=interval):
            break
```

### Why NOT use httpx.AsyncClient for QUADS API

The health checker and etcd watcher both run as background threads with sync clients. The QUADS poller is the same class of work -- periodic polling that runs independently of request handling. Using `httpx.AsyncClient` would require either:
- Running in an asyncio task (which would share the event loop with request handling -- bad for a 5-minute poll cycle), or
- `asyncio.to_thread()` wrapping (pointless complexity when sync httpx works directly)

Sync `httpx.Client` in a thread is the established pattern. Follow it.

## What NOT to Add

| Technology | Why Not |
|------------|---------|
| requests | httpx is already installed and is the modern replacement. Adding requests alongside httpx is redundant. QUADS's own client uses `requests.Session` but we write our own thin client with httpx. |
| aiohttp | httpx already handles HTTP. Adding aiohttp for one API client is waste. |
| quads (pip package) | The QUADS Python package is a CLI/server tool, not an API client library. It pulls in Flask, SQLAlchemy, and dozens of dependencies. We need 2 GET endpoints. Write a 30-line httpx client. |
| APScheduler / schedule | Background polling is `while True: do_thing(); stop_event.wait(interval)`. That's 4 lines. No scheduler library needed. |
| tenacity | Retry logic for QUADS API calls can be a simple try/except with logging. The poller runs every N minutes anyway -- a failed poll just waits for the next cycle. No exponential backoff library needed for "try again in 5 minutes." |
| cachetools / cachelib | The QUADS host list is an in-memory dict/list updated by the poller thread. That IS the cache. No cache library needed. |
| WebSocket / SSE libraries | The dashboard already uses JS polling (`setInterval` + `fetch`). The unified node list follows the same pattern. No real-time push needed for a list that changes every few hours. |

## Integration Points with Existing App

### Settings (pydantic-settings)

```python
class QuadsSettings(BaseModel):
    """QUADS API integration configuration."""
    base_url: str = ""  # Empty = QUADS integration disabled
    poll_interval: int = 300  # 5 minutes between polls
    request_timeout: int = 30
```

Added as `quads: QuadsSettings = QuadsSettings()` in root `Settings`. Env var: `INFERENCE_PROXY_QUADS__BASE_URL=https://quads.example.com/api/v3`.

When `base_url` is empty, QUADS integration is disabled -- the gateway works exactly as v1.2. Feature flag via configuration, no code branching needed beyond "start the poller thread or don't."

### Lifespan (main.py)

The QUADS poller thread starts alongside the existing watcher and health checker threads in the lifespan context manager. Same `stop_event` for coordinated shutdown.

### Dashboard

Extend the existing `/admin/nodes` JSON endpoint (or add a parallel `/admin/quads/hosts` endpoint) that the dashboard JS fetches. The unified node list merges QUADS hosts with etcd-registered nodes client-side or server-side.

## Installation

```bash
# No new dependencies
# Existing pyproject.toml already has everything needed
```

## Key Version Constraints

No new version constraints. All existing constraints from v1.2 remain valid.

| Existing Dependency | Minimum | Still Valid |
|---------------------|---------|-------------|
| httpx >= 0.28 | Stable sync and async client APIs | Yes |
| Pydantic >= 2.10 | Frozen model support, model_copy | Yes |
| pydantic-settings >= 2.14 | Nested env var resolution | Yes |
| structlog >= 26.1.0 | Context variables, async-safe | Yes |
| Jinja2 >= 3.1 | Template rendering for dashboard | Yes |

## Sources

- QUADS GitHub: https://github.com/redhat-performance/quads
- QUADS API client source: `src/quads/quads_api.py` -- shows endpoint patterns (GET /hosts, GET /available)
- QUADS Host model: `src/quads/server/models.py` -- Host columns (name, model, broken, retired, processors with GPU type)
- QUADS blueprints: `src/quads/server/blueprints/hosts.py` -- GET endpoints are unauthenticated
- QUADS available blueprint: `src/quads/server/blueprints/available.py` -- returns list of hostname strings
- QUADS server config: `src/quads/server/config.py` -- `API_VERSION = "v3"`
- QUADS auth decorator: `src/quads/server/blueprints/__init__.py` -- `check_access` only on write endpoints
- QUADS swagger: `src/quads/server/swagger.yaml` -- OpenAPI 3.0.0 spec, base URL `https://quads.example.com/api/v3/`
