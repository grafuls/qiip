# Phase 15: QUADS Client and Models - Research

**Researched:** 2026-07-16
**Domain:** QUADS REST API client, Pydantic models, hostname normalization, configuration
**Confidence:** HIGH

## Summary

Phase 15 builds the foundation layer for QUADS integration: a thin httpx-based async client that talks to the QUADS REST API, a Pydantic model for GPU host data, a hostname normalization function, and configuration settings. This is a pure data-access layer with zero UI or background-polling concerns (those are Phase 16+). The phase requires no new dependencies -- httpx and Pydantic are already installed.

The QUADS API returns host objects with a `processors` array; GPU hosts are identified by `processor_type == "GPU"` entries. The `/api/v3/available` endpoint returns a flat list of hostname strings. Both endpoints are unauthenticated GETs. The client must filter out broken/retired hosts and normalize hostnames to lowercase-stripped form for downstream merge compatibility.

**Primary recommendation:** Follow the existing package-per-domain pattern (`inference_proxy/quads/`), inject `httpx.AsyncClient` for testability, use `pytest-httpx` for mocking. Total scope is ~120-180 LOC across 3 new files and 2 modified files.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** QUADS instance returns short hostnames (not FQDNs). No domain stripping needed.
- **D-02:** Minimal `canonical_hostname()` function: strip whitespace, lowercase, strip trailing dots. Cheap insurance against format drift.
- **D-03:** `canonical_hostname()` lives in `quads/client.py`. Move to a shared location if needed when Phase 17 merge logic arrives.
- **D-04:** QUADSHost model captures: hostname, GPU vendor, GPU model, GPU count. Minimal data scope.
- **D-05:** GPU info captured now (vendor, model) even though Phase 15 only needs a boolean filter. Avoids model changes in Phase 18 which needs vendor/model display (DASH-05).
- **D-06:** Client filters out broken and retired hosts before returning. Downstream code never sees them.
- **D-07:** Host availability determined via `GET /api/v3/available` endpoint. Returns list of available hostnames.
- **D-08:** `get_available()` method added to QUADSClient in Phase 15. Phase 16 poller calls it.
- **D-09:** Client raises typed `QUADSConnectionError` exception on API failure. Callers handle it explicitly.
- **D-10:** QUADS is "required when configured" -- if `quads.base_url` is set, QUADS features are active. If not set, QUADS features are skipped. No explicit enabled/disabled toggle.
- **D-11:** Lazy validation -- no connectivity check at construction time. First `get_hosts()` or `get_available()` call reveals misconfiguration.

### Claude's Discretion
- httpx client configuration (timeouts, connection pooling) for the QUADS client
- QUADSHost Pydantic model field naming and exact structure
- QUADSSettings field names and defaults (base_url, request timeout)
- Internal method organization within QUADSClient

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUADS-01 | Gateway can connect to a configurable QUADS REST API and retrieve the list of all hosts | QUADSClient with `get_hosts()` using httpx.AsyncClient; QUADSSettings with `base_url` and `timeout` fields; existing pydantic-settings env var pattern |
| QUADS-03 | Gateway filters QUADS hosts to only those with GPU processors (processor_type=GPU) | Filter on `processors` array entries where `processor_type == "GPU"`; D-06 also filters broken/retired |
| QUADS-04 | Gateway normalizes hostnames to a canonical format for matching QUADS FQDNs with etcd short names | `canonical_hostname()` function per D-02: strip whitespace, lowercase, strip trailing dots |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| QUADS API communication | API / Backend | -- | httpx calls from gateway process to external QUADS server |
| Host data parsing | API / Backend | -- | Pydantic model validation of JSON responses |
| GPU filtering | API / Backend | -- | Business logic filtering on processor_type field |
| Hostname normalization | API / Backend | -- | String normalization for merge key consistency |
| Configuration | API / Backend | -- | pydantic-settings env vars, same tier as all existing config |

## Standard Stack

