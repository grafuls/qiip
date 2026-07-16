# Phase 16: Background Polling - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 16-background-polling
**Areas discussed:** Polling mechanism, Cache scope

---

## Polling Mechanism

### How should the QUADS poller run?

| Option | Description | Selected |
|--------|-------------|----------|
| asyncio.Task (Recommended) | QUADSClient is already async. An asyncio.Task with asyncio.sleep() is the natural fit — no thread overhead, no asyncio.to_thread() wrapping. Starts in lifespan, cancels on shutdown. | ✓ |
| threading.Thread | Matches the existing health_checker.py pattern (threading.Event + stop_event.wait). But QUADSClient is async, so you'd need to run an event loop inside the thread or wrap async calls. | |
| You decide | Let Claude pick based on codebase fit. | |

**User's choice:** asyncio.Task (Recommended)

### Should the poller be a standalone function or a class?

| Option | Description | Selected |
|--------|-------------|----------|
| Class with start/stop | QUADSPoller class holds the cache, staleness state, and the background task. Lifespan calls poller.start() and await poller.stop(). Clean API for Phase 17 to read cached data. | ✓ |
| Standalone function | run_quads_poller() function like run_health_checker(). Cache and staleness state passed in or returned. Flatter, but harder for consumers to access cached data. | |
| You decide | Let Claude pick based on codebase fit. | |

**User's choice:** Class with start/stop

### Where should QUADSPoller live?

| Option | Description | Selected |
|--------|-------------|----------|
| quads/poller.py | New module in existing quads/ package. Keeps polling logic with the QUADS domain. Follows package-per-domain convention (like discovery/watcher.py). | ✓ |
| quads/client.py | Add the poller class to the existing client module. Fewer files, but mixes API client concerns with scheduling/caching. | |
| You decide | Let Claude pick. | |

**User's choice:** quads/poller.py

---

## Cache Scope

### What should each poll cycle fetch from QUADS?

| Option | Description | Selected |
|--------|-------------|----------|
| Both hosts + available (Recommended) | Call get_hosts() and get_available() each cycle. Phase 17 needs host details (GPU info) AND availability status for the unified list. Two fast HTTP GETs per interval — negligible cost. | ✓ |
| Only hosts | Call get_hosts() only. Phase 17 would need to call get_available() on-demand at request time for availability status. Saves one API call per cycle. | |
| You decide | Let Claude pick. | |

**User's choice:** Both hosts + available (Recommended)

### How should cached data be accessed by consumers?

| Option | Description | Selected |
|--------|-------------|----------|
| Properties on QUADSPoller | poller.hosts and poller.available_hostnames return the last-fetched data. Simple, direct. Phase 17 gets the poller from app.state. | ✓ |
| Snapshot method | poller.get_snapshot() returns a frozen dataclass with hosts, available, last_sync, staleness info. One call gets everything. More structured. | |
| You decide | Let Claude pick. | |

**User's choice:** Properties on QUADSPoller

---

## Claude's Discretion

- Staleness thresholds (what defines "stale" vs "unavailable")
- Polling interval config field naming and default value
- Internal error handling within the poll loop
- Whether to do an initial poll at startup before the first interval tick

## Deferred Ideas

None — discussion stayed within phase scope.
