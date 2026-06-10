# Walking Skeleton -- QUADS LLM Inference Proxy

**Phase:** 1
**Generated:** 2026-06-10

## Capability Proven End-to-End

A developer can start the gateway with `uv run uvicorn inference_proxy.main:app`, hit GET /health and receive a 200 JSON response, and run `uv run pytest` to execute a passing test suite that validates all shared data models.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Framework | FastAPI >=0.135 with app factory pattern (`create_app()`) | Native SSE, Pydantic v2 integration, auto OpenAPI docs. Factory pattern enables test isolation with different configs. |
| Data layer | etcd via etcd3gw (Phase 2) | Service discovery for dynamic vLLM node registry. HTTP gateway protocol avoids grpcio C extension issues. |
| Auth | None (internal network) | v1 is internal-only per REQUIREMENTS.md out-of-scope table. No external-facing endpoints. |
| Deployment target | Local dev via `uv run uvicorn` | Deployment is a separate concern per CLAUDE.md constraints. NGINX/SSL termination handled externally. |
| Directory layout | Domain-grouped under `inference_proxy/` with subdirectories: config/, models/, api/, discovery/, routing/, resilience/ | Per D-01. Each concern gets its own package. Stub __init__.py for future phases per D-04. |
| Package manager | uv with pyproject.toml + uv.lock | 10-100x faster than pip, lockfile support, Python version management. |
| Configuration | pydantic-settings with env_prefix + nested delimiter, DI via Depends() | Type-safe config from env vars. Domain-split settings (Gateway, Etcd, Routing) composed into root Settings per D-05. |
| Logging | structlog with JSON/console renderer toggle | Structured JSON for production, pretty console for dev. Async-safe via context variables. |
| HTTP client | httpx (Phase 3) | Async streaming, connection pooling, native SSE consumption with httpx-sse. |
| Testing | pytest + pytest-asyncio (auto mode) + pytest-httpx | Standard Python testing stack. Auto mode eliminates marker boilerplate. |
| Linting/formatting | ruff (single tool) | Replaces flake8 + black + isort. Rust-based, 10-100x faster. |
| Type checking | mypy --strict with pydantic plugin | Static type safety across the entire codebase. |

## Stack Touched in Phase 1

- [x] Project scaffold (uv init, pyproject.toml, build system, ruff, mypy, pytest config)
- [x] Routing -- GET /health endpoint returns 200 with JSON status
- [ ] Database -- N/A (etcd integration is Phase 2; no traditional DB in this project)
- [ ] UI -- N/A (API-only gateway; no frontend)
- [x] Deployment -- documented local run command: `uv run uvicorn inference_proxy.main:app --host 0.0.0.0 --port 8080`

**Note:** This project is a stateless API gateway, not a traditional web app. There is no database or UI layer. The "data layer" equivalent is etcd (Phase 2) for service discovery. The walking skeleton proves the toolchain works: uv + FastAPI + Pydantic + pytest + structlog.

## Out of Scope (Deferred to Later Slices)

- etcd connectivity and node discovery (Phase 2)
- Request proxying to vLLM nodes (Phase 3)
- SSE streaming (Phase 3)
- Load balancing logic (Phase 4)
- Health checks, retry, circuit breaker (Phase 5)
- Structured request logging, admin API (Phase 6)
- Authentication/authorization (out of scope for v1)
- Multi-worker Uvicorn (out of scope for v1)
- NGINX/SSL termination (separate deployment concern)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 2: Gateway discovers and tracks vLLM nodes registered in etcd in real time
- Phase 3: Clients send OpenAI-compatible requests and receive responses (including SSE streaming) through the gateway
- Phase 4: Gateway routes to optimal node based on active connections and requested model
- Phase 5: Gateway handles node failures transparently with health checks, retry, circuit breaker, graceful shutdown
- Phase 6: Operators monitor via structured logs and inspect node state via admin API