### Core (Already Installed -- Zero Additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | 0.28.1 | Async HTTP client to QUADS API | Already the proxy engine; AsyncClient for non-blocking calls [VERIFIED: installed in project] |
| pydantic | 2.13.4 | QUADSHost model, response validation | Already used for all models; frozen ConfigDict pattern established [VERIFIED: installed in project] |
| pydantic-settings | 2.14.1 | QUADSSettings configuration | Already used for all settings sub-models [VERIFIED: installed in project] |
| structlog | (installed) | Logging in client | Already used project-wide [VERIFIED: installed in project] |
| pytest-httpx | 0.36.2 | Mock httpx requests in tests | Already a dev dependency [VERIFIED: installed in project] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx AsyncClient | `quads` pip package | Pulls Flask + SQLAlchemy for 2 GET endpoints. Massive overkill. [CITED: .planning/research/SUMMARY.md] |
| httpx AsyncClient | `requests` (sync) | Sync-only, would need `asyncio.to_thread()` wrapping. httpx is already installed. |

**Installation:** None required. All dependencies already in `pyproject.toml`.

## Package Legitimacy Audit

No new packages to install. All libraries referenced are existing project dependencies verified in `pyproject.toml` and `uv.lock`.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    QUADSSettings (env vars)
                         |
                         v
  FastAPI lifespan --> QUADSClient(http_client, settings)
                         |
                         | httpx.AsyncClient
                         v
                    QUADS REST API
                    GET /api/v3/hosts --> JSON --> QUADSHost (Pydantic)
                    GET /api/v3/available --> JSON --> list[str]
                         |
                         v
                    canonical_hostname() normalizes hostnames
                         |
                         v
                    Filter: processor_type=="GPU", not broken, not retired
                         |
                         v
                    list[QUADSHost]  (returned to caller)
```

### Recommended Project Structure

```
inference_proxy/
├── quads/
│   ├── __init__.py      # exports QUADSClient, QUADSConnectionError
│   └── client.py        # QUADSClient class, canonical_hostname(), QUADSConnectionError
├── models/
│   └── quads.py         # QUADSHost Pydantic model (NEW)
├── config/
│   ├── settings.py      # Add QUADSSettings nested model (MODIFY)
│   └── dependencies.py  # Add get_quads_client() DI provider (MODIFY)

tests/
├── quads/
│   ├── __init__.py
│   └── test_client.py   # QUADSClient tests with pytest-httpx
├── models/
│   └── test_quads.py    # QUADSHost model tests
├── config/
│   └── test_settings.py # QUADSSettings tests (extend existing)
```

### Pattern 1: Package-per-domain

**What:** Each domain concept gets its own package under `inference_proxy/`. QUADS client goes in `inference_proxy/quads/`, not bolted onto provisioning or discovery. [VERIFIED: existing pattern -- `provisioning/`, `discovery/`, `resilience/`, `routing/`]

**When to use:** Always for new domain concepts in this project.

### Pattern 2: Frozen Pydantic Models with ConfigDict

**What:** All domain models use `ConfigDict(frozen=True)` for immutability. [VERIFIED: `Node`, `NodeCapabilities`, `AdminNodeResponse` all use this pattern]

**Example:**
```python
# Source: inference_proxy/models/node.py (existing pattern)
class QUADSHost(BaseModel):
    model_config = ConfigDict(frozen=True)

    hostname: str
    gpu_vendor: str
    gpu_model: str
    gpu_count: int
```

### Pattern 3: Nested BaseModel for Settings (not BaseSettings)

**What:** Sub-models inherit `BaseModel`, only root `Settings` inherits `BaseSettings`. Env vars use `INFERENCE_PROXY_QUADS__BASE_URL` format. [VERIFIED: `settings.py` lines 14-118, every sub-model is `BaseModel`]

**Example:**
```python
# Source: inference_proxy/config/settings.py (existing pattern)
class QUADSSettings(BaseModel):
    base_url: str | None = None  # D-10: None means QUADS disabled
    timeout: float = 10.0

# In root Settings class:
quads: QUADSSettings = QUADSSettings()
```

### Pattern 4: DI via app.state + Depends()

**What:** Services created in lifespan, stored in `app.state`, exposed via `get_*()` functions using `Request`. [VERIFIED: `dependencies.py` -- `get_provisioner()`, `get_proxy_client()`, etc.]

**Example:**
```python
# Source: inference_proxy/config/dependencies.py (existing pattern)
def get_quads_client(request: Request) -> QUADSClient:
    return request.app.state.quads_client
