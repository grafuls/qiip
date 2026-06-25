# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 1-Foundation
**Areas discussed:** Package layout, Configuration design, OpenAI schema scope, Node state model

---

## Package Layout

### Source tree organization

| Option | Description | Selected |
|--------|-------------|----------|
| Domain-grouped | inference_proxy/ with subdirectories per concern: models/, config/, api/, discovery/, routing/ | ✓ |
| Flat package | All modules directly under inference_proxy/. Simpler but may get crowded by Phase 3-4 | |
| You decide | Let Claude pick the layout based on what fits the roadmap best | |

**User's choice:** Domain-grouped
**Notes:** None

### Root package name

| Option | Description | Selected |
|--------|-------------|----------|
| inference_proxy | Matches the repo name, clear what it does | ✓ |
| quads_gateway | Ties it to the QUADS ecosystem | |
| llm_gateway | More generic | |

**User's choice:** inference_proxy
**Notes:** None

### Test location

| Option | Description | Selected |
|--------|-------------|----------|
| Separate tests/ tree | tests/ at repo root mirroring src structure | ✓ |
| Co-located tests | Test files next to source | |

**User's choice:** Separate tests/ tree
**Notes:** None

### Placeholder modules

| Option | Description | Selected |
|--------|-------------|----------|
| Only active modules | Create config/, models/, api/ with real code. Leave discovery/ and routing/ for later phases | |
| Full skeleton with stubs | Create all directories now with __init__.py stubs | ✓ |

**User's choice:** Full skeleton with stubs
**Notes:** None

---

## Configuration Design

### Config structure

| Option | Description | Selected |
|--------|-------------|----------|
| Split by domain | Separate Pydantic Settings classes per concern composed into root Settings | ✓ |
| Single flat class | One Settings class with all fields | |
| You decide | Let Claude pick based on what fits the roadmap best | |

**User's choice:** Split by domain
**Notes:** None

### Env var prefix

| Option | Description | Selected |
|--------|-------------|----------|
| INFERENCE_PROXY_ | Matches the package name, nested with double-underscore | ✓ |
| GATEWAY_ | Shorter, role-focused | |
| No prefix | Bare env vars, collision-prone | |

**User's choice:** INFERENCE_PROXY_
**Notes:** None

### .env.example

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, with defaults | Ship .env.example with all config keys and sensible defaults for local dev | ✓ |
| No .env file | Rely on pydantic-settings defaults in the code | |

**User's choice:** Yes, with defaults
**Notes:** None

### Settings injection

| Option | Description | Selected |
|--------|-------------|----------|
| FastAPI dependency injection | get_settings() with @lru_cache, injected via Depends() | ✓ |
| Module-level singleton | Instantiate settings at module import time | |

**User's choice:** FastAPI dependency injection
**Notes:** None

---

## OpenAI Schema Scope

### API spec coverage

| Option | Description | Selected |
|--------|-------------|----------|
| vLLM-relevant subset | Model the fields vLLM actually accepts and returns | ✓ |
| Pass-through with minimal validation | Validate only model and stream, forward everything else | |
| Full OpenAI spec | Model the complete OpenAI chat/completion API | |

**User's choice:** vLLM-relevant subset
**Notes:** None

### Unknown field handling

| Option | Description | Selected |
|--------|-------------|----------|
| Pass through unknown fields | Use Pydantic extra='allow' — future-proof | ✓ |
| Strict validation, reject unknowns | Use extra='forbid' — safer but requires updates | |

**User's choice:** Pass through unknown fields
**Notes:** None

### Response models

| Option | Description | Selected |
|--------|-------------|----------|
| Both request and response | Define response models, streaming chunk models, and error schema in Phase 1 | ✓ |
| Requests only | Response models wait for Phase 3 | |

**User's choice:** Both request and response
**Notes:** None

### Completions endpoint

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, both endpoints | Include /v1/completions models alongside chat completions | ✓ |
| Chat only, defer completions | Focus on /v1/chat/completions only | |

**User's choice:** Yes, both endpoints
**Notes:** None

---

## Node State Model

### Status representation

| Option | Description | Selected |
|--------|-------------|----------|
| String enum | Python StrEnum with healthy, unhealthy, draining, unknown | ✓ |
| Boolean flags | Separate is_healthy and is_draining booleans | |
| You decide | Let Claude pick the representation | |

**User's choice:** String enum
**Notes:** None

### Node fields

| Option | Description | Selected |
|--------|-------------|----------|
| PLAN.md fields + routing metadata | Include active_connections, node_id, nested NodeCapabilities | ✓ |
| Strict PLAN.md only | Add routing fields in Phase 4 | |
| You decide | Let Claude determine the right fields | |

**User's choice:** PLAN.md fields + routing metadata
**Notes:** None

### etcd serialization

| Option | Description | Selected |
|--------|-------------|----------|
| Separate serializer | Node is a pure domain model, separate module handles etcd JSON conversion | ✓ |
| Built into the model | from_etcd_value()/to_etcd_value() class methods on Node | |

**User's choice:** Separate serializer
**Notes:** None

### Multi-model support

| Option | Description | Selected |
|--------|-------------|----------|
| One model per node | model field as str. Multiple models = multiple containers | ✓ |
| Multiple models per node | model field as list[str] | |

**User's choice:** One model per node
**Notes:** None

---

## Claude's Discretion

- pyproject.toml structure and uv configuration details
- pytest fixture design and conftest.py organization
- structlog configuration specifics
- Ruff and mypy configuration settings
- FastAPI app factory pattern vs direct instantiation

## Deferred Ideas

None — discussion stayed within phase scope
