# QUADS LLM Inference Proxy

## What This Is

An OpenAI-compatible inference gateway that proxies requests to vLLM nodes on QUADS lab servers with automatic service discovery, least-connections load balancing, circuit breaker resilience, structured observability, and an operations dashboard. Part of a larger system that dynamically provisions LLM inference capacity from unused GPU servers in Scale and Alias labs.

## Core Value

Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## Requirements

### Validated

- [x] OpenAI-compatible API proxy (chat completions, completions, models, health) — v1.0
- [x] etcd-based service discovery for vLLM nodes — v1.0
- [x] Least-connections load balancing across healthy nodes — v1.0
- [x] SSE streaming support for token-by-token responses — v1.0
- [x] Automatic retry on another healthy node when a request fails — v1.0
- [x] Health checking of registered vLLM nodes — v1.0
- [x] Circuit breaker pattern for node failure isolation — v1.0
- [x] Graceful shutdown with in-flight request draining — v1.0
- [x] Structured request logging with target node tracking — v1.0
- [x] Admin API for node fleet inspection — v1.0

### Validated in v1.1

- ✓ Operations dashboard showing node fleet status and request metrics — v1.1
- ✓ Node fleet overview with health state, model, connections, circuit breaker status — v1.1
- ✓ Request metrics (counts per-node, per-model, total) — v1.1
- ✓ Auto-refresh via polling to keep dashboard current — v1.1

### Active

None — planning next milestone.

## Current State

Shipped v1.1 Web UI (2026-07-01). All milestones complete. Next milestone TBD via `/gsd:new-milestone`.

### Out of Scope

- Authentication/authorization — internal network only for v1
- NGINX/SSL termination — separate deployment concern
- Control plane (node provisioning) — next phase after gateway
- Auto-scaling — future work
- Multi-tenancy — future work
- Geographic distribution — future work
- Model caching/optimization — future work

## Context

Shipped v1.1 with 7,618 LOC (Python + HTML/CSS/JS) across 9 phases and 265 tests.
Tech stack: Python 3.12, FastAPI, httpx, etcd3gw, structlog, Pydantic v2, Jinja2.

The system leverages existing QUADS-managed server infrastructure. QUADS tracks server allocations across labs; idle servers with GPUs can be dynamically provisioned to run vLLM containers. The gateway sits between clients and these vLLM nodes, providing a single stable endpoint.

**Architecture:**
- vLLM nodes run in Podman containers on bare metal servers
- Models are served from NFS shared storage (read-only mounts)
- etcd provides service registry — nodes register with endpoint, model info, capabilities
- The gateway is a FastAPI application using httpx for async proxying
- Operations dashboard: Jinja2-rendered HTML with vanilla JS polling for auto-refresh
- Future: control plane (SSH-based provisioning), NGINX (external access), Prometheus metrics

## Constraints

- **Tech stack**: Python, FastAPI, httpx, etcd3 — aligns with existing team expertise and PLAN.md design
- **Network**: Internal network only, no external-facing endpoints in v1
- **Compatibility**: Must implement OpenAI API contract so clients can use standard SDKs
- **Scope**: Code complete and tested locally; deployment is a separate concern

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI for gateway | Async support, OpenAI compatibility, team familiarity | Validated v1.0 |
| etcd3gw for discovery | HTTP gateway client, no grpcio dependency, OpenStack-maintained | Validated v1.0 |
| Least connections balancing | Better utilization than round-robin for variable-length inference requests | Validated v1.0 |
| No auth in v1 | Internal network, simplifies initial implementation | Validated v1.0 |
| Retry on failure | Transparent failover improves reliability without client complexity | Validated v1.0 |
| Circuit breaker pattern | Trip after 3 consecutive failures, auto-recover on health check success | Validated v1.0 |
| Background health checker | Dedicated thread probes /health, marks nodes UNHEALTHY/HEALTHY | Validated v1.0 |
| Graceful shutdown | 503 for new requests (except /health), drain in-flight up to timeout | Validated v1.0 |
| BaseHTTPMiddleware for logging | Simpler than pure ASGI; accepted streaming duration trade-off | Validated v1.0 |
| Separate admin router | /admin namespace for operational endpoints, distinct from proxy routes | Validated v1.0 |
| Jinja2 + vanilla JS for Web UI | No build step, stays in Python ecosystem, minimal dependencies | ✓ Validated v1.1 |
| Polling for auto-refresh | Simple JS interval vs SSE/WebSocket; sufficient for ops dashboard | ✓ Validated v1.1 |
| In-memory counters only | No persistent metrics storage; Prometheus/Grafana is future work | ✓ Validated v1.1 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? Move to Out of Scope with reason
2. Requirements validated? Move to Validated with phase reference
3. New requirements emerged? Add to Active
4. Decisions to log? Add to Key Decisions
5. "What This Is" still accurate? Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-01 after v1.1 milestone*
