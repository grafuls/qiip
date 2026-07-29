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

### Validated in v1.2

- ✓ SSH-based node setup from gateway (connect, install deps, start vLLM, register) — v1.2
- ✓ Node teardown (stop container, deregister from etcd) — v1.2
- ✓ Admin API for node provisioning (POST setup, DELETE teardown) — v1.2
- ✓ Dashboard UI for setup/teardown operations — v1.2
- ✓ Pre-flight validation (SSH, GPU, disk checks) — v1.2
- ✓ Step-by-step state machine tracking for provisioning — v1.2

### Validated in v1.3

- ✓ QUADS REST API client to discover available GPU hosts — v1.3
- ✓ Periodic background polling to keep QUADS host list fresh — v1.3
- ✓ Unified node list showing all systems (available, provisioned, healthy, unhealthy) — v1.3
- ✓ Inline action buttons per node state (Setup, Teardown, Retry, Cancel, Force Teardown) — v1.3
- ✓ QUADS connection status indicator (connected/stale/unavailable) — v1.3
- ✓ GPU hardware info (vendor, model) visible per host — v1.3

### Validated in v1.4

- ✓ Chat UI page with message input and SSE streaming response display — v1.4 (Phase 19)
- ✓ Model selector showing available healthy models — v1.4 (Phase 19)
- ✓ Conversation history (in-session, not persisted) — v1.4 (Phase 19)

### Validated in v1.4

- ✓ System prompt configuration — v1.4 (Phase 20)
- ✓ Dark/light mode consistency on chat page — v1.4 (Phase 20)

### Validated in v1.5

- ✓ Redfish BMC client with power state query and power actions (On, ForceOff, GracefulRestart, ForceRestart) — v1.5 (Phase 21)
- ✓ Admin API power management endpoints (GET/POST) — v1.5 (Phase 22)
- ✓ Auto-power-on before SSH provisioning for offline servers — v1.5 (Phase 23)
- ✓ Step-level error capture for failed provisioning (actual step name, not exception class) — v1.5 (Phase 24)
- ✓ Dashboard expandable error sub-row for failed nodes — v1.5 (Phase 24)
- ✓ Human-readable Redfish error mapping — v1.5 (Phase 21)

### Validated in v1.7

- [x] HuggingFace API token configuration for gated model access — v1.7 (Phase 30)
- [x] NFS cache directory scanning returning list of downloaded models — v1.7 (Phase 30)
- [x] Admin API: GET /admin/models/catalog — v1.7 (Phase 30)
- [x] Background model download from HuggingFace Hub to NFS — v1.7 (Phase 31)
- [x] Download status tracking (downloading/complete/failed) — v1.7 (Phase 31)
- [x] Admin API: POST /admin/models/download, GET /admin/models/downloads — v1.7 (Phase 31)
- [x] Dashboard download button per recommended model — v1.7 (Phase 32)
- [x] "Already downloaded" badge in recommendations table — v1.7 (Phase 32)
- [x] Live download status in recommendations table with polling — v1.7 (Phase 32)

### Validated in v1.6

- ✓ Install llmfit CLI on target GPU servers during provisioning setup — v1.6 (Phase 26)
- ✓ Operator selects which model to deploy via SetupRequest.model field — v1.6 (Phase 28)

### Validated in v1.8

- [x] Power state display on node detail page (On/Off/Unknown badge) — v1.8 (Phase 33)
- [x] Power action buttons on node detail page (Power On, Force Off, Graceful Restart, Force Restart) — v1.8 (Phase 34)

### Active

- [ ] Model selector dropdown on node detail page for setup (from downloaded catalog)
- [ ] Setup button disabled when no models downloaded

## Current Milestone: v1.9 Model Selection in Node Setup

**Goal:** Operators select which downloaded model to deploy when setting up a node from the node detail page.

**Target features:**
- Model selector dropdown populated from NFS model catalog
- Setup sends selected model in SetupRequest.model
- Setup blocked when no models downloaded

### Out of Scope

- llmfit SSH-based hardware detection and ranked model recommendations — partially built in v1.6, deferred
- Admin API for model fit recommendations — deferred from v1.6
- Authentication/authorization — internal network only for v1
- NGINX/SSL termination — separate deployment concern
- Control plane (full orchestration, auto-scaling) — v1.2 covers setup/teardown only
- Auto-scaling — future work
- Multi-tenancy — future work
- Geographic distribution — future work
- Model caching/optimization — future work

