# Phase 4: Intelligent Routing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 04-intelligent-routing
**Areas discussed:** Connection tracking, Model-not-found behavior, Select_node signature, Drain coordination

---

## Connection Tracking

| Option | Description | Selected |
|--------|-------------|----------|
| Separate counter structure | Connection counts in a dedicated structure, not inside NodeRegistry | ✓ |
| Inside the registry | Track connections within the registry | |

**User's choice:** Separate counter structure
**Notes:** Registry stays a pure node store; connection tracking is a routing concern.

| Option | Description | Selected |
|--------|-------------|----------|
| Context manager in routes | Increment/decrement around proxy calls in route handlers | ✓ |
| Inside ProxyClient | Manage counts inside the proxy client | |

**User's choice:** Context manager in routes

| Option | Description | Selected |
|--------|-------------|----------|
| Random | Random selection among tied nodes | ✓ |
| Round-robin among tied | Cycle through tied nodes | |

**User's choice:** Random

---

## Model-Not-Found Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| OpenAI-compatible error | Return 404 with standard OpenAI error schema | ✓ |
| 503 Service Unavailable | Treat as a capacity/routing issue | |

**User's choice:** OpenAI-compatible error (404)

| Option | Description | Selected |
|--------|-------------|----------|
| Exact match only | Client must specify exact model string from etcd | ✓ |
| Prefix match | "llama-3" matches any model starting with "llama-3" | |

**User's choice:** Exact match only

| Option | Description | Selected |
|--------|-------------|----------|
| Different error (503) | 503 "model temporarily unavailable" for unhealthy nodes | ✓ |
| Same 404 error | Treat identically to model-not-found | |

**User's choice:** Different error (503)
**Notes:** Clients can distinguish "model doesn't exist" (404) from "model is down, retry later" (503).

---

## Select_node Signature

| Option | Description | Selected |
|--------|-------------|----------|
| Add parameters | select_node(registry, model, connection_tracker) pure function | |
| Strategy object | NodeSelector class with select(model) method | ✓ |

**User's choice:** Strategy object (NodeSelector class)
**Notes:** Good fit given LBAL-03 (pluggable strategies) is on v2 roadmap.

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI Depends() | Consistent with existing DI pattern | ✓ |
| app.state | Created once in lifespan, accessed directly | |

**User's choice:** FastAPI Depends()

| Option | Description | Selected |
|--------|-------------|----------|
| Optional (default None) | select(model=None) returns any healthy node | ✓ |
| Required | Always require model parameter | |

**User's choice:** Optional (default None)
**Notes:** Backwards-compatible with Phase 3 behavior; useful for non-model-specific operations.

---

## Drain Coordination

| Option | Description | Selected |
|--------|-------------|----------|
| Stop routing + natural drain | Mark DRAINING, let in-flight requests finish on their own | ✓ |
| Stop routing + active drain | Track when connection count hits 0, then remove | |

**User's choice:** Stop routing + natural drain

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-remove at 0 connections | Remove from registry when drain completes | ✓ |
| Keep until etcd deletes | Stay as DRAINING until etcd watch fires DELETE event | |

**User's choice:** Auto-remove at 0 connections

| Option | Description | Selected |
|--------|-------------|----------|
| No timeout | Rely on httpx request timeouts to bound stuck requests | ✓ |
| Configurable timeout | drain_timeout_seconds setting with force-removal | |

**User's choice:** No timeout

| Option | Description | Selected |
|--------|-------------|----------|
| Watcher sets DRAINING | etcd watch callback updates node status directly | |
| Registry drain method | Registry exposes drain(node_id) method | |
| You decide | Claude picks the cleanest approach | ✓ |

**User's choice:** You decide

| Option | Description | Selected |
|--------|-------------|----------|
| Filter out DRAINING | Only show models from HEALTHY nodes in /v1/models | |
| Include DRAINING | Show all models regardless of status | |
| You decide | Claude picks based on client experience | ✓ |

**User's choice:** You decide

---

## Claude's Discretion

- Drain trigger ownership (watcher sets DRAINING vs registry drain method)
- Whether DRAINING nodes appear in /v1/models response
- Internal connection counter implementation details
- Test fixture design

## Deferred Ideas

None — discussion stayed within phase scope
