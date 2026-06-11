# Phase 2: Service Discovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-11
**Phase:** 02-service-discovery
**Areas discussed:** etcd key schema, watch mechanism, node registry design, startup/shutdown behavior, node serialization
**Mode:** --auto (all decisions auto-selected using recommended defaults)

---

## etcd Key Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Per PLAN.md prefix scheme | Keys under `/nodes/{node-id}` with JSON value | ✓ |
| Flat key with embedded metadata | Single key per node with all data in key name | |

**Auto-selected:** Per PLAN.md prefix scheme (recommended, aligns with architecture doc)

---

## Watch Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Background thread | Dedicated `threading.Thread` for long-polling watch | ✓ |
| asyncio.to_thread per watch | Wrap sync watch in asyncio | |
| Polling interval | Periodic fetch instead of watch | |

**Auto-selected:** Background thread (recommended per CLAUDE.md etcd3gw notes)

---

## Node Registry Design

| Option | Description | Selected |
|--------|-------------|----------|
| Thread-safe dict with Lock | `NodeRegistry` class with `dict[str, Node]` + `threading.Lock` | ✓ |
| asyncio-native with Queue | Async registry using asyncio primitives | |
| Concurrent dict wrapper | `concurrent.futures` based approach | |

**Auto-selected:** Thread-safe dict with Lock (recommended — simple, matches threading model)

---

## Startup/Shutdown Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Resilient startup | Start with empty registry if etcd unavailable, log warning | ✓ |
| Fail-fast startup | Crash if etcd is unreachable at startup | |

**Auto-selected:** Resilient startup (recommended — gateway stays responsive)

---

## Node Serialization

| Option | Description | Selected |
|--------|-------------|----------|
| Separate serializer module | `discovery/serializer.py` per Phase 1 D-15 | ✓ |
| Methods on Node model | Serialize/deserialize as Node class methods | |

**Auto-selected:** Separate serializer module (recommended per Phase 1 decision D-15)

---

## Claude's Discretion

- Internal threading and synchronization details
- etcd3gw API usage patterns and error handling specifics
- Test fixture design for mocking etcd operations
- Watch event parsing and dispatch logic

## Deferred Ideas

None — discussion stayed within phase scope