```

### Pattern 5: Constructor Injection for Testability

**What:** Pass `httpx.AsyncClient` into `QUADSClient.__init__()` rather than creating it internally. Tests inject a mock client. [VERIFIED: `ProxyClient` takes `http_client` in constructor, `NodeProvisioner` takes all deps via constructor]

### Anti-Patterns to Avoid
- **Bolting QUADS onto NodeProvisioner:** Different responsibilities, different change frequencies. SRP violation. [CITED: .planning/research/ARCHITECTURE.md]
- **Installing the `quads` pip package:** Pulls Flask + SQLAlchemy for 2 GET calls. Use httpx directly. [CITED: .planning/research/SUMMARY.md]
- **Connectivity check in constructor:** D-11 says lazy validation. First API call reveals issues.
- **Returning broken/retired hosts:** D-06 says filter them out in the client. Downstream never sees them.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP client | Custom urllib wrapper | `httpx.AsyncClient` | Already installed, handles connection pooling, timeouts, async |
| Response validation | Manual dict parsing | Pydantic `BaseModel` with `model_validate()` | Automatic type coercion, `extra="ignore"` for forward compat |
| Config from env vars | `os.getenv()` calls | `pydantic-settings` `BaseModel` subclass | Type validation, nested delimiter support, `.env` file loading |
| Retry logic | Custom retry loops | Let caller (Phase 16 poller) handle retries | D-09 says client raises `QUADSConnectionError`; retry policy belongs to the poller |

## Common Pitfalls

### Pitfall 1: QUADS Response Has `extra` Fields
**What goes wrong:** QUADS returns many fields per host (interfaces, disks, memory, cloud, etc.). If QUADSHost model is strict, it rejects responses.
**Why it happens:** Pydantic v2 default is `extra="ignore"` for BaseModel, but it's easy to accidentally set `extra="forbid"`.
**How to avoid:** Explicitly set `extra="ignore"` on QUADSHost or rely on the default. Only capture the 4 fields we need per D-04.
**Warning signs:** `ValidationError` mentioning unexpected fields.

### Pitfall 2: Processors Array is Nested
**What goes wrong:** GPU data is inside a `processors` array on the host object. Each entry has `processor_type`, `vendor`, `product`. Need to iterate to find GPU entries.
**Why it happens:** A host can have multiple processors (CPUs and GPUs). There is no top-level `has_gpu` flag.
**How to avoid:** Parse the full host JSON, extract GPU processors from the `processors` array, aggregate into QUADSHost fields (vendor, model, count).
**Warning signs:** Treating the first processor as the GPU, or assuming only one GPU type per host.

### Pitfall 3: Available Endpoint Returns Strings, Not Objects
**What goes wrong:** `GET /api/v3/available` returns `["host01", "host02"]` -- a flat list of hostname strings, not host objects. Trying to parse as host objects fails.
**Why it happens:** Different endpoint, different response shape.
**How to avoid:** `get_available()` returns `list[str]` (after `canonical_hostname()` normalization), not `list[QUADSHost]`. [CITED: .planning/research/FEATURES.md lines 119-121]
**Warning signs:** Pydantic validation errors on the available response.

### Pitfall 4: Optional base_url Handling
**What goes wrong:** If `quads.base_url` is `None` (not configured), calling `get_hosts()` crashes with an httpx URL error.
**Why it happens:** D-10 says QUADS is "required when configured." The client is only instantiated when `base_url` is set.
**How to avoid:** Gate QUADSClient creation in lifespan on `settings.quads.base_url is not None`. The DI provider returns `None` when QUADS is not configured. Callers check before use.
**Warning signs:** `httpx.InvalidURL` exceptions at runtime.

### Pitfall 5: Separate httpx Client for QUADS
**What goes wrong:** Reusing the proxy httpx.AsyncClient for QUADS calls means QUADS timeouts (short) conflict with LLM inference timeouts (120s read).
**Why it happens:** Different backend, different latency profile.
**How to avoid:** Create a dedicated `httpx.AsyncClient` for QUADSClient with its own timeout configuration (e.g., 10s connect+read). [CITED: .planning/research/SUMMARY.md, pitfall #13]
**Warning signs:** QUADS calls waiting 120s before timing out.

## Code Examples

### QUADSHost Model

```python
# Pattern: frozen Pydantic model, minimal fields per D-04
from pydantic import BaseModel, ConfigDict

class QUADSHost(BaseModel):
    """A GPU host from the QUADS inventory."""
    model_config = ConfigDict(frozen=True)

    hostname: str
    gpu_vendor: str
    gpu_model: str
    gpu_count: int
