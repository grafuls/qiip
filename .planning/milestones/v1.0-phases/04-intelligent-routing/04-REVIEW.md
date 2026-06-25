---
phase: 04-intelligent-routing
reviewed: 2026-06-24T12:00:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - inference_proxy/api/errors.py
  - inference_proxy/api/routes.py
  - inference_proxy/config/dependencies.py
  - inference_proxy/discovery/registry.py
  - inference_proxy/discovery/watcher.py
  - inference_proxy/main.py
  - inference_proxy/routing/connection_tracker.py
  - inference_proxy/routing/node_selector.py
  - tests/api/test_errors.py
  - tests/api/test_routes.py
  - tests/conftest.py
  - tests/discovery/test_registry.py
  - tests/discovery/test_watcher.py
  - tests/routing/__init__.py
  - tests/routing/test_connection_tracker.py
  - tests/routing/test_node_selector.py
findings:
  critical: 2
  warning: 5
  info: 2
  total: 9
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-06-24T12:00:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Phase 4 introduces model-aware least-connections routing, a connection tracker, node selection strategy, and drain/auto-removal logic. The core data structures (ConnectionTracker, NodeSelector, NodeRegistry.drain) are well-designed and individually thread-safe. The main concerns are: (1) a logic bug in `_select_error` that returns the wrong error code when nodes exist but all are unhealthy with no model filter, (2) a TOCTOU race between the compound check-then-act in `_maybe_remove_drained` / `_scan_drained_nodes` that could prematurely remove a DRAINING node while a new request is being dispatched to it, and (3) systematic violation of encapsulation by accessing `NodeSelector._registry` from route handlers, which breaks the abstraction boundary.

## Critical Issues

### CR-01: `_select_error` returns wrong error code when all nodes are unhealthy and `model` is `None`

**File:** `inference_proxy/api/routes.py:44-62`
**Issue:** When `model` is `None` (or falsy, though unlikely given Pydantic validation), and nodes ARE registered but all are UNHEALTHY/DRAINING, the function falls through to line 62 and returns `no_nodes_error()` (503 "No inference nodes available"). This is incorrect -- nodes exist, they are just all unhealthy. The error message is misleading and could cause operators to investigate service discovery when the real problem is backend health.

More critically, line 58 (`if model and not node_selector.has_model(model)`) and line 60 (`if model and node_selector.has_model(model)`) are mutually exhaustive when `model` is truthy, so line 62 is ONLY reachable when `model` is falsy AND `all_nodes` is non-empty. The function has no path to return a "nodes exist but all unhealthy" error when model filtering is not in play. While the OpenAI API contract requires `model` as a mandatory field (so `model` will always be a non-empty string coming from Pydantic-validated requests), if `_select_error` is ever called with `model=None` from a different code path, it produces a confusing 503.

**Fix:**
```python
def _select_error(
    model: str | None,
    node_selector: NodeSelector,
) -> tuple[int, Any]:
    all_nodes = node_selector._registry.get_all()
    if not all_nodes:
        return no_nodes_error()
    if model and not node_selector.has_model(model):
        return model_not_found_error(model)
    if model and node_selector.has_model(model):
        return model_unavailable_error(model)
    # Nodes exist but all are unhealthy/draining (model=None case)
    return model_unavailable_error(model or "unknown")
```
Or better: introduce a dedicated `all_nodes_unhealthy_error()` function so the error message is accurate rather than reusing `model_unavailable_error` with a synthetic model name.

### CR-02: TOCTOU race in `_maybe_remove_drained` can remove a node while a concurrent request is being set up for it

**File:** `inference_proxy/api/routes.py:65-82`
**Issue:** `_maybe_remove_drained` performs a multi-step check-then-act that is not atomic: it reads node status from the registry (line 74), reads connection count from the tracker (line 78), and then removes from both (lines 80-81). Between the connection count check (`tracker.get(node.node_id) == 0`) and the `registry.remove()`, a concurrent request handler could call `node_selector.select()`, get a reference to this same DRAINING node (impossible since select() filters to HEALTHY only -- but `_scan_drained_nodes` on line 85 has the same pattern for ALL draining nodes), and then `tracker.increment()` it. The remove then deletes the node from registry and tracker, losing the increment.

