# Phase 1: Foundation - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Project scaffolding, configuration management, shared Pydantic data models, and test infrastructure for the QUADS LLM Inference Proxy. This phase delivers a buildable, runnable, testable project skeleton — no business logic beyond model validation.

</domain>

<decisions>
## Implementation Decisions

### Package Layout
- **D-01:** Domain-grouped source tree under `inference_proxy/` with subdirectories per concern: `config/`, `models/`, `api/`, `discovery/`, `routing/`, `resilience/`
- **D-02:** Root Python package named `inference_proxy` (matches repo name)
- **D-03:** Separate `tests/` tree at repo root mirroring source structure (e.g., `tests/models/test_openai.py`)
- **D-04:** Full skeleton with stub `__init__.py` files for all future phase modules (discovery/, routing/) — gives a complete architecture view upfront

### Configuration Design
- **D-05:** Split pydantic-settings classes by domain: `GatewaySettings`, `EtcdSettings`, `RoutingSettings` composed into a root `Settings` class
- **D-06:** Env var prefix `INFERENCE_PROXY_` (nested vars use double-underscore: `INFERENCE_PROXY_GATEWAY__HOST`)
- **D-07:** Ship `.env.example` with all config keys and sensible defaults for local development
- **D-08:** Settings provided via FastAPI dependency injection — `get_settings()` function with `@lru_cache`, injected via `Depends()`. Tests can override the dependency.

### OpenAI Schema Scope
- **D-09:** Model the vLLM-relevant subset of the OpenAI API (messages, model, temperature, max_tokens, top_p, stream, stop) — skip OpenAI-only features like tools/function calling
- **D-10:** Use Pydantic `extra='allow'` on request models so unknown fields pass through to vLLM untouched — future-proof against new vLLM parameters
- **D-11:** Define both request AND response Pydantic models in Phase 1 (ChatCompletionResponse, CompletionResponse, streaming chunk models, OpenAI error schema)
- **D-12:** Include models for both `/v1/chat/completions` AND `/v1/completions` (text completion) endpoints

### Node State Model
- **D-13:** Node status as Python `StrEnum` with values: `healthy`, `unhealthy`, `draining`, `unknown`
- **D-14:** Node model includes PLAN.md fields (endpoint, status, model, last_heartbeat, capabilities) PLUS routing metadata (`active_connections: int`, `node_id: str`). Capabilities as a nested `NodeCapabilities` model.
- **D-15:** Separate serializer module for etcd JSON ↔ Node conversion (not built into the model). Keeps domain model testable without etcd dependency.
- **D-16:** One model per node — `model` field is a `str`, not `list[str]`. Multiple models means multiple containers on different ports.

### Claude's Discretion
- pyproject.toml structure and uv configuration details
- pytest fixture design and conftest.py organization
- structlog configuration specifics
- Ruff and mypy configuration settings
- FastAPI app factory pattern vs direct instantiation

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture
- `PLAN.md` — Architecture design document with etcd data schema (nodes/{node-id} JSON format), gateway pseudocode, gateway config YAML template, and system workflow diagrams
- `PLAN.md` §Component Details > etcd Service Registry — Defines the node registration JSON schema that Node model must match
- `PLAN.md` §Appendix > Gateway Configuration — Reference for configuration keys and defaults

### Project Context
- `.planning/REQUIREMENTS.md` — v1 requirement IDs (PROXY-01 through OBSV-01). Phase 1 has no direct requirements but establishes infrastructure for all of them.
- `.planning/ROADMAP.md` — Phase dependencies and success criteria. Phase 1 success criteria: pytest passes, uvicorn starts, Pydantic models validate.

### Technology Stack
- `CLAUDE.md` §Technology Stack — Locked dependency versions and rationale. Key: FastAPI >=0.135, httpx >=0.28, Pydantic >=2.10, etcd3gw >=2.5.0, Python >=3.12.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project with no existing code

### Established Patterns
- None — this phase establishes the patterns all future phases will follow

### Integration Points
- `pyproject.toml` — Entry point for `uv run uvicorn` and `uv run pytest`
- `inference_proxy/main.py` — FastAPI app instance that future phases add routes to

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

*Phase: 1-Foundation*
*Context gathered: 2026-06-10*