```

### canonical_hostname()

```python
# Per D-02: strip whitespace, lowercase, strip trailing dots
def canonical_hostname(raw: str) -> str:
    """Normalize a hostname to canonical form for merge-key matching."""
    return raw.strip().lower().rstrip(".")
```

### QUADSClient Skeleton

```python
# Pattern: constructor injection, typed exception, structlog
import httpx
import structlog

logger = structlog.get_logger()

class QUADSConnectionError(Exception):
    """Raised when the QUADS API is unreachable or returns an error."""

class QUADSClient:
    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")

    async def get_hosts(self) -> list[QUADSHost]:
        """Fetch GPU hosts from QUADS, filtering out broken/retired."""
        try:
            resp = await self._client.get(f"{self._base_url}/api/v3/hosts")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise QUADSConnectionError(str(exc)) from exc

        hosts = []
        for raw in resp.json():
            if raw.get("broken") or raw.get("retired"):
                continue  # D-06
            gpus = [p for p in raw.get("processors", []) if p.get("processor_type") == "GPU"]
            if not gpus:
                continue  # QUADS-03: GPU filter
            hosts.append(QUADSHost(
                hostname=canonical_hostname(raw["name"]),
                gpu_vendor=gpus[0].get("vendor", ""),
                gpu_model=gpus[0].get("product", ""),
                gpu_count=len(gpus),
            ))
        return hosts

    async def get_available(self) -> list[str]:
        """Fetch list of available hostnames from QUADS."""
        try:
            resp = await self._client.get(f"{self._base_url}/api/v3/available")
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise QUADSConnectionError(str(exc)) from exc
        return [canonical_hostname(h) for h in resp.json()]
```

### QUADSSettings Pattern

```python
# Follows SSHSettings / ProvisioningSettings pattern
class QUADSSettings(BaseModel):
    """QUADS API configuration. None base_url = QUADS disabled (D-10)."""
    base_url: str | None = None
    timeout: float = 10.0
```

### Lifespan Integration

```python
# In main.py lifespan, after provisioner setup:
if resolved_settings.quads.base_url is not None:
    quads_http = httpx.AsyncClient(
        timeout=httpx.Timeout(resolved_settings.quads.timeout),
    )
    quads_client = QUADSClient(quads_http, resolved_settings.quads.base_url)
    app.state.quads_client = quads_client
else:
    app.state.quads_client = None
    quads_http = None

# In shutdown:
if quads_http is not None:
    await quads_http.aclose()
```

### DI Provider

```python
# Returns QUADSClient | None -- callers check
from inference_proxy.quads.client import QUADSClient

def get_quads_client(request: Request) -> QUADSClient | None:
    return request.app.state.quads_client  # type: ignore[no-any-return]
```

### Test Pattern with pytest-httpx

```python
# Follows existing test patterns in tests/proxy/test_client.py
import pytest
from pytest_httpx import HTTPXMock

async def test_get_hosts_filters_gpu(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://quads.example.com/api/v3/hosts",
        json=[
            {"name": "gpu-host", "broken": False, "retired": False,
             "processors": [{"processor_type": "GPU", "vendor": "NVIDIA", "product": "A100"}]},
            {"name": "cpu-host", "broken": False, "retired": False,
             "processors": [{"processor_type": "CPU", "vendor": "Intel", "product": "Xeon"}]},
        ],
    )
    async with httpx.AsyncClient() as client:
        quads = QUADSClient(client, "https://quads.example.com")
        hosts = await quads.get_hosts()

    assert len(hosts) == 1
    assert hosts[0].hostname == "gpu-host"
    assert hosts[0].gpu_vendor == "NVIDIA"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `quads` pip package (requests-based sync client) | Direct httpx AsyncClient calls | Project decision | Avoids pulling Flask+SQLAlchemy transitive deps |
| Pydantic v1 models | Pydantic v2 with `ConfigDict(frozen=True)` | Pydantic 2.0 (2023) | Rust-backed validation, `model_validate()` API |
| `os.getenv()` config | `pydantic-settings` nested models | Project convention | Type-safe, validated, nested delimiter support |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | QUADS v3 API `GET /hosts` returns `processors` array with `processor_type` field | Code Examples | GPU filter logic would need different field path. Low risk -- verified against QUADS source. |
| A2 | `GET /available` returns flat `list[str]` of hostnames | Code Examples | Would need different parsing. Low risk -- verified against QUADS blueprints source. |
| A3 | QUADS GET endpoints are unauthenticated | Architecture Patterns | Would need auth header config. Verified against QUADS blueprint decorators. |

