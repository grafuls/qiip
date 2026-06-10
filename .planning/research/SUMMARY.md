# Research Summary: QUADS LLM Inference Proxy

## Executive Summary

This project is an internal LLM inference gateway providing an OpenAI-compatible API in front of vLLM nodes on repurposed GPU servers managed by QUADS. The recommended approach is a centralized proxy built on FastAPI (native async and SSE), httpx (streaming HTTP client), and etcd3gw (service registry). The architecture decomposes into five SOLID-compliant components: API Layer, Node Registry, Router, Proxy Core, and Health Checker. The critical path is SSE streaming correctness — 80% of production issues stem from buffering, connection leaks, and retry failures.

Primary risks are: (1) response buffering destroying streaming UX, (2) connection leaks from unclosed responses, (3) vLLM `/health` only checking process liveness not GPU readiness, and (4) retry amplification. All mitigated via architectural choices: `httpx.stream()` with async generators, active readiness probes, and pre-stream-only retry.

## Stack

- **Python 3.12**, **FastAPI >=0.135** (built-in SSE via `EventSourceResponse`), **httpx >=0.28** (async streaming), **Pydantic v2 >=2.10**
- **etcd3gw >=2.5.0** (OpenStack-maintained, HTTP gateway, no grpcio dependency) with `asyncio.to_thread()` for async compatibility
- **httpx-sse >=0.4.3** for consuming SSE events from upstream vLLM backends
- **uv** for package management (replaces pip/poetry)
- **Dev tooling:** ruff (lint+format), mypy >=2.1, pytest-asyncio + pytest-httpx, structlog >=26.1.0
- **etcd client note:** Architecture research recommends `aetcd`/`etcetra` for native async; Stack research recommends `etcd3gw` with sync wrapper. Both viable — spike to decide.

## Table Stakes Features

All confirmed across LiteLLM, Portkey, Bifrost, OpenRouter, vLLM Router:
- OpenAI-compatible API surface (`/v1/chat/completions`, `/v1/completions`, `/v1/models`, `/health`)
- SSE streaming for token-by-token responses
- Health checking of backend nodes
- Retry on failure with failover
- Load balancing (least-connections)
- Service discovery (etcd)
- Proper error formatting (OpenAI error schema)

## Key Pitfalls

1. **SSE streaming is highest-risk.** Three buffering layers (httpx, FastAPI, NGINX) can each destroy streaming. Must use `httpx.AsyncClient.stream()` with async generators and correct `Content-Type`.
2. **vLLM `/health` is insufficient.** Only checks process liveness, not GPU readiness. Needs inference-based readiness probes.
3. **Least-connections is flawed for LLM workloads.** One 4k-token generation saturates a GPU but counts as "one connection." Must use Strategy pattern for future extensibility.
4. **Retry only pre-stream failures.** Mid-stream retries garble output. Budget caps and circuit breakers prevent storms.
5. **`python-etcd3` has async/sync gRPC conflicts.** Can hang FastAPI event loop. `etcd3gw` (HTTP gateway) avoids this.

## Architecture

Six internal components with clear boundaries:
1. **API Layer** — FastAPI routes, request validation, OpenAI schema
2. **Node Registry** — etcd watch, node state management
3. **Router** — Strategy pattern, least-connections default
4. **Proxy Core** — httpx streaming proxy, SSE forwarding
5. **Health Checker** — Background probes, node status updates
6. **Connection Tracker** — Active request counting for load balancing

Build order: Config/models → Node Registry → Proxy Core → API Layer → Resilience

## Suggested Phase Structure

1. **Core Gateway** — Streaming proxy + etcd discovery. Validates highest-risk components first.
2. **Reliability & Routing** — Least-connections balancing, retry with circuit breaker, readiness probes.
3. **Observability & Operations** — Prometheus metrics, structured logging, admin API.
4. **Production Hardening** — Graceful shutdown, connection draining, config hot-reload.

## Confidence

| Area | Level | Notes |
|------|-------|-------|
| Stack | HIGH | All deps verified via PyPI/official docs; etcd client MEDIUM |
| Features | HIGH | Cross-verified across 6+ gateway products |
| Architecture | HIGH | Verified across production systems |
| Pitfalls | HIGH | Verified via issue trackers and production reports |

## Open Questions

- Which async etcd3 client works best with FastAPI? Needs validation spike.
- Does vLLM expose metrics beyond `/health`? Prometheus metrics could inform readiness probes.
- Single-process vs multi-worker Uvicorn from day one?

---
*Research completed: 2026-06-10*
*Sources: 4 research files (STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md)*