## Context

Shipped v1.8 across 34 phases. Milestones: v1.0 MVP, v1.1 Web UI, v1.2 Node Setup, v1.3 QUADS Integration, v1.4 Chatbot Playground, v1.5 Node Setup Enhancements, v1.6 LLMFit for Best Fit Models, v1.7 HuggingFace Integration, v1.8 Nodes Power Control. Currently building v1.9: model selection from downloaded catalog during node setup.
Tech stack: Python 3.12, FastAPI, httpx, etcd3gw, asyncssh, structlog, Pydantic v2, Jinja2, huggingface-hub.
Codebase: 16,237 LOC, 568 tests.

The system leverages existing QUADS-managed server infrastructure. QUADS tracks server allocations across labs; idle servers with GPUs can be dynamically provisioned to run vLLM containers. The gateway sits between clients and these vLLM nodes, providing a single stable endpoint.

**Architecture:**
- vLLM nodes run in Podman containers on bare metal servers
- Models are served from NFS shared storage (read-only mounts)
- etcd provides service registry — nodes register with endpoint, model info, capabilities
- The gateway is a FastAPI application using httpx for async proxying
- Operations dashboard: Jinja2-rendered HTML with vanilla JS polling for auto-refresh
- v1.2: SSH-based node provisioning and teardown from gateway
- v1.7: HuggingFace model downloads to NFS with dashboard integration
- Future: NGINX (external access), Prometheus metrics, auto-scaling

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
| asyncssh for SSH operations | Native asyncio, no paramiko thread-wrapping needed | ✓ Validated v1.2 |
| Embed provisioning in gateway process | No Celery/task queue — asyncio tasks suffice for stateless proxy | ✓ Validated v1.2 |
| Write to etcd, let watcher propagate | Never mutate NodeRegistry directly from provisioner | ✓ Validated v1.2 |
| Graceful teardown default, force optional | Drain connections before stop; force skips drain | ✓ Validated v1.2 |
| etcd3gw HTTP gateway for QUADS client | Same lib as discovery; avoids adding aiohttp/requests dep | ✓ Validated v1.3 |
| Background polling thread for QUADS | etcd3gw is sync; thread + asyncio.to_thread natural fit | ✓ Validated v1.3 |
| Unified node list merging QUADS + etcd | Single source of truth for operators; hostname-based merge | ✓ Validated v1.3 |
| Data-driven ACTION_CONFIG in dashboard.js | Single dispatch map replaces per-action functions; O/C compliant | ✓ Validated v1.3 |
| Zero new dependencies for v1.3 | httpx, Pydantic, structlog, pydantic-settings cover everything | ✓ Validated v1.3 |
| SSE via fetch+ReadableStream for chat | Unidirectional streaming; no WebSocket overhead needed | ✓ Validated v1.4 |
| In-session conversation only | No persistent storage; cleared on page refresh — simplest viable | ✓ Validated v1.4 |
| System prompt via messages.slice()+unshift | Never mutates conversation array; takes effect on next send | ✓ Validated v1.4 |
| localStorage for system prompt persistence | Same pattern as theme preference; single-user internal tool | ✓ Validated v1.4 |
| CSS custom properties for theming | All new UI uses var(--*) tokens only — zero hardcoded colors | ✓ Validated v1.4 |
| huggingface-hub for HF integration | Single dependency, native cache scanning, gated model support | ✓ Validated v1.7 |
| cache_dir= over local_dir= | HF cache layout compatibility with vLLM model loading | ✓ Validated v1.7 |
| Sync downloads via ThreadPoolExecutor | huggingface-hub is sync; dedicated 2-3 worker thread pool | ✓ Validated v1.7 |
| Independent fetch for catalog/downloads | try/catch per request, not Promise.all — prevents cascade failures | ✓ Validated v1.7 |
| Lazy 4s polling with single-timer guard | Starts on download trigger, auto-stops when no active downloads | ✓ Validated v1.7 |

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
*Last updated: 2026-07-29 after v1.9 milestone start*
