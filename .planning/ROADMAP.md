# Roadmap: QUADS LLM Inference Proxy

## Overview

Deliver an OpenAI-compatible gateway that proxies inference requests to vLLM nodes discovered via etcd, with least-connections load balancing, automatic failover, and SSE streaming. The build progresses from project scaffolding through service discovery, core proxying with streaming, intelligent routing, resilience, and finally observability -- each phase delivering a verifiable end-to-end capability.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Project scaffolding, config, data models, and test infrastructure (completed 2026-06-11)
- [x] **Phase 2: Service Discovery** - etcd-based node registry with watch-based live updates (completed 2026-06-11)
- [ ] **Phase 3: Request Proxying and Streaming** - OpenAI-compatible proxy with SSE streaming to vLLM nodes
- [ ] **Phase 4: Intelligent Routing** - Least-connections load balancing with model-aware filtering
- [ ] **Phase 5: Resilience** - Health checks, retry with failover, circuit breaker, graceful shutdown
- [ ] **Phase 6: Observability and Admin** - Structured logging and admin API for operational visibility

## Phase Details

### Phase 1: Foundation

**Goal**: As a developer, I want to start the gateway and run its test suite, so that I have a buildable, runnable, testable project skeleton for all future phases
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: None directly (prerequisite infrastructure)
**Success Criteria** (what must be TRUE):

  1. Running `uv run pytest` executes the test suite and passes
  2. Running `uv run uvicorn` starts a FastAPI application that responds on a port
  3. Pydantic models for node state, gateway config, and OpenAI request/response schemas exist and validate input

**Plans:** 3/3 plans complete

Plans:
**Wave 1**

- [x] 01-01-PLAN.md -- Project scaffold, FastAPI app factory, and passing smoke test

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md -- Configuration settings and node state model with tests
- [x] 01-03-PLAN.md -- OpenAI request/response/streaming/error models with tests

### Phase 2: Service Discovery

**Goal**: Gateway discovers and tracks vLLM nodes registered in etcd in real time
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: DISC-01, DISC-02
**Success Criteria** (what must be TRUE):

  1. Gateway reads vLLM node entries from etcd under a configurable key prefix on startup
  2. When a new node is registered in etcd, the gateway detects it within seconds without restart
  3. When a node is removed from etcd, the gateway stops considering it for routing within seconds

**Plans:** 2/2 plans complete

Plans:
**Wave 1**

- [x] 02-01-PLAN.md -- Serializer, registry, and etcd client wrapper (discovery building blocks)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md -- Watch thread with reconnection and lifespan integration

### Phase 3: Request Proxying and Streaming

**Goal**: Clients can send OpenAI-compatible requests through the gateway and receive responses (including token-by-token streaming) from vLLM nodes
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: PROXY-01, PROXY-02, PROXY-03, PROXY-04, PROXY-05, STRM-01, STRM-02, STRM-03
**Success Criteria** (what must be TRUE):

  1. Client sends a chat completion request to `/v1/chat/completions` and receives a well-formed response from a vLLM node
  2. Client sends a chat completion request with `stream: true` and receives tokens one-by-one via SSE, ending with `data: [DONE]`
  3. Client calls `/v1/models` and sees the list of models available across registered nodes
  4. Client calls `/health` and gets a status indicating gateway availability
  5. When a proxied request fails, the gateway returns an OpenAI-compatible error response with proper HTTP status code and error schema

**Plans:** 2 plans

Plans:
**Wave 1**

- [x] 03-01-PLAN.md -- Proxy infrastructure: ProxyClient, node selector, error mapper, ProxySettings, and unit tests

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 03-02-PLAN.md -- API routes, lifespan integration, and integration tests for all endpoints

### Phase 4: Intelligent Routing

**Goal**: Gateway routes requests to the optimal node based on active connections and requested model
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: DISC-03, LBAL-01, LBAL-02
**Success Criteria** (what must be TRUE):

  1. When multiple nodes host the same model, the gateway sends the request to the node with the fewest active connections
  2. When a client requests a model only available on specific nodes, the gateway routes exclusively to those nodes
  3. When a node is being removed, active connections drain before the node leaves the routing pool

**Plans**: TBD

Plans:

- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

### Phase 5: Resilience

**Goal**: Gateway handles node failures transparently -- health checks detect problems, failed requests retry on another node, and the gateway shuts down cleanly
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: RESL-01, RESL-02, RESL-03, RESL-04
**Success Criteria** (what must be TRUE):

  1. Gateway periodically probes vLLM nodes and stops routing to nodes that fail health checks
  2. When a pre-stream request fails on one node, the gateway retries it on another healthy node without the client seeing the failure
  3. After consecutive failures to a node, a circuit breaker opens and stops sending traffic to it; after recovery, it closes again
  4. When the gateway receives a shutdown signal, it finishes in-flight requests before stopping

**Plans**: TBD

Plans:

- [ ] 05-01: TBD
- [ ] 05-02: TBD
- [ ] 05-03: TBD

### Phase 6: Observability and Admin

**Goal**: Operators can monitor gateway behavior through structured logs and inspect node state through an admin API
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: OBSV-01, DISC-04
**Success Criteria** (what must be TRUE):

  1. Every proxied request produces a structured JSON log entry containing method, path, HTTP status, duration, and target node
  2. Admin can call an API endpoint and see all registered nodes, which models they serve, and their health status

**Plans**: TBD

Plans:

- [ ] 06-01: TBD
- [ ] 06-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete   | 2026-06-11 |
| 2. Service Discovery | 2/2 | Complete   | 2026-06-11 |
| 3. Request Proxying and Streaming | 1/2 | In progress | - |
| 4. Intelligent Routing | 0/3 | Not started | - |
| 5. Resilience | 0/3 | Not started | - |
| 6. Observability and Admin | 0/2 | Not started | - |
