# Phase 22: Power Management Endpoints - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-22
**Phase:** 22-power-management-endpoints
**Areas discussed:** Node identification, Endpoint structure

---

## Node Identification

### What identifier should power endpoints use?

| Option | Description | Selected |
|--------|-------------|----------|
| Hostname (Recommended) | Use bare hostname (e.g., 'server01'). Works for all nodes regardless of provisioning state. Matches RedfishClient API and setup endpoint pattern. BMC resolution via mgmt-{hostname} template. | ✓ |
| Node ID from etcd | Use etcd node ID. Consistent with teardown endpoint, but limits power ops to provisioned nodes only — can't power on an unregistered server. | |
| Either (flexible) | Accept hostname and resolve node_id → hostname when needed. More forgiving but adds lookup logic. | |

**User's choice:** Hostname (Recommended)

### How should the hostname be provided?

| Option | Description | Selected |
|--------|-------------|----------|
| URL path parameter (Recommended) | e.g., /admin/nodes/{hostname}/power — RESTful, bookmarkable, consistent with teardown's path-parameter style. Hostname goes through canonical_hostname() normalization. | ✓ |
| Request body | Like the setup endpoint (POST body with hostname field). More flexible for future batch ops but less RESTful for single-node actions. | |

**User's choice:** URL path parameter (Recommended)

---

## Endpoint Structure

### How should the power endpoints be structured?

| Option | Description | Selected |
|--------|-------------|----------|
| Single resource (Recommended) | GET /admin/nodes/{hostname}/power → returns power state. POST /admin/nodes/{hostname}/power with {"action": "On"} → executes action. Two endpoints, clean REST resource model. Action validated from enum. | ✓ |
| Separate action endpoints | GET /admin/nodes/{hostname}/power/status, POST .../power/on, POST .../power/off, POST .../power/restart. More endpoints but each is self-documenting. Restart needs sub-choice (graceful vs force). | |
| RPC-style namespace | POST /admin/power/{action} with hostname in body. Groups all power ops under /admin/power/ instead of nesting under /nodes/. Simpler routing, less RESTful. | |

**User's choice:** Single resource (Recommended)

### What should the POST power action response include?

| Option | Description | Selected |
|--------|-------------|----------|
| Final state only (Recommended) | Return {"hostname": "x", "power_state": "On"} after polling completes. Synchronous — caller gets definitive result. RedfishClient already polls (up to 60s), so the endpoint blocks until done. | ✓ |
| Action + before/after states | Return {"hostname": "x", "action": "On", "previous_state": "Off", "power_state": "On"}. More informative but slightly more complex response model. | |
| You decide | Let Claude pick the simplest response model that covers the success criteria. | |

**User's choice:** Final state only (Recommended)

### Should the endpoint expose all 4 Redfish actions directly or simplify to operator-friendly names?

| Option | Description | Selected |
|--------|-------------|----------|
| Direct Redfish actions (Recommended) | Expose On, ForceOff, GracefulRestart, ForceRestart as-is. Transparent mapping, no translation layer. Operators are technical users on internal network. | ✓ |
| Simplified aliases | Map to friendlier names: on, off, restart, force-restart. Requires a translation dict in the endpoint. | |

**User's choice:** Direct Redfish actions (Recommended)

---

## Claude's Discretion

- Pydantic request/response model design (PowerActionRequest, PowerStateResponse)
- Error mapping from RedfishError to HTTP status codes
- Whether power endpoints go in existing admin.py or a separate router file

## Deferred Ideas

None — discussion stayed within phase scope
