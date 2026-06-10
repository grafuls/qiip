# Requirements: QUADS LLM Inference Proxy

**Defined:** 2026-06-10
**Core Value:** Route inference requests to healthy vLLM nodes with automatic failover — the gateway must reliably proxy requests and handle node failures transparently.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Request Proxying

- [ ] **PROXY-01**: Client can send chat completion requests via `/v1/chat/completions` and receive responses from a vLLM node
- [ ] **PROXY-02**: Client can send text completion requests via `/v1/completions` and receive responses from a vLLM node
- [ ] **PROXY-03**: Client can list available models via `/v1/models` with model name, node count, and availability
- [ ] **PROXY-04**: Client can check gateway health via `/health` endpoint
- [ ] **PROXY-05**: Gateway returns OpenAI-compatible error responses with proper status codes and error schema

### Streaming

- [ ] **STRM-01**: Client receives streaming token-by-token responses via SSE for chat completions
- [ ] **STRM-02**: Client receives streaming token-by-token responses via SSE for text completions
- [ ] **STRM-03**: Gateway correctly forwards SSE `data: [DONE]` termination signal from vLLM

### Service Discovery

- [ ] **DISC-01**: Gateway discovers vLLM nodes registered in etcd under a configurable key prefix
- [ ] **DISC-02**: Gateway watches etcd for real-time node additions and removals without restart
- [ ] **DISC-03**: Gateway routes requests only to nodes hosting the requested model (model-aware filtering)
- [ ] **DISC-04**: Admin can view registered nodes, their models, and health status via admin API endpoint

### Load Balancing

- [ ] **LBAL-01**: Gateway routes requests to the node with the fewest active connections (least-connections)
- [ ] **LBAL-02**: Gateway drains active connections before removing a departing node from the routing pool

### Resilience

- [ ] **RESL-01**: Gateway performs periodic health checks against vLLM nodes and marks unhealthy nodes as unavailable
- [ ] **RESL-02**: Gateway retries failed pre-stream requests on another healthy node (does not retry mid-stream)
- [ ] **RESL-03**: Gateway applies per-node circuit breaker that opens after consecutive failures and closes after recovery
- [ ] **RESL-04**: Gateway shuts down gracefully, draining in-flight requests before stopping

### Observability

- [ ] **OBSV-01**: Gateway emits structured JSON logs (structlog) for all requests with method, path, status, duration, and target node

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Observability

- **OBSV-02**: Gateway exposes Prometheus metrics endpoint with request count, latency histograms, and node health gauges
- **OBSV-03**: Gateway logs full request/response bodies at configurable log levels

### Resilience

- **RESL-05**: Gateway performs active readiness probes (lightweight inference) beyond vLLM `/health` to detect GPU faults
- **RESL-06**: Gateway supports configurable per-request timeout values

### Load Balancing

- **LBAL-03**: Gateway supports pluggable routing strategies via Strategy pattern (token-aware, queue-depth-aware)

### Operations

- **OPS-01**: Gateway supports config hot-reload without restart
- **OPS-02**: Gateway supports rate limiting per client or API key

## Out of Scope

| Feature | Reason |
|---------|--------|
| Authentication/authorization | Internal network only for v1; no external access |
| Multi-provider translation | All backends are OpenAI-compatible vLLM; no format translation needed |
| KV cache-aware routing | High complexity, requires deep vLLM integration; defer to future |
| Semantic caching | High complexity, questionable value for internal use |
| Guardrails/content filtering | Not needed for internal developer use |
| Request queuing | Adds latency and complexity; rely on load balancing instead |
| Multi-worker Uvicorn | Single process sufficient for initial scale; connection tracking simpler |
| NGINX/SSL termination | Separate deployment concern, not part of gateway code |
| Control plane (node provisioning) | Next milestone after gateway |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PROXY-01 | — | Pending |
| PROXY-02 | — | Pending |
| PROXY-03 | — | Pending |
| PROXY-04 | — | Pending |
| PROXY-05 | — | Pending |
| STRM-01 | — | Pending |
| STRM-02 | — | Pending |
| STRM-03 | — | Pending |
| DISC-01 | — | Pending |
| DISC-02 | — | Pending |
| DISC-03 | — | Pending |
| DISC-04 | — | Pending |
| LBAL-01 | — | Pending |
| LBAL-02 | — | Pending |
| RESL-01 | — | Pending |
| RESL-02 | — | Pending |
| RESL-03 | — | Pending |
| RESL-04 | — | Pending |
| OBSV-01 | — | Pending |

**Coverage:**
- v1 requirements: 19 total
- Mapped to phases: 0
- Unmapped: 19 ⚠️

---
*Requirements defined: 2026-06-10*
*Last updated: 2026-06-10 after initial definition*
