# Phase 2: Service Discovery - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning

<domain>
## Phase Boundary

etcd-based service discovery for vLLM nodes. The gateway discovers nodes registered in etcd under a configurable key prefix on startup, then watches for real-time additions and removals. This phase delivers the discovery infrastructure — routing logic and health checking are separate phases.

</domain>

<decisions>
## Implementation Decisions

### etcd Key Schema
- **D-01:** Nodes stored under configurable prefix (default `/nodes/`) with node ID as key suffix: `/nodes/{node-id}`. JSON value contains endpoint, model, capabilities, status per PLAN.md etcd data schema.
- **D-02:** Node ID is derived from the etcd key path (last segment after prefix), not stored redundantly in the JSON value.

### Watch Mechanism
- **D-03:** etcd3gw watch runs in a dedicated `threading.Thread` started during FastAPI lifespan startup. Watch is long-polling, so thread-per-watcher is natural.
- **D-04:** Short-lived etcd operations (get, put, lease) wrapped in `asyncio.to_thread()` for non-blocking use in FastAPI handlers and background tasks.
- **D-05:** Initial node list fetch runs synchronously at startup (blocking is acceptable during lifespan init).

### Node Registry
- **D-06:** `NodeRegistry` class in `inference_proxy/discovery/registry.py` holds discovered nodes in a `dict[str, Node]` protected by `threading.Lock`.
- **D-07:** Registry is a singleton created during FastAPI lifespan, stored in `app.state`, and exposed via a FastAPI dependency (`get_registry()`).
- **D-08:** Registry provides thread-safe methods: `add(node)`, `remove(node_id)`, `get_all() -> list[Node]`, `get(node_id) -> Node | None`.

### Startup/Shutdown Behavior
- **D-09:** On startup: fetch all nodes from etcd under the configured prefix, populate registry, then start watch thread. If etcd is unavailable, start with empty registry and log warning — gateway remains responsive but routing will fail until nodes appear.
- **D-10:** On shutdown (via lifespan exit): stop the watch thread cleanly. Use a `threading.Event` to signal the watcher to stop.

### Node Serialization
- **D-11:** Separate serializer module at `inference_proxy/discovery/serializer.py` per D-15 from Phase 1. Functions: `node_from_etcd(key: str, value: bytes) -> Node` and `node_to_etcd(node: Node) -> tuple[str, bytes]`.
- **D-12:** Serializer handles missing/malformed JSON gracefully — logs warning and skips the node rather than crashing the gateway.

### etcd Client Wrapper
- **D-13:** Thin wrapper around etcd3gw client at `inference_proxy/discovery/etcd_client.py` that encapsulates connection configuration and provides typed methods for node operations.
- **D-14:** etcd client created from `EtcdSettings` (endpoints, node_prefix) — no additional config needed beyond what Phase 1 already defined.

### Claude's Discretion
- Internal threading and synchronization details
- etcd3gw API usage patterns and error handling specifics
- Test fixture design for mocking etcd operations
- Watch event parsing and dispatch logic

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `PLAN.md` — Architecture design document with etcd data schema (nodes/{node-id} JSON format), gateway pseudocode, and system workflow diagrams
- `PLAN.md` §Component Details > etcd Service Registry — Node registration JSON schema, watch behavior, lease/TTL patterns

### Project Context
- `.planning/REQUIREMENTS.md` — DISC-01 (discover nodes from etcd), DISC-02 (watch for real-time updates)
- `.planning/ROADMAP.md` — Phase 2 success criteria and dependencies

### Technology Stack
- `CLAUDE.md` §Technology Stack — etcd3gw >=2.5.0 usage notes: sync client, thread-per-watcher pattern, asyncio.to_thread() for non-blocking
- `CLAUDE.md` §Technology Stack > Service Discovery — etcd3gw selection rationale and alternatives considered

### Prior Phase
- `.planning/phases/01-foundation/01-CONTEXT.md` — D-05 through D-08 (config design), D-13 through D-16 (node model design)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `inference_proxy/config/settings.py:EtcdSettings` — Already has `endpoints` and `node_prefix` fields ready for etcd client configuration
- `inference_proxy/models/node.py:Node` — Domain model with all fields needed for registry storage
- `inference_proxy/models/node.py:NodeStatus` — StrEnum for node health state transitions
- `inference_proxy/config/dependencies.py:get_settings` — DI pattern to follow for `get_registry()`

### Established Patterns
- FastAPI lifespan context manager in `main.py` — extend for registry init and watch thread management
- Dependency injection via `Depends()` — use same pattern for registry access
- Pydantic BaseModel for data classes — use for any new config or data types

### Integration Points
- `inference_proxy/main.py:lifespan` — Add registry initialization and watch thread start/stop
- `inference_proxy/config/settings.py:EtcdSettings` — Already configured, consumed by etcd client
- `inference_proxy/discovery/__init__.py` — Empty stub exists, ready for module code

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 2-Service Discovery*
*Context gathered: 2026-06-11*
