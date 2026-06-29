---
phase: 07-request-metrics-and-admin-api
reviewed: 2026-06-29T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - inference_proxy/api/admin.py
  - inference_proxy/api/routes.py
  - inference_proxy/config/dependencies.py
  - inference_proxy/main.py
  - inference_proxy/models/admin.py
  - inference_proxy/resilience/circuit_breaker.py
  - inference_proxy/routing/request_metrics.py
  - tests/api/test_admin.py
  - tests/conftest.py
  - tests/models/test_admin.py
  - tests/routing/test_request_metrics.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-29
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 7 adds `RequestMetrics` (a thread-safe counter), two admin API endpoints (`/admin/nodes`, `/admin/metrics`), and wires them into the existing proxy routes and lifespan. The new code is small, well-tested at the unit level, and follows existing project patterns. However, the review surfaced two correctness/data-integrity issues, and a few quality concerns.

## Critical Issues

### CR-01: `.env.example` routing section corrupted -- users get broken config template

**File:** `.env.example:14`
**Issue:** The four commented-out routing example lines were replaced with the nonsensical fragment `# INFERENCE_PROXY_ROUTING__ 0`. Anyone using this file as a starting point for configuration gets a broken template with no indication of valid routing keys.
**Fix:**
```dotenv
# Routing (Phase 4+)
# INFERENCE_PROXY_ROUTING__STRATEGY=least_connections
# INFERENCE_PROXY_ROUTING__HEALTH_CHECK_INTERVAL=30
# INFERENCE_PROXY_ROUTING__MAX_RETRIES=3
# INFERENCE_PROXY_ROUTING__TIMEOUT=30
```

### CR-02: `GET /admin/nodes` creates circuit breakers as side effect of a read-only query

**File:** `inference_proxy/api/admin.py:48`
**Issue:** The endpoint calls `cb_registry.get_or_create(n.node_id)` for every node in the registry. `get_or_create` allocates a new `CircuitBreaker` object (with its own `threading.Lock`) for any node that has never received traffic. This means every call to `GET /admin/nodes` silently mutates the `CircuitBreakerRegistry`, creating breaker entries for nodes that were never proxied to. Over time with ephemeral nodes, this leaks `CircuitBreaker` objects that are never cleaned up. More critically, an operational dashboard poll (e.g., every 5 seconds) will continuously create breakers for every new node the moment it registers, before any traffic reaches it -- corrupting the "consecutive failures" semantic (a freshly-created breaker starts at 0 failures / closed state, which is correct, but its mere existence prevents the registry from ever being cleaned up since `CircuitBreakerRegistry.remove()` is only called in one narrow path).
**Fix:** Add a non-creating `get` method to `CircuitBreakerRegistry` and use it in the admin endpoint:
```python
# In CircuitBreakerRegistry:
def get(self, node_id: str) -> CircuitBreaker | None:
    """Return the breaker for *node_id*, or None if absent."""
    with self._lock:
        return self._breakers.get(node_id)

# In admin.py list_nodes:
breaker = cb_registry.get(n.node_id)
circuit_breaker_state = breaker.state if breaker is not None else "closed"
```

## Warnings

### WR-01: `RequestMetrics` counters grow unboundedly with no reset or eviction

**File:** `inference_proxy/routing/request_metrics.py:32-33`
**Issue:** `_per_node` and `_per_model` dicts accumulate entries for every node ID and model name seen across the process lifetime. In environments with ephemeral node IDs (e.g., node-{uuid}), this is a slow, unbounded memory growth with no eviction path. There is no `reset()` or `remove()` method, so entries for deregistered nodes persist forever and are surfaced in `/admin/metrics` responses.
**Fix:** Add a `remove(node_id)` method to clean up per-node entries when nodes are deregistered, and consider adding a `reset()` for operational use. At minimum, document the growth characteristic.

### WR-02: Admin endpoint accesses `node_selector._registry` (private attribute) directly

**File:** `inference_proxy/api/admin.py:39` (also `routes.py:65,84,90,103,109,142,321`)
**Issue:** Multiple files access `node_selector._registry` (underscore-prefixed private attribute) to get the registry directly. The admin endpoint uses `Depends(get_registry)` properly to get the registry, but `routes.py` accesses it through `node_selector._registry` in `_select_error`, `_maybe_remove_drained`, `_scan_drained_nodes`, `_record_failure_and_trip`, and `list_models`. This couples the route handlers to the internal structure of `NodeSelector` and will break silently if the attribute is renamed or encapsulated.
**Fix:** Either expose a public `registry` property on `NodeSelector` (like the existing `tracker` property), or inject the registry separately where needed.

### WR-03: `_stream_completion` records success only on `[DONE]` marker -- silent success gap

**File:** `inference_proxy/api/routes.py:384-391`
**Issue:** The circuit breaker `record_success()` is only called when the SSE stream yields a `[DONE]` event (line 388-391). If the upstream vLLM server closes the connection cleanly after sending all data but without a `[DONE]` marker (non-standard but possible), or if the async generator is cancelled by the client disconnecting, success is never recorded. The breaker's failure count from any prior failures is never cleared, potentially causing a future request to trip the breaker unfairly.
**Fix:** Record success in the `finally` block if no exception was raised, using a flag:
```python
async def event_generator() -> AsyncGenerator[bytes, None]:
    succeeded = False
    try:
        async with aconnect_sse(...) as event_source:
            event_source.response.raise_for_status()
            async for sse in event_source.aiter_sse():
                if sse.data == "[DONE]":
                    yield format_sse_event(data_str="[DONE]")
                    succeeded = True
                    return
                yield format_sse_event(data_str=sse.data)
            # Stream ended without [DONE] -- still a success
            succeeded = True
    except Exception as exc:
        ...
    finally:
        if succeeded:
            circuit_breaker_registry.get_or_create(node.node_id).record_success()
        tracker.decrement(node.node_id)
        ...
```

## Info

### IN-01: `conftest.py` sets `app.state` attributes AND dependency overrides redundantly

**File:** `tests/conftest.py:102-116`
**Issue:** The `app` fixture sets both `application.state.registry = test_registry` (line 103) AND `application.dependency_overrides[get_node_selector] = lambda: node_selector` (line 110). The `get_registry` dependency reads from `request.app.state.registry`, so the state assignment suffices for that path. Meanwhile, `get_node_selector` is overridden but `get_registry` is not. This inconsistency is not a bug (both paths resolve correctly), but it creates confusion about which mechanism is canonical. Future test authors may not understand why some dependencies need overrides and others do not.
**Fix:** For consistency, either override all dependencies via `dependency_overrides` (and skip `app.state` assignments), or document the dual-path approach.

---

_Reviewed: 2026-06-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