The realistic scenario: Two concurrent requests both finish at the same time. Both call `_scan_drained_nodes`. Request A reads `tracker.get("draining-node") == 0`, then Request B's `tracker.increment("new-node")` runs and Request B's `_scan_drained_nodes` also reads `tracker.get("draining-node") == 0`. Both proceed to call `registry.remove` and `tracker.remove`. The double-remove is a no-op (safe), but the underlying race window exists.

The more dangerous variant: A watcher PUT event re-adds a node with the same ID as HEALTHY between the `get()` check and the `remove()`. The remove would then delete a freshly-added HEALTHY node.

**Fix:** The registry and tracker operations need to be coordinated atomically. Options:
1. Add a `remove_if_draining_and_idle(node_id, tracker)` method to `NodeRegistry` that does the check-and-remove under a single lock acquisition.
2. Accept the race as low-probability and document it. (Not recommended for production.)

```python
# Option 1: Add to NodeRegistry
def remove_if_drained(self, node_id: str, tracker: ConnectionTracker) -> bool:
    """Remove node only if DRAINING with 0 active connections."""
    with self._lock:
        node = self._nodes.get(node_id)
        if (
            node is not None
            and node.status == NodeStatus.DRAINING
            and tracker.get(node_id) == 0  # tracker.get is also locked internally
        ):
            del self._nodes[node_id]
            tracker.remove(node_id)
            return True
    return False
```
Note: This still has a cross-lock ordering issue (registry lock, then tracker lock inside `tracker.get`). A cleaner design would use a single shared lock or combine the check into a single data structure.

## Warnings

### WR-01: Systematic encapsulation violation -- route handlers access `NodeSelector._registry` directly

**File:** `inference_proxy/api/routes.py:55,74,80,93,99,193`
**Issue:** The routes module accesses `node_selector._registry` (a private attribute, per Python naming convention) in six places: `_select_error`, `_maybe_remove_drained`, `_scan_drained_nodes`, and `list_models`. This violates the encapsulation of `NodeSelector` and creates tight coupling between the route layer and the registry implementation. If the registry interface changes, routes break. It also violates the Dependency Inversion Principle documented in the project's CLAUDE.md -- the route handlers depend on the concrete `NodeRegistry` internal rather than the `NodeSelector` abstraction.

**Fix:** Expose the needed operations through `NodeSelector`'s public interface:
```python
# Add to NodeSelector
@property
def registry(self) -> NodeRegistry:
    """Return the registry for operations that need direct access."""
    return self._registry

# Or better, add dedicated methods:
def get_all_nodes(self) -> list[Node]:
    return self._registry.get_all()

def remove_drained_nodes(self) -> None:
    """Remove all DRAINING nodes with 0 active connections."""
    ...
```

### WR-02: `_scan_drained_nodes` iterates all nodes on every request completion

**File:** `inference_proxy/api/routes.py:85-101`
**Issue:** `_scan_drained_nodes` is called from both `_proxy_non_streaming` (line 134) and `_stream_completion` (line 260) on every single completed request. It iterates ALL registered nodes, checking each one for DRAINING status with 0 connections. This is called redundantly alongside `_maybe_remove_drained` which already handles the specific node that was just proxied to. The scan exists to catch OTHER draining nodes, but it runs on every request regardless of whether any nodes are draining. With many nodes, this adds unnecessary overhead to every request's critical path. More importantly, the redundant removal logic duplicates the logic in `_maybe_remove_drained`, violating DRY.

**Fix:** Either:
1. Remove `_maybe_remove_drained` entirely and rely solely on `_scan_drained_nodes` (simpler, one code path).
2. Or move drain cleanup to a periodic background task rather than running it on every request completion.

### WR-03: `list_models` endpoint accesses `_registry` directly, bypassing `NodeSelector`

