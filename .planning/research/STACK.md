# Technology Stack

**Project:** QUADS LLM Inference Proxy
**Researched:** 2026-06-10
**Overall Confidence:** HIGH

## Recommended Stack

### Runtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.12 | Runtime | Mature async support, broad library compatibility, matches team expertise. 3.13 is viable but 3.12 has the widest library ecosystem validation. Avoid 3.14 (too new, some deps still catching up). | HIGH |
| uv | >=0.11 | Package/project manager | 10-100x faster than pip, replaces pip+virtualenv+pip-tools. Lockfile support via `uv.lock`. Rust-based, stable in production CI pipelines across ecosystem. Astral-backed (same org as Ruff). | HIGH |

### Core Framework

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| FastAPI | >=0.135, <1.0 | HTTP framework | Native SSE via `fastapi.sse.EventSourceResponse` (added 0.135.0). Built-in Pydantic integration for request/response validation. Async-first. Auto-generates OpenAPI docs useful for debugging. Current latest is 0.136.3. | HIGH |
| Uvicorn | >=0.45 | ASGI server | Standard FastAPI deployment server. Install with `[standard]` extra for uvloop + httptools performance. Current latest is 0.49.0. Requires Python 3.10+. | HIGH |
| Pydantic | >=2.10, <3.0 | Data validation | Core FastAPI dependency. Use v2 (Rust-backed validation). Current latest 2.13.4. Pydantic v1 support is deprecated in FastAPI; v2 is the only path forward. | HIGH |
| pydantic-settings | >=2.14 | Configuration | Type-safe settings from env vars, `.env` files, YAML. Nested config support. Natural fit with Pydantic models. Current latest 2.14.1. | HIGH |

### HTTP Client (Proxy Engine)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| httpx | >=0.28, <1.0 | Async HTTP client | The proxy engine -- forwards requests to vLLM backends. Native async (`AsyncClient`), streaming via `client.stream()`, connection pooling. Paired with `httpx-sse` for SSE consumption. Current stable 0.28.1 (1.0.dev1 exists but is not stable). | HIGH |
| httpx-sse | >=0.4.3 | SSE client consumption | Parses upstream SSE events from vLLM streaming responses. `aconnect_sse()` + `aiter_sse()` for clean async iteration. 176M monthly downloads -- widely adopted. MIT licensed. | HIGH |

### Service Discovery

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| etcd3gw | >=2.5.0 | etcd client (sync operations) | OpenStack-maintained, actively released (Jan 2026). Uses etcd's HTTP/JSON gateway -- no grpcio dependency (avoids C extension build issues). Provides get/put/delete/watch/lease/lock. Synchronous API. | MEDIUM |

**The etcd client decision is the most nuanced choice in this stack. Here is the full rationale:**

The PLAN.md references `etcd3` (kragniz/python-etcd3), which is **effectively abandoned** -- last meaningful release years ago, Python 2.7/3.4/3.5 era, synchronous-only, grpcio dependency with C build issues. Do not use it.

The async etcd client landscape is fragmented:

| Library | Protocol | Async | Last Release | Stars | Verdict |
|---------|----------|-------|-------------|-------|---------|
| etcd3 (kragniz) | Native gRPC | No | Abandoned | ~500 | **REJECT** -- unmaintained, sync only |
| etcd3gw | HTTP Gateway | No | Jan 2026 | ~80 | **USE** -- actively maintained by OpenStack |
| async-etcd3gw | HTTP Gateway | Yes (aiohttp) | May 2023 | 1 | **REJECT** -- abandoned, adds aiohttp dep |
| aetcd | Native gRPC | Yes | Alpha (1.0.0a4) | 31 | **REJECT** -- alpha, grpcio dep, small community |
| etcetra | Pure asyncio gRPC | Yes | Apr 2024 | 9 | **REJECT** -- tiny community, uncertain future |

**Recommendation: Use `etcd3gw` with a thin async wrapper.**

`etcd3gw` is the only option that is (a) actively maintained, (b) has institutional backing (OpenStack), (c) avoids the grpcio C extension nightmare, and (d) has a real user base. Its synchronous API (backed by `requests`) works fine for the gateway's etcd interaction patterns:

- **Watch operations**: Run `etcd3gw` watch in a dedicated background thread via `asyncio.to_thread()` or a `threading.Thread`. Watch is long-polling, so thread-per-watcher is natural.
- **Get/put/lease**: These are short-lived calls. Wrap in `asyncio.to_thread()` for non-blocking use in FastAPI handlers, or call from background tasks.
- **Startup**: Initial node list fetch runs at startup (sync is fine).

