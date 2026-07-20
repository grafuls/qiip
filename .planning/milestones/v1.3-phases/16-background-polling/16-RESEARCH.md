# Phase 16: Background Polling - Research

**Researched:** 2026-07-16
**Domain:** asyncio background tasks, in-memory caching, FastAPI lifespan integration
**Confidence:** HIGH

## Summary

This phase builds a `QUADSPoller` class in `inference_proxy/quads/poller.py` that periodically calls the existing `QUADSClient.get_hosts()` and `QUADSClient.get_available()`, caches results in memory, tracks staleness metadata, and integrates with the FastAPI lifespan for clean start/stop.

No new dependencies are required. The entire implementation uses stdlib `asyncio` (Task, sleep, CancelledError), `datetime`, and the already-installed `structlog`. The QUADSClient is already async (httpx.AsyncClient), so `asyncio.create_task()` is the natural scheduling mechanism -- no threads, no `asyncio.to_thread()`.

**Primary recommendation:** Model QUADSPoller as a class with `start()`/`stop()` methods, an internal `asyncio.Task` for the loop, and property accessors for cached data. Follow the health_checker.py error-handling pattern (log + continue) but in async form.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use `asyncio.Task` for the background poller, not `threading.Thread`. QUADSClient is already async (httpx.AsyncClient), so asyncio.Task is the natural fit -- no thread overhead, no asyncio.to_thread() wrapping.
- **D-02:** Poller starts via `asyncio.create_task()` in the lifespan and is cancelled on shutdown (task.cancel() + await).
- **D-03:** QUADSPoller is a class with `start()` and `stop()` methods. Holds the cache, staleness state, and the background task internally. Lifespan calls `poller.start()` / `await poller.stop()`.
- **D-04:** QUADSPoller lives in `inference_proxy/quads/poller.py`. Keeps polling/caching logic separate from the API client (`quads/client.py`). Follows package-per-domain convention (like `discovery/watcher.py`).
- **D-05:** Each poll cycle calls both `get_hosts()` and `get_available()`. Phase 17 needs host details (GPU info) AND availability status for the unified list. Two fast HTTP GETs per interval -- negligible cost.
- **D-06:** Cached data is accessed via properties on QUADSPoller: `poller.hosts` and `poller.available_hostnames`. Phase 17 gets the poller from `app.state`.
- **D-07:** Poller tracks `last_sync` (datetime of last successful poll) and `consecutive_failures` (int, reset on success). Sufficient for DASH-04's connected/stale/unavailable indicator.
- **D-08:** Cached data remains available when QUADS API is unreachable -- stale cache is better than no data. Only the staleness metadata changes on failure.

### Claude's Discretion
- Staleness thresholds (what defines "stale" vs "unavailable") -- can be simple multiples of the poll interval
- Polling interval config field naming and default value in QUADSSettings
- Internal error handling within the poll loop (log + continue pattern)
- Whether to do an initial poll at startup before the first interval tick

### Deferred Ideas (OUT OF SCOPE)
None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUADS-02 | Gateway polls QUADS periodically in the background with configurable interval and in-memory caching | QUADSPoller class with asyncio.Task loop, `poll_interval` field on QUADSSettings, property accessors for cached hosts/available data, staleness tracking via `last_sync`/`consecutive_failures` |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Periodic QUADS polling | API / Backend (asyncio Task) | -- | Background task in the gateway process, no client involvement |
| Host data caching | API / Backend (in-memory) | -- | Simple Python attributes on the poller instance |
| Staleness tracking | API / Backend | -- | `last_sync` datetime + `consecutive_failures` counter |
| Lifespan integration | API / Backend (FastAPI) | -- | start/stop in the existing lifespan context manager |
| Configuration | API / Backend (pydantic-settings) | -- | `poll_interval` field on existing QUADSSettings |

## Standard Stack

