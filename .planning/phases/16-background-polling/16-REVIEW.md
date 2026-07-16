---
phase: 16-background-polling
reviewed: 2026-07-16T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - inference_proxy/quads/poller.py
  - tests/quads/test_poller.py
  - inference_proxy/config/settings.py
  - inference_proxy/config/dependencies.py
  - inference_proxy/main.py
findings:
  critical: 1
  warning: 3
  info: 0
  total: 4
status: issues_found
---

# Phase 16: Code Review Report

**Reviewed:** 2026-07-16
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

The QUADSPoller is a clean, small class that polls on an interval and caches results. Integration into `main.py` lifespan and dependency injection via `dependencies.py` is straightforward. Settings addition is correct.

The critical defect is that the background poll loop can die permanently from any exception not wrapped in `QUADSConnectionError`, with no recovery and no operator-visible signal. The upstream `QUADSClient._get` method has a gap where `resp.json()` sits outside the `try/except httpx.HTTPError` block, meaning a malformed JSON response kills the poller forever.

## Critical Issues

### CR-01: Unhandled exceptions permanently kill the background poll loop

**File:** `inference_proxy/quads/poller.py:74-79` (with root cause in `inference_proxy/quads/client.py:88`)
**Issue:** `_poll_once` catches only `QUADSConnectionError`. The `_poll_loop` caller has no exception handling at all. Any other exception type kills the `asyncio.Task` silently -- no log, no recovery, polling stops forever while the application continues serving stale data.

This is reachable today: in `client.py:88`, `resp.json()` is outside the `try/except httpx.HTTPError` block. A QUADS server returning `200 OK` with an HTML error page (common behind reverse proxies) raises `json.JSONDecodeError`, which is not an `httpx.HTTPError` and not a `QUADSConnectionError`. Similarly, `get_hosts` accesses `raw["name"]` (client.py:67) which raises `KeyError` if the field is absent.

**Fix:** Broaden the catch in `_poll_once` to `Exception` so the loop survives unexpected errors:
```python
async def _poll_once(self) -> None:
    """Fetch hosts and availability; on error retain cache."""
    try:
        hosts = await self._client.get_hosts()
        available = await self._client.get_available()
    except Exception:
        self._consecutive_failures += 1
        logger.warning(
            "quads_poll_failed",
            consecutive_failures=self._consecutive_failures,
            exc_info=True,
        )
        return

    self._hosts = hosts
    self._available = available
    self._last_sync = datetime.now(tz=UTC)
    self._consecutive_failures = 0
```

Adding `exc_info=True` also fixes the missing diagnostic -- currently even `QUADSConnectionError` failures are logged without the traceback, making debugging harder.

## Warnings

### WR-01: `start()` leaks the previous task if called twice

**File:** `inference_proxy/quads/poller.py:58-60`
**Issue:** `start()` unconditionally creates a new task. If called a second time (e.g., during a reconnect or test), the previous task is orphaned -- it keeps running, keeps polling, and is never cancelled. Two concurrent poll loops will double the request rate to QUADS and race on cache writes.

**Fix:**
```python
def start(self) -> None:
    """Kick off the background poll loop."""
    if self._task is not None and not self._task.done():
        return
    self._task = asyncio.create_task(self._poll_loop())
```

### WR-02: Properties expose mutable internal lists

**File:** `inference_proxy/quads/poller.py:41-46`
**Issue:** `hosts` and `available_hostnames` return direct references to the internal `_hosts` and `_available` lists. Any consumer that appends, clears, or sorts the returned list mutates the poller's cache. Since `_poll_once` replaces the list reference on success (line 94-95, `self._hosts = hosts`), this only corrupts data between polls, but a consumer doing `poller.hosts.clear()` would wipe the cache until the next poll cycle.

**Fix:** Return copies, or use `tuple` internally:
```python
@property
def hosts(self) -> list[QUADSHost]:
    return list(self._hosts)

@property
def available_hostnames(self) -> list[str]:
    return list(self._available)
```

### WR-03: Partial fetch failure discards successfully retrieved data

**File:** `inference_proxy/quads/poller.py:83-91`
**Issue:** `get_hosts()` and `get_available()` are called sequentially under a single try/except. If `get_hosts()` succeeds but `get_available()` raises `QUADSConnectionError`, the successfully fetched host data is thrown away. The cache retains the entirely stale previous snapshot rather than updating what it can.

This is arguably correct (atomic update semantics), but it means a transient failure on one endpoint penalizes both data sets. If atomic updates are intended, add a comment documenting the design choice. If not, consider independent try/except blocks so each data set updates independently.

**Fix (if independent updates are preferred):**
```python
async def _poll_once(self) -> None:
    failed = False
    try:
        hosts = await self._client.get_hosts()
        self._hosts = hosts
    except Exception:
        failed = True
        logger.warning("quads_poll_hosts_failed", exc_info=True)

    try:
        available = await self._client.get_available()
        self._available = available
    except Exception:
        failed = True
        logger.warning("quads_poll_available_failed", exc_info=True)

    if failed:
        self._consecutive_failures += 1
    else:
        self._last_sync = datetime.now(tz=UTC)
        self._consecutive_failures = 0
```

---

_Reviewed: 2026-07-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