**File:** `inference_proxy/api/routes.py:183-212`
**Issue:** The `/v1/models` endpoint gets `node_selector` via DI but then reaches directly into `node_selector._registry.get_all()` (line 193). This is a specific instance of WR-01 but worth calling out separately because `list_models` does not use `NodeSelector.select()` at all -- it only needs the registry. The handler should either use a public method on `NodeSelector` or depend on `NodeRegistry` directly via its own DI provider (which already exists as `get_registry`).

**Fix:**
```python
@router.get("/v1/models")
async def list_models(
    registry: NodeRegistry = Depends(get_registry),
) -> JSONResponse:
    nodes = registry.get_all()
    ...
```

### WR-04: `conftest.py` app fixture creates a real app with lifespan then overwrites state

**File:** `tests/conftest.py:76-92`
**Issue:** The `app` fixture calls `create_app(settings=test_settings)` which triggers the full lifespan context manager. This lifespan creates a real `EtcdClient`, attempts `_initial_load` from etcd (which will fail in tests since etcd is not running), starts a real watch thread, and creates its own `ConnectionTracker` and `NodeSelector`. These are then immediately overwritten by `application.state.registry = test_registry` etc. The real watch thread continues running in the background during tests (it will reconnect in a loop until the test teardown eventually triggers lifespan shutdown). This is wasteful and could cause flaky tests if the watch thread interacts with the registry before the override happens.

**Fix:** Either:
1. Mock the `EtcdClient` in the test settings/lifespan to prevent real connection attempts.
2. Create the FastAPI app without lifespan for unit tests (use `create_app` with a test-only lifespan that skips etcd).
3. Use `TestClient` context manager to ensure lifespan runs, then override state.

### WR-05: `format_sse_event` return type is `bytes` but `EventSourceResponse` may expect `str`

**File:** `inference_proxy/api/routes.py:240-262`
**Issue:** The `event_generator` is typed as `AsyncGenerator[bytes, None]` and yields `format_sse_event(data_str=...)` which returns `bytes`. `EventSourceResponse` in FastAPI accepts generators yielding either `str` or `bytes`, so this works at runtime. However, the inconsistency between the generator yield type and what `EventSourceResponse` typically documents as accepting (strings/ServerSentEvent objects in examples) means this relies on an implementation detail rather than a documented contract. If FastAPI changes `EventSourceResponse` to enforce str-only yields, this will break silently (no type error, just runtime failure).

**Fix:** Verify this is the intended usage per FastAPI docs for the pinned version. If `format_sse_event` is the documented way to produce pre-formatted bytes for `EventSourceResponse`, document this assumption in a comment. Otherwise, consider yielding `ServerSentEvent` objects.

## Info

### IN-01: Unused import `NodeStatus` in `routes.py` is used only in `list_models`

**File:** `inference_proxy/api/routes.py:34`
**Issue:** `NodeStatus` is imported alongside `Node` from `inference_proxy.models.node`. It is used in `list_models` (line 197) and `_maybe_remove_drained` (line 77). This is fine -- just noting that the import serves two separate concerns (model listing and drain logic) from the same route module, which supports the case for WR-01/WR-03 that these concerns could be separated.

**Fix:** No action needed unless refactoring per WR-01/WR-03.

### IN-02: `ConnectionTracker.decrement` silently floors at zero without logging the anomaly

**File:** `inference_proxy/routing/connection_tracker.py:46-53`
**Issue:** When `decrement` is called for a node with count 0 (indicating a logic bug -- decrement without matching increment), the method silently does nothing except log a normal "connection decremented" debug message. An unmatched decrement is a sign of a bug in the calling code. While the floor-at-zero is correct defensive behavior, the anomaly should be logged at WARNING level so it can be detected in production.

**Fix:**
```python
def decrement(self, node_id: str) -> None:
    with self._lock:
        current = self._counts.get(node_id, 0)
        if current > 0:
            self._counts[node_id] = current - 1
        else:
            logger.warning(
                "decrement called on node with zero connections",
                node_id=node_id,
            )
            return
    logger.debug("connection decremented", node_id=node_id)
```

---

_Reviewed: 2026-06-24T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