All three assumptions are verified against QUADS source code (github.com/redhat-performance/quads) per the pre-existing research. Risk is low. The main uncertainty is whether the deployed QUADS instance matches the source code version -- this is flagged in the research summary as needing a `curl` test before coding.

## Open Questions

1. **Deployed QUADS instance version**
   - What we know: Research covers QUADS v3 API from GitHub source
   - What's unclear: Whether the target deployment runs v3 or an older version
   - Recommendation: First task should include a manual `curl` verification step against the live instance

2. **Multiple GPU types per host**
   - What we know: D-04 captures gpu_vendor, gpu_model, gpu_count. Code examples use `gpus[0]` for vendor/model.
   - What's unclear: If a host has mixed GPU types (e.g., 2x A100 + 2x V100), which vendor/model to report
   - Recommendation: Use first GPU's vendor/model (simplest). Phase 18 can show full list if needed. Flag with a comment.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/quads/ tests/models/test_quads.py -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUADS-01 | Connect to QUADS API and retrieve hosts | unit | `uv run pytest tests/quads/test_client.py::TestGetHosts -x` | Wave 0 |
| QUADS-01 | QUADSSettings base_url configurable | unit | `uv run pytest tests/config/test_settings.py::TestQUADSSettings -x` | Wave 0 |
| QUADS-03 | Filter to GPU-only hosts | unit | `uv run pytest tests/quads/test_client.py::TestGPUFilter -x` | Wave 0 |
| QUADS-04 | canonical_hostname normalization | unit | `uv run pytest tests/quads/test_client.py::TestCanonicalHostname -x` | Wave 0 |
| D-06 | Filter broken/retired hosts | unit | `uv run pytest tests/quads/test_client.py::TestBrokenRetiredFilter -x` | Wave 0 |
| D-08 | get_available() returns normalized hostnames | unit | `uv run pytest tests/quads/test_client.py::TestGetAvailable -x` | Wave 0 |
| D-09 | QUADSConnectionError on API failure | unit | `uv run pytest tests/quads/test_client.py::TestConnectionError -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/quads/ tests/models/test_quads.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/quads/__init__.py` -- package init
- [ ] `tests/quads/test_client.py` -- QUADSClient unit tests with pytest-httpx
- [ ] `tests/models/test_quads.py` -- QUADSHost model tests

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | QUADS GETs are unauthenticated |
| V3 Session Management | no | Stateless client |
| V4 Access Control | no | Read-only integration |
| V5 Input Validation | yes | Pydantic model validation on QUADS responses; `canonical_hostname()` strips/lowercases input |
| V6 Cryptography | no | No secrets handled |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SSRF via configurable base_url | Spoofing | Internal network only (project constraint); base_url from env vars, not user input |
| Malformed QUADS response injection | Tampering | Pydantic validation with `extra="ignore"`; only known fields extracted |
| QUADS API unavailability | Denial of Service | Typed exception (QUADSConnectionError); callers degrade gracefully |

## Sources

### Primary (HIGH confidence)
- Existing codebase: `inference_proxy/config/settings.py`, `dependencies.py`, `main.py`, `models/node.py`, `models/admin.py` -- verified patterns for settings, DI, models
- QUADS GitHub source: blueprints, models, swagger.yaml -- verified API response shapes [CITED: .planning/research/FEATURES.md, .planning/research/SUMMARY.md]
- Project `pyproject.toml` -- verified installed dependencies and versions
- Test suite: 340 tests passing, pytest-httpx pattern established

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` -- component placement decisions
- `.planning/phases/15-quads-client-and-models/15-CONTEXT.md` -- locked decisions D-01 through D-11

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all patterns verified in existing codebase
- Architecture: HIGH -- follows established package-per-domain, DI, frozen model patterns
- Pitfalls: HIGH -- response shapes verified against QUADS source code; httpx timeout separation documented

**Research date:** 2026-07-16
**Valid until:** 2026-08-16 (stable domain, no fast-moving dependencies)
