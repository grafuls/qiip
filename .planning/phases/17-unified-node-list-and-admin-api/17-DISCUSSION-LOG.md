# Phase 17: Unified Node List and Admin API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 17-unified-node-list-and-admin-api
**Areas discussed:** Merge strategy, State computation, Duplicate guard, QUADS re-validation

---

## Merge Strategy

### Q1: Where should the QUADS+etcd merge logic live?

| Option | Description | Selected |
|--------|-------------|----------|
| New service class | UnifiedNodeService in a new module, takes QUADSPoller + NodeRegistry + CircuitBreakerRegistry, returns merged list. Clean SRP, testable in isolation. | ✓ |
| Inline in endpoint | Merge directly in the GET /admin/nodes handler. Fewer files but complex endpoint. | |
| You decide | Claude picks simplest testable approach. | |

**User's choice:** New service class

### Q2: Hostname matching between QUADS and etcd?

| Option | Description | Selected |
|--------|-------------|----------|
| canonical_hostname() both | Apply canonical_hostname() to both sources before matching. | |
| Direct string match | Trust QUADS hostnames and etcd node_ids match as-is. | ✓ |
| You decide | Claude picks cheapest/safest. | |

**User's choice:** Direct string match

### Q3: Should etcd nodes without QUADS match appear in unified list?

| Option | Description | Selected |
|--------|-------------|----------|
| Always show etcd nodes | Etcd nodes always appear regardless of QUADS match. GPU info fields null/empty. | |
| Only matched nodes | Only show nodes appearing in at least one source. Orphan etcd nodes hidden. | ✓ |
| You decide | Claude picks safer approach. | |

**User's choice:** Only matched nodes

### Q4: New response model or extend existing?

| Option | Description | Selected |
|--------|-------------|----------|
| New model, replace | Create UnifiedNodeResponse, replace AdminNodeResponse in GET /admin/nodes. | |
| Extend existing | Add optional QUADS fields to AdminNodeResponse. One model, but bigger. | ✓ |
| You decide | Claude picks based on downstream impact. | |

**User's choice:** Extend existing AdminNodeResponse

---

## State Computation

### Q1: How should node state be computed?

| Option | Description | Selected |
|--------|-------------|----------|
| Etcd wins when present | Etcd status takes precedence. QUADS-only + available = "available". QUADS-unavailable + not-in-etcd = skip. | ✓ |
| Explicit state matrix | User defines the full priority matrix. | |
| You decide | Claude derives from requirements and NodeStatus enum. | |

**User's choice:** Etcd wins when present

### Q2: Actions for Provisioning and Draining states?

| Option | Description | Selected |
|--------|-------------|----------|
| No actions while busy | Provisioning and Draining show no action buttons. Wait for completion. | |
| Cancel/force options | Provisioning shows "Cancel", Draining shows "Force teardown". More control. | ✓ |
| You decide | Claude picks based on provisioner capabilities. | |

**User's choice:** Cancel/force options

### Q3: Actions returned as data or derived client-side?

| Option | Description | Selected |
|--------|-------------|----------|
| Server returns actions | API includes 'actions' list per node. Dashboard renders what server says. | ✓ |
| Client derives from state | API returns state only. Dashboard maps state→actions. | |
| You decide | Claude picks for maintainability. | |

**User's choice:** Server returns actions

---

## Duplicate Guard

### Q1: Where should the pending_hosts guard live?

| Option | Description | Selected |
|--------|-------------|----------|
| On NodeProvisioner | Pending set on provisioner class. provision() manages it. | |
| On UnifiedNodeService | New service owns pending set since it already merges data. | |
| In the endpoint | Module-level set in api/admin.py. Simplest. | ✓ |
| You decide | Claude picks best fit. | |

**User's choice:** In the endpoint (module-level set)

### Q2: Block setup for etcd-registered hosts too?

| Option | Description | Selected |
|--------|-------------|----------|
| Block both | 409 for pending OR already in etcd. | |
| Only pending | 409 only for in-flight provisioning. Re-provisioning is operator's decision. | ✓ |
| You decide | Claude picks for safety. | |

**User's choice:** Only pending (in-flight provisioning)

---

## QUADS Re-validation

### Q1: How should setup re-validate availability?

| Option | Description | Selected |
|--------|-------------|----------|
| Live call, fail if down | Call QUADSClient.get_available() directly. QUADS unreachable = 503. | ✓ |
| Live call, fallback to cache | Try live, fall back to poller cache on failure. | |
| You decide | Claude picks from requirement wording. | |

**User's choice:** Live call, fail if down (503)

### Q2: Call QUADSClient directly or through service?

| Option | Description | Selected |
|--------|-------------|----------|
| Direct QUADSClient | Inject QUADSClient into setup endpoint via Depends. Simple one-call validation. | ✓ |
| Through service | UnifiedNodeService gets validate_available() method. Centralizes QUADS interaction. | |
| You decide | Claude picks laziest option. | |

**User's choice:** Direct QUADSClient via Depends

---

## Claude's Discretion

- Module placement for UnifiedNodeService
- Exact field naming for new AdminNodeResponse fields
- Pending set cleanup callback wiring to fire_background task completion
- Whether to add a DI provider for UnifiedNodeService or construct inline

## Deferred Ideas

None — discussion stayed within phase scope.
