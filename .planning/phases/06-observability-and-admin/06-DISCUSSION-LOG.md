# Phase 6: Observability and Admin - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-25
**Phase:** 06-observability-and-admin
**Areas discussed:** Request logging approach, Admin API design

---

## Request Logging Approach

### Q1: How should request logging be implemented?

| Option | Description | Selected |
|--------|-------------|----------|
| Logging middleware | A single middleware wraps every request — captures method, path, status, duration, target node. Follows ShutdownMiddleware pattern. | ✓ |
| Per-route logging | Add structured log calls inside each route handler. More control but easy to forget. | |
| You decide | Let Claude pick the best approach | |

**User's choice:** Logging middleware
**Notes:** None

### Q2: What context should each request log entry include?

| Option | Description | Selected |
|--------|-------------|----------|
| Minimum only | method, path, status_code, duration_ms, target_node. Matches OBSV-01 exactly. | ✓ |
| Add request_id | Include a unique request ID for correlating logs across retries. | |
| Add request_id + model | Request ID plus the model name from the request body. | |

**User's choice:** Minimum only
**Notes:** None

### Q3: Should the middleware log all requests or only proxy requests?

| Option | Description | Selected |
|--------|-------------|----------|
| All requests | Log everything — /health, /v1/models, admin, and proxy routes. Target node is null for non-proxy. | ✓ |
| Proxy routes only | Only log /v1/chat/completions and /v1/completions. | |
| You decide | Let Claude pick based on OBSV-01 wording | |

**User's choice:** All requests
**Notes:** None

### Q4: How should the middleware get the target node?

| Option | Description | Selected |
|--------|-------------|----------|
| request.state | Route handlers set request.state.target_node after node selection. Middleware reads it in the response phase. | ✓ |
| Response header | Route handlers add an X-Target-Node response header. Also visible to clients. | |
| You decide | Let Claude pick the cleanest approach | |

**User's choice:** request.state
**Notes:** None

---

## Admin API Design

### Q1: Where should the admin endpoint live?

| Option | Description | Selected |
|--------|-------------|----------|
| /admin/nodes | Separate /admin namespace. Clear separation from /v1 proxy API. | ✓ |
| /v1/nodes | Under the /v1 namespace alongside other endpoints. | |
| /internal/nodes | Explicit internal namespace. | |

**User's choice:** /admin/nodes
**Notes:** None

### Q2: What data should the admin nodes endpoint return per node?

| Option | Description | Selected |
|--------|-------------|----------|
| Core fields | node_id, endpoint, model, status. Matches DISC-04 exactly. | ✓ |
| Core + operational | Add active_connections and circuit_breaker_open. More useful but couples admin to internals. | |
| You decide | Let Claude pick based on DISC-04 | |

**User's choice:** Core fields
**Notes:** None

### Q3: Separate admin router or same router?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate admin router | New APIRouter in inference_proxy/api/admin.py with prefix='/admin'. Clean SRP separation. | ✓ |
| Same router | Add route to existing routes.py. Simpler but mixes concerns. | |
| You decide | Let Claude pick | |

**User's choice:** Separate admin router
**Notes:** None

### Q4: Include summary stats alongside node list?

| Option | Description | Selected |
|--------|-------------|----------|
| Node list only | Just the array of nodes. Clients derive counts. | ✓ |
| Node list + summary | Add total_nodes, healthy_count, unhealthy_count, models list. | |

**User's choice:** Node list only
**Notes:** None

---

## Claude's Discretion

- Middleware class name and module placement
- Request duration measurement approach
- Log level strategy for different route types
- Admin response Pydantic model design
- Admin router OpenAPI docs inclusion
- Test fixture design

## Deferred Ideas

None — discussion stayed within phase scope