### Core
No new libraries. Everything needed is already installed or in stdlib.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio (stdlib) | Python 3.12 | Task scheduling, sleep, cancellation | Built-in. `create_task()` + `task.cancel()` is the standard pattern for background async work. [VERIFIED: stdlib] |
| datetime (stdlib) | Python 3.12 | Staleness tracking (`last_sync` timestamp) | Built-in. `datetime.now(UTC)` for timezone-aware timestamps. [VERIFIED: stdlib] |
| structlog | >=26.1.0 (installed) | Logging within poll loop | Already used throughout codebase. Bound logger pattern. [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| QUADSClient | (local) | The actual HTTP calls to QUADS API | Injected into QUADSPoller constructor. [VERIFIED: codebase quads/client.py] |
| pydantic-settings | >=2.14 (installed) | `poll_interval` config field | Add field to existing QUADSSettings. [VERIFIED: codebase config/settings.py] |

### Alternatives Considered
None. All decisions are locked. asyncio.Task is the only sensible choice when the wrapped client is already async.

## Package Legitimacy Audit

No new packages to install. Phase uses only stdlib and already-installed dependencies.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    FastAPI Lifespan
                         |
                    poller.start()
                         |
                         v
              +--------------------+
              |   QUADSPoller      |
              |                    |
              |  _task (asyncio)   |----> asyncio.create_task(_poll_loop)
              |  _client (injected)|                |
              |  _interval (config)|                v
              |                    |     +---------------------+
              |  Cache:            |     |   _poll_loop()      |
              |   _hosts: list     |<----|   while True:       |
              |   _available: list |     |     _poll_once()    |
              |                    |     |     asyncio.sleep()  |
              |  Staleness:        |     +---------------------+
              |   last_sync: dt    |                |
              |   consec_failures  |                v
              +--------------------+     QUADSClient.get_hosts()
                    |                    QUADSClient.get_available()
                    |
              poller.stop()  <-- task.cancel() + await
```

### Recommended Project Structure
```
inference_proxy/
  quads/
    __init__.py       # (exists, empty)
    client.py         # (exists) QUADSClient
    poller.py         # (NEW) QUADSPoller
  models/
    quads.py          # (exists) QUADSHost
  config/
    settings.py       # (MODIFY) add poll_interval to QUADSSettings
    dependencies.py   # (MODIFY) add get_quads_poller() DI provider
  main.py             # (MODIFY) create/start/stop poller in lifespan
tests/
  quads/
    test_client.py    # (exists)
    test_poller.py    # (NEW) QUADSPoller unit tests
```

### Pattern 1: Async Background Poller (asyncio.Task)
**What:** A class that owns an asyncio.Task running a poll-sleep loop, with cache state accessible via properties.
**When to use:** When the wrapped client is already async and the loop runs in the same event loop as the ASGI server.
**Example:**
```python
# Source: stdlib asyncio + project health_checker.py pattern (adapted to async)
import asyncio
from datetime import UTC, datetime

import structlog

from inference_proxy.models.quads import QUADSHost
from inference_proxy.quads.client import QUADSClient, QUADSConnectionError

logger = structlog.get_logger()


class QUADSPoller:
    def __init__(self, client: QUADSClient, interval: float = 300.0) -> None:
        self._client = client
        self._interval = interval
        self._task: asyncio.Task[None] | None = None
        self._hosts: list[QUADSHost] = []
        self._available: list[str] = []
        self._last_sync: datetime | None = None
        self._consecutive_failures: int = 0

    @property
    def hosts(self) -> list[QUADSHost]:
        return self._hosts

    @property
    def available_hostnames(self) -> list[str]:
        return self._available

    @property
    def last_sync(self) -> datetime | None:
        return self._last_sync

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        await self._poll_once()
        while True:
            await asyncio.sleep(self._interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        try:
            hosts = await self._client.get_hosts()
            available = await self._client.get_available()
            self._hosts = hosts
            self._available = available
            self._last_sync = datetime.now(UTC)
            self._consecutive_failures = 0
            logger.info("quads_poll_succeeded", host_count=len(hosts), available_count=len(available))
        except QUADSConnectionError:
            self._consecutive_failures += 1
            logger.warning("quads_poll_failed", consecutive_failures=self._consecutive_failures)
```
[VERIFIED: codebase patterns from health_checker.py + stdlib asyncio]

### Pattern 2: Lifespan Integration
**What:** Creating and wiring the poller in the existing FastAPI lifespan.
**When to use:** At app startup/shutdown.
**Example:**
```python
# In main.py lifespan, after QUADSClient creation (lines 169-179):
if resolved_settings.quads.base_url is not None:
    quads_http = httpx.AsyncClient(...)
    quads_client = QUADSClient(quads_http, resolved_settings.quads.base_url)
    app.state.quads_client = quads_client

    poller = QUADSPoller(quads_client, resolved_settings.quads.poll_interval)
    poller.start()
    app.state.quads_poller = poller
else:
    app.state.quads_client = None
    app.state.quads_poller = None

# On shutdown (before quads_http.aclose()):
if app.state.quads_poller is not None:
    await app.state.quads_poller.stop()
```
[VERIFIED: codebase main.py lifespan pattern]

### Pattern 3: Config Field Addition
**What:** Adding `poll_interval` to existing QUADSSettings.
**Example:**
```python
# In config/settings.py
class QUADSSettings(BaseModel):
    base_url: str | None = None
    timeout: float = 10.0
    poll_interval: float = 300.0  # 5 minutes default
```
Env var: `INFERENCE_PROXY_QUADS__POLL_INTERVAL=120`
[VERIFIED: codebase settings.py pattern]

### Pattern 4: DI Provider
**What:** FastAPI dependency for route handlers to access the poller.
**Example:**
```python
# In config/dependencies.py
from inference_proxy.quads.poller import QUADSPoller

def get_quads_poller(request: Request) -> QUADSPoller | None:
    return request.app.state.quads_poller
```
[VERIFIED: codebase dependencies.py pattern]

### Anti-Patterns to Avoid
- **Threading for an async client:** QUADSClient uses httpx.AsyncClient. Wrapping it in a thread defeats the purpose. Use asyncio.Task. [VERIFIED: D-01]
- **Blocking the event loop:** Never use `time.sleep()` in async code. Use `asyncio.sleep()`. [VERIFIED: stdlib asyncio]
- **Swallowing CancelledError in the loop:** The poll loop must let `CancelledError` propagate for clean shutdown. Only catch it in `stop()`. [VERIFIED: stdlib asyncio]
- **Re-raising on poll failure:** The poll loop must catch `QUADSConnectionError` and continue. Stale cache is always better than no cache. [VERIFIED: D-08]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Task scheduling | Custom timer/scheduler | `asyncio.create_task()` + `asyncio.sleep()` | stdlib, battle-tested, cancellation-aware |
| Timestamps | Manual epoch math | `datetime.now(UTC)` | Timezone-aware, readable, stdlib |
| Structured logging | print/f-string logging | `structlog.get_logger()` | Already used everywhere in the codebase |

## Common Pitfalls

### Pitfall 1: CancelledError Handling
**What goes wrong:** Catching broad exceptions inside `_poll_once` that accidentally suppress `asyncio.CancelledError` raised during an httpx call mid-cancellation.
**Why it happens:** If the task is cancelled while httpx is mid-request, the CancelledError may propagate through httpx internals. Catching `Exception` broadly could swallow it in Python < 3.9, but even in 3.12 where CancelledError is a BaseException, some httpx internals wrap errors.
**How to avoid:** Catch only `QUADSConnectionError` in `_poll_once`. Let everything else propagate.
**Warning signs:** Shutdown hangs or takes the full graceful_shutdown_timeout.

### Pitfall 2: Initial Poll Timing
**What goes wrong:** If the poller sleeps first and then polls, Phase 17's unified list is empty for the first N seconds after startup.
**Why it happens:** The natural loop is `while True: sleep(); poll()` but that delays the first data availability.
**How to avoid:** Poll once immediately at the start of the loop: `poll_once(); while True: sleep(); poll_once()`.
**Warning signs:** Dashboard shows empty QUADS data for one interval after startup.

### Pitfall 3: Task Cleanup on Stop
**What goes wrong:** If `stop()` only calls `task.cancel()` without awaiting, the task lingers and Python warns "Task was destroyed but it is pending."
**Why it happens:** `task.cancel()` requests cancellation but does not wait for it.
**How to avoid:** Always `await self._task` after `cancel()`, wrapped in `try/except asyncio.CancelledError`.
**Warning signs:** RuntimeWarning about pending tasks in logs at shutdown.

### Pitfall 4: Testing Async Poll Loops
**What goes wrong:** Tests hang waiting for `asyncio.sleep()` in the infinite poll loop.
**Why it happens:** The poll loop runs forever until cancelled. Tests need to control the loop.
**How to avoid:** Test `_poll_once()` directly for cache/staleness behavior. Test `start()`/`stop()` lifecycle with a very short interval (0.01s). Mock the QUADSClient with `AsyncMock`.
**Warning signs:** Tests taking >1s or timing out.

### Pitfall 5: Thread Safety of Cache Reads
**What goes wrong:** Concern about concurrent reads from request handlers while the poller writes.
**Why it happens:** Multiple async coroutines may read `poller.hosts` while `_poll_once` updates it.
**How to avoid:** This is safe without locks. The poller replaces the entire list reference atomically (`self._hosts = hosts`). Python's GIL ensures reference assignment is atomic. QUADSHost objects are frozen Pydantic models. Readers get either the old or new list, never a partially-updated one.
**Warning signs:** None expected -- this is a non-issue but worth documenting to prevent someone from adding unnecessary locking.

## Code Examples

### Testing QUADSPoller (recommended pattern)
```python
# Source: project test patterns from tests/quads/test_client.py
import asyncio
from unittest.mock import AsyncMock

from inference_proxy.models.quads import QUADSHost
from inference_proxy.quads.client import QUADSConnectionError
from inference_proxy.quads.poller import QUADSPoller


class TestPollOnce:
    async def test_successful_poll_caches_data(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_hosts.return_value = [
            QUADSHost(hostname="h1", gpu_vendor="NVIDIA", gpu_model="A100", gpu_count=4)
        ]
        mock_client.get_available.return_value = ["h1"]

        poller = QUADSPoller(mock_client, interval=300.0)
        await poller._poll_once()

        assert len(poller.hosts) == 1
        assert poller.hosts[0].hostname == "h1"
        assert poller.available_hostnames == ["h1"]
        assert poller.last_sync is not None
        assert poller.consecutive_failures == 0

    async def test_failed_poll_preserves_stale_cache(self) -> None:
        mock_client = AsyncMock()
        host = QUADSHost(hostname="h1", gpu_vendor="NVIDIA", gpu_model="A100", gpu_count=4)
        mock_client.get_hosts.return_value = [host]
        mock_client.get_available.return_value = ["h1"]

        poller = QUADSPoller(mock_client, interval=300.0)
        await poller._poll_once()  # First poll succeeds

        mock_client.get_hosts.side_effect = QUADSConnectionError("down")
        await poller._poll_once()  # Second poll fails

        assert len(poller.hosts) == 1  # Stale data preserved
        assert poller.consecutive_failures == 1


class TestLifecycle:
    async def test_start_stop(self) -> None:
        mock_client = AsyncMock()
        mock_client.get_hosts.return_value = []
        mock_client.get_available.return_value = []

        poller = QUADSPoller(mock_client, interval=0.01)
        poller.start()
        await asyncio.sleep(0.05)
        await poller.stop()

        assert mock_client.get_hosts.call_count >= 1
```
[VERIFIED: project test patterns from tests/quads/test_client.py and tests/resilience/test_health_checker.py]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `threading.Thread` + `stop_event.wait(interval)` | `asyncio.create_task()` + `asyncio.sleep()` | When wrapping async clients | Simpler cancellation, no GIL concerns, no thread-to-async bridging |
| `CancelledError(Exception)` | `CancelledError(BaseException)` | Python 3.9 | `except Exception` no longer catches CancelledError -- desired behavior for clean shutdown |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 300s (5 min) is a reasonable default poll interval | Architecture Patterns / Pattern 3 | Low -- configurable via env var, easy to change |
| A2 | Initial poll should run before first sleep interval | Common Pitfalls / Pitfall 2 | Low -- if startup latency matters, can defer to first interval tick |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 (auto mode) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/quads/test_poller.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUADS-02a | Successful poll caches hosts and available | unit | `uv run pytest tests/quads/test_poller.py -x -k successful` | Wave 0 |
| QUADS-02b | Failed poll preserves stale cache | unit | `uv run pytest tests/quads/test_poller.py -x -k stale` | Wave 0 |
| QUADS-02c | Failed poll increments consecutive_failures, success resets | unit | `uv run pytest tests/quads/test_poller.py -x -k failures` | Wave 0 |
| QUADS-02d | Poller starts and stops cleanly | unit | `uv run pytest tests/quads/test_poller.py -x -k lifecycle` | Wave 0 |
| QUADS-02e | poll_interval is configurable via QUADSSettings | unit | `uv run pytest tests/config/ -x -k quads` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/quads/test_poller.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/quads/test_poller.py` -- covers QUADS-02 (all sub-requirements)

## Security Domain

No new attack surface. The poller makes outbound HTTP GETs to an internal QUADS API over the existing QUADSClient. No user input reaches the poller. No new endpoints exposed.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | -- |
| V3 Session Management | no | -- |
| V4 Access Control | no | -- |
| V5 Input Validation | no | Data comes from trusted internal QUADS API via existing QUADSClient |
| V6 Cryptography | no | -- |

## Sources

### Primary (HIGH confidence)
- `inference_proxy/quads/client.py` -- QUADSClient API (get_hosts, get_available, QUADSConnectionError)
- `inference_proxy/models/quads.py` -- QUADSHost frozen Pydantic model
- `inference_proxy/resilience/health_checker.py` -- existing background poller pattern (threading-based reference)
- `inference_proxy/main.py` -- lifespan startup/shutdown, app.state registration (lines 169-179)
- `inference_proxy/config/settings.py` -- QUADSSettings class, nested BaseModel pattern
- `inference_proxy/config/dependencies.py` -- DI provider pattern (get_quads_client example)
- Python 3.12 asyncio stdlib -- Task, create_task, CancelledError semantics

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib + already-installed packages
- Architecture: HIGH -- direct adaptation of existing health_checker.py pattern to async
- Pitfalls: HIGH -- well-documented asyncio patterns, verified against Python 3.12 behavior

**Research date:** 2026-07-16
**Valid until:** 2026-08-16 (stable -- no moving parts, all stdlib)