This approach is pragmatic: the etcd interaction surface is small (watch prefix, get nodes, health updates) and doesn't justify pulling in an unstable async library. A project-local `EtcdServiceRegistry` abstraction class hides the sync-vs-async detail behind a clean interface, making future migration to a native async client trivial.

### Logging

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| structlog | >=26.1.0 | Structured logging | JSON-structured logs for production, pretty console for dev. Async-safe (context variables). Battle-tested since 2013. Integrates with stdlib logging. Current latest 26.1.0. | HIGH |

### Development & Quality

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| ruff | >=0.15 | Linter + formatter | Replaces flake8 + black + isort in a single Rust binary. 10-100x faster. Configures via pyproject.toml. Current latest 0.15.16. | HIGH |
| mypy | >=2.1 | Type checking | Static type safety. Use `--strict` mode. Current latest 2.1.0. Minimum target Python 3.10. | HIGH |
| pytest | >=8.0 | Test framework | Standard Python testing. | HIGH |
| pytest-asyncio | >=1.4 | Async test support | Run async test functions in event loops. Use `auto` mode to avoid manual `@pytest.mark.asyncio` everywhere. Current latest 1.4.0. | HIGH |
| pytest-httpx | >=0.36 | HTTP mocking | Mock httpx requests in tests. Clean API for registering responses, matching URLs, streaming. Essential for testing proxy behavior without live backends. Current latest 0.36.2. | HIGH |
| coverage | >=7.0 | Code coverage | Measure test coverage. Use with `pytest-cov`. | HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | >=9.0 | Retry logic | Retry failed proxy requests to alternate backends. Configurable backoff strategies, exception filtering. |
| anyio | >=4.13 | Async primitives | Task groups, cancellation scopes. Already a FastAPI/httpx transitive dependency. Use for structured concurrency in background health checks. |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Framework | FastAPI | Flask, aiohttp, Starlette (raw) | Flask lacks native async. aiohttp is lower-level with no auto-validation. Raw Starlette lacks Pydantic integration. FastAPI provides the best DX for an OpenAI-compatible API. |
| HTTP Client | httpx | aiohttp.ClientSession, requests | requests is sync-only. aiohttp is viable but httpx has cleaner API, native httpcore/h2 support, and better streaming ergonomics. httpx is already FastAPI's recommended HTTP client. |
| etcd Client | etcd3gw + thread wrapper | aetcd, etcetra, python-etcd3 | All async alternatives are alpha/abandoned/tiny-community. python-etcd3 is abandoned. etcd3gw is the only production-grade option with institutional maintenance. |
| SSE (server) | FastAPI built-in EventSourceResponse | sse-starlette | FastAPI 0.135+ ships native SSE with Pydantic serialization on the Rust side. sse-starlette (v3.4.4) is excellent but now redundant for new projects targeting modern FastAPI. |
| SSE (client) | httpx-sse | sseclient, raw iter_bytes | httpx-sse integrates natively with httpx streaming. sseclient works but is older and less ergonomic with async code. |
| Package manager | uv | pip, poetry, pdm | uv is 10-100x faster, handles Python version management, and has lockfile support. Poetry is slower and more opinionated about publishing workflow. pdm is good but less ecosystem momentum. |
| Linter | ruff | flake8 + black + isort | ruff replaces all three in a single tool. No reason to use the three-tool approach in 2026. |
| Type checker | mypy | pyright, ty | mypy is the most widely supported. pyright is faster but requires Node.js. ty (from Astral/Ruff team) is emerging but not yet production-ready. |
| Logging | structlog | loguru, stdlib logging | loguru is good for simple projects but structlog's processor pipeline is better for structured JSON output needed in production observability. stdlib logging alone is too verbose to configure well. |
| Config | pydantic-settings | python-dotenv, dynaconf | pydantic-settings provides type validation on configuration values, integrates naturally with the Pydantic-heavy stack. python-dotenv is just env loading without validation. |

## What NOT to Use

| Technology | Why Not |
|------------|---------|
| python-etcd3 (kragniz) | Abandoned. Python 2.7 era. grpcio dependency causes build issues. |
| etcd3 on PyPI | Same as python-etcd3. The name is confusing but it's the same dead library. |
| aiohttp (as framework) | Lower-level than FastAPI, no auto-validation, no OpenAPI generation. Fine as a client library but not as the framework. |
| grpcio (direct) | Heavy C extension. Build issues on some platforms. etcd3gw avoids this entirely by using the HTTP gateway. |
| Flask | Synchronous by default. Async support bolted on. Not suitable for a streaming proxy. |
| Django | Massive ORM-centric framework. Wrong tool for a stateless proxy. |
| sse-starlette | Still works but FastAPI 0.135+ has built-in SSE. Adding sse-starlette is an unnecessary dependency for new projects. |
| requests | Synchronous HTTP client. httpx is the modern replacement with both sync and async APIs. |
| Celery | No background task queue needed. The gateway is a stateless proxy. asyncio tasks suffice. |

## Project Structure

```
inference-proxy/
  pyproject.toml          # uv project config, dependencies, tool settings
  uv.lock                 # Lockfile (auto-generated by uv)
  src/
    inference_proxy/
      __init__.py
      main.py             # FastAPI app factory
      config.py           # pydantic-settings configuration
      api/                # Route handlers (OpenAI-compatible endpoints)
      proxy/              # httpx-based request forwarding, SSE streaming
      discovery/          # etcd service registry abstraction
      balancer/           # Load balancing strategies
      health/             # Backend health checking
  tests/
    conftest.py
    test_api/
    test_proxy/
    test_discovery/
    test_balancer/
```

## Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize project
uv init --lib --name inference-proxy

# Core dependencies
uv add "fastapi[standard]>=0.135"
uv add "httpx>=0.28"
uv add "httpx-sse>=0.4.3"
uv add "etcd3gw>=2.5.0"
uv add "pydantic>=2.10"
uv add "pydantic-settings>=2.14"
uv add "structlog>=26.1.0"
uv add "tenacity>=9.0"

# Dev dependencies
uv add --dev "pytest>=8.0"
uv add --dev "pytest-asyncio>=1.4"
uv add --dev "pytest-httpx>=0.36"
uv add --dev "pytest-cov>=5.0"
uv add --dev "ruff>=0.15"
uv add --dev "mypy>=2.1"
```

## Key Version Constraints

| Dependency | Minimum | Why This Minimum |
|------------|---------|-----------------|
| FastAPI >= 0.135 | Built-in `fastapi.sse.EventSourceResponse` added in 0.135.0. Below this, you need sse-starlette. |
| httpx >= 0.28 | Stable async streaming API. Earlier versions had breaking changes in transport layer. |
| Pydantic >= 2.10 | Required by FastAPI >= 0.135 (`pydantic>=2.9.0` is the floor, but 2.10+ has important fixes). |
| Python >= 3.12 | Needed for improved asyncio task groups, better typing support, performance improvements. |
| etcd3gw >= 2.5.0 | Latest release with Python 3.12 support. |

## Sources

- FastAPI releases: https://github.com/fastapi/fastapi/releases -- v0.136.3 (May 2026)
- FastAPI SSE docs: https://fastapi.tiangolo.com/tutorial/server-sent-events/
- httpx PyPI: https://pypi.org/project/httpx/ -- v0.28.1 (Dec 2024)
- httpx streaming docs: https://www.python-httpx.org/async
- httpx-sse PyPI: https://pypi.org/project/httpx-sse/ -- v0.4.3 (Oct 2025)
- etcd3gw PyPI: https://pypi.org/project/etcd3gw/ -- v2.5.0 (Jan 2026)
- etcd3gw docs: https://docs.openstack.org/etcd3gw/latest/
- etcd Python client discussion: https://github.com/etcd-io/etcd/discussions/18211
- Pydantic PyPI: https://pypi.org/project/pydantic/ -- v2.13.4 (May 2026)
- pydantic-settings PyPI: https://pypi.org/project/pydantic-settings/ -- v2.14.1 (May 2026)
- Uvicorn PyPI: https://pypi.org/project/uvicorn/ -- v0.49.0
- structlog docs: https://www.structlog.org/ -- v26.1.0
- Ruff GitHub: https://github.com/astral-sh/ruff -- v0.15.16
- mypy PyPI: https://pypi.org/project/mypy/ -- v2.1.0 (May 2026)
- pytest-asyncio PyPI: https://pypi.org/project/pytest-asyncio/ -- v1.4.0
- pytest-httpx PyPI: https://pypi.org/project/pytest-httpx/ -- v0.36.2
- uv GitHub: https://github.com/astral-sh/uv -- v0.11.19 (Jun 2026)
- vLLM OpenAI API docs: https://docs.vllm.ai/en/stable/serving/openai_compatible_server/
- LLM gateway patterns: https://agenta.ai/blog/top-llm-gateways
