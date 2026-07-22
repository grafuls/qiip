# Phase 22: Power Management Endpoints - Research

**Researched:** 2026-07-22
**Domain:** FastAPI endpoint wiring (admin API extension)
**Confidence:** HIGH

## Summary

This phase wires the existing `RedfishClient` (Phase 21) to two new admin API endpoints: GET and POST on `/admin/nodes/{hostname}/power`. No new dependencies, no new architectural patterns -- it reuses the exact DI, model, and router conventions already established in `inference_proxy/api/admin.py`.

The entire scope is: two Pydantic models, two route handlers, error mapping from `RedfishError` to HTTP status codes, and tests. The codebase already has every building block.

**Primary recommendation:** Add models to `inference_proxy/models/admin.py`, add route handlers to `inference_proxy/api/admin.py`, add tests to `tests/api/test_admin.py`. No new files needed unless SRP argues for a `power.py` router (discretion item).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use bare hostname as URL path parameter (e.g., `/admin/nodes/{hostname}/power`)
- **D-02:** Apply `canonical_hostname()` normalization on the path parameter -- same as setup endpoint
- **D-03:** Works on unprovisioned hosts -- no etcd registration required for power operations
- **D-04:** Single resource model: GET `/admin/nodes/{hostname}/power` returns current power state, POST `/admin/nodes/{hostname}/power` with `{"action": "On"}` executes action
- **D-05:** POST response returns final state only: `{"hostname": "x", "power_state": "On"}` -- synchronous, blocks until RedfishClient polling completes
- **D-06:** Expose Redfish actions directly: On, ForceOff, GracefulRestart, ForceRestart -- no alias translation layer
- **D-07:** Return 503 when `get_redfish_client` yields None (Redfish not configured)

### Claude's Discretion
- Pydantic request/response model design (PowerActionRequest, PowerStateResponse)
- Error mapping from RedfishError to HTTP status codes (400/503/etc.)
- Whether to add power endpoints to existing `admin.py` or create a separate `power.py` router file (SOLID SRP consideration)

### Deferred Ideas (OUT OF SCOPE)
None

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PWR-01 | User can power on a node via Redfish API from the admin endpoint | POST handler calls `RedfishClient.power_action(hostname, "On")` -- method exists and is tested |
| PWR-02 | User can power off a node via Redfish API from the admin endpoint | POST handler calls `RedfishClient.power_action(hostname, "ForceOff")` -- method exists and is tested |
| PWR-03 | User can restart a node via Redfish API from the admin endpoint | POST handler calls `RedfishClient.power_action(hostname, "GracefulRestart")` or `"ForceRestart"` -- both supported |
| PWR-04 | User can query the current power state of a node | GET handler calls `RedfishClient.get_power_state(hostname)` -- method exists and is tested |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Power state query | API / Backend | -- | Admin API endpoint delegates to RedfishClient |
| Power action execution | API / Backend | -- | Admin API endpoint delegates to RedfishClient, which talks to BMC |
| Request validation | API / Backend | -- | Pydantic model validates action enum in request body |
| Error translation | API / Backend | -- | Route handler maps RedfishError to HTTP 400/500/503 |

## Standard Stack

No new packages. Everything needed is already installed:

| Library | Role in This Phase | Already Installed |
|---------|-------------------|-------------------|
| FastAPI | Route handlers, `Depends()`, `HTTPException` | Yes |
| Pydantic | Request/response models | Yes |
| httpx | Used by RedfishClient (no direct use in endpoints) | Yes |
| pytest / pytest-httpx | Testing | Yes |

**Installation:** None required.

## Architecture Patterns

### System Flow

```
Client POST /admin/nodes/{hostname}/power {"action": "On"}
  |
  v
admin_router handler
  |-- canonical_hostname(hostname)          # normalize
  |-- get_redfish_client via Depends()      # DI
  |   |-- None? -> 503                      # not configured
  |-- redfish.power_action(hostname, action)  # delegates to Phase 21 client
  |   |-- RedfishError? -> map to 400/500
  |-- return PowerActionResponse(hostname=..., power_state=final_state)
```

### Recommended Approach: Extend existing admin.py

The admin router currently has 6 endpoints and ~170 lines. Adding 2 more keeps it under 250 lines -- well within "single module" territory. Creating a separate `power.py` router is defensible for SRP but adds a file, an import in `main.py`, and router mounting for two functions. The lazy choice: keep them in `admin.py` unless the implementer finds it crowded. [ASSUMED -- discretion item]

### Pattern: Pydantic Models (matching existing conventions)

All models in `models/admin.py` use `model_config = ConfigDict(frozen=True)`. New models must follow suit. [VERIFIED: codebase inspection]

```python
# Source: inference_proxy/models/admin.py (existing convention)
from enum import Enum
from pydantic import BaseModel, ConfigDict

class PowerAction(str, Enum):
    """Allowed Redfish reset actions (D-06)."""
    ON = "On"
    FORCE_OFF = "ForceOff"
    GRACEFUL_RESTART = "GracefulRestart"
    FORCE_RESTART = "ForceRestart"

class PowerActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    action: PowerAction

class PowerStateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    hostname: str
    power_state: str
```

Using a `str, Enum` for `PowerAction` gives automatic 422 validation when the client sends an invalid action -- FastAPI + Pydantic handle this with zero custom code. The enum values match `_ACTION_TARGET_STATE` keys in `redfish/client.py` exactly. [VERIFIED: codebase inspection]

### Pattern: Error Mapping from RedfishError to HTTP

`RedfishError` carries a `human_message: str`. The endpoint needs to map it to HTTP status codes:

| RedfishError cause | HTTP status | Rationale |
|--------------------|-------------|-----------|
| Invalid action (caught by Pydantic enum) | 422 | FastAPI automatic validation |
| BMC connection refused / timeout | 502 | Upstream (BMC) unreachable |
| BMC returns 4xx (bad request, auth) | 400 | Client-actionable error |
| BMC returns 5xx (internal error) | 500 | Server error, pass through |
| Poll timeout (state never reached) | 504 | Gateway timeout waiting for BMC |
| Redfish not configured (client is None) | 503 | Service unavailable |

Simplification: Since `RedfishError` doesn't distinguish connection vs. BMC errors today, a single `except RedfishError` -> 502 is the pragmatic choice. The `human_message` already contains useful text. Splitting error types can happen later if operators need different retry logic per status code. [ASSUMED -- discretion item]

### Pattern: Route Handler (matching existing conventions)

```python
# Source: inference_proxy/api/admin.py (existing pattern)
@admin_router.get("/nodes/{hostname}/power")
async def get_power_state(
    hostname: str,
    redfish: RedfishClient | None = Depends(get_redfish_client),
) -> PowerStateResponse:
    if redfish is None:
        raise HTTPException(status_code=503, detail="Redfish not configured")
    hostname = canonical_hostname(hostname)
    try:
        state = await redfish.get_power_state(hostname)
    except RedfishError as exc:
        raise HTTPException(status_code=502, detail=exc.human_message) from exc
    return PowerStateResponse(hostname=hostname, power_state=state)
```

POST handler is identical in structure, calling `redfish.power_action(hostname, body.action.value)` instead. [VERIFIED: codebase pattern match]

### Anti-Patterns to Avoid
- **Creating a service layer for two pass-through functions:** The handlers directly call RedfishClient methods. No intermediate "PowerService" class -- that's a factory for one product.
- **Re-validating actions in the handler:** The Pydantic `PowerAction` enum already rejects invalid actions with a 422. Don't add a redundant `if action not in ...` check.
- **Async background for power actions:** D-05 says synchronous response. Don't use `fire_background()` here -- power actions are fast enough (poll timeout defaults to 60s, typical is <10s).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Action validation | `if action not in [...]` check | `PowerAction(str, Enum)` in Pydantic model | FastAPI auto-returns 422 with clear error message |
| Hostname normalization | Inline `.strip().lower()` | `canonical_hostname()` from `quads/client.py` | Already exists, already tested, used by setup endpoint |
| DI for Redfish client | Manual `app.state` access | `Depends(get_redfish_client)` | Existing provider, testable via `dependency_overrides` |

## Common Pitfalls

### Pitfall 1: Forgetting canonical_hostname on the path parameter
**What goes wrong:** Hostname "GPU01" and "gpu01" are treated as different hosts.
**Why it happens:** Path parameters come in as-is from the URL.
**How to avoid:** Apply `canonical_hostname()` before any RedfishClient call (D-02).
**Warning signs:** Tests pass with lowercase but BMC lookup fails with mixed case.

### Pitfall 2: Not handling None redfish client
**What goes wrong:** `AttributeError: 'NoneType' has no attribute 'get_power_state'` at runtime.
**Why it happens:** `get_redfish_client` returns None when Redfish is not configured (no BMC settings).
**How to avoid:** Guard with `if redfish is None: raise HTTPException(503)` before any client call (D-07).
**Warning signs:** 500 errors in environments without Redfish configured.

### Pitfall 3: Using enum name instead of enum value
**What goes wrong:** Passing `"FORCE_OFF"` to `RedfishClient.power_action()` instead of `"ForceOff"`.
**Why it happens:** Python enum `.name` vs `.value` confusion.
**How to avoid:** Use `body.action.value` (the string "ForceOff") when calling the client. Or use `body.action` directly since `PowerAction` is a `str` enum (its string representation IS the value).
**Warning signs:** `RedfishError: Unsupported action: FORCE_OFF`.

### Pitfall 4: Test fixture doesn't override get_redfish_client
**What goes wrong:** Tests get `None` for the redfish client (conftest default), every test returns 503.
**Why it happens:** `conftest.py` sets `get_redfish_client` override to `lambda: None`.
**How to avoid:** Power endpoint tests must override `get_redfish_client` with a mock `RedfishClient`.
**Warning signs:** All power tests return 503 regardless of test intent.

## Code Examples

### GET Power State Handler
```python
# Source: follows pattern from inference_proxy/api/admin.py setup_node
@admin_router.get("/nodes/{hostname}/power")
async def get_power_state(
    hostname: str,
    redfish: RedfishClient | None = Depends(get_redfish_client),
) -> PowerStateResponse:
    if redfish is None:
        raise HTTPException(status_code=503, detail="Redfish not configured")
    hostname = canonical_hostname(hostname)
    try:
        state = await redfish.get_power_state(hostname)
    except RedfishError as exc:
        raise HTTPException(status_code=502, detail=exc.human_message) from exc
    return PowerStateResponse(hostname=hostname, power_state=state)
```

### POST Power Action Handler
```python
# Source: follows pattern from inference_proxy/api/admin.py setup_node
@admin_router.post("/nodes/{hostname}/power")
async def execute_power_action(
    hostname: str,
    body: PowerActionRequest,
    redfish: RedfishClient | None = Depends(get_redfish_client),
) -> PowerStateResponse:
    if redfish is None:
        raise HTTPException(status_code=503, detail="Redfish not configured")
    hostname = canonical_hostname(hostname)
    try:
        final_state = await redfish.power_action(hostname, body.action.value)
    except RedfishError as exc:
        raise HTTPException(status_code=502, detail=exc.human_message) from exc
    return PowerStateResponse(hostname=hostname, power_state=final_state)
```

### Test Pattern (mock RedfishClient via DI override)
```python
# Source: follows pattern from tests/api/test_admin.py TestSetupQuadsRevalidation
class TestGetPowerState:
    def test_returns_current_state(
        self, app: FastAPI, client: TestClient
    ) -> None:
        mock_redfish = AsyncMock()
        mock_redfish.get_power_state.return_value = "On"
        app.dependency_overrides[get_redfish_client] = lambda: mock_redfish

        response = client.get("/admin/nodes/gpu01/power")
        assert response.status_code == 200
        assert response.json() == {"hostname": "gpu01", "power_state": "On"}

    def test_returns_503_when_not_configured(
        self, client: TestClient
    ) -> None:
        # Default conftest has redfish=None
        response = client.get("/admin/nodes/gpu01/power")
        assert response.status_code == 503
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4.x |
| Config file | `pyproject.toml` (pytest section) |
| Quick run command | `uv run pytest tests/api/test_admin.py -x -q` |
| Full suite command | `uv run pytest --tb=short` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PWR-01 | POST with action=On returns 200 + final state | unit | `uv run pytest tests/api/test_admin.py -k "power_on" -x` | No -- Wave 0 |
| PWR-02 | POST with action=ForceOff returns 200 + final state | unit | `uv run pytest tests/api/test_admin.py -k "power_off" -x` | No -- Wave 0 |
| PWR-03 | POST with action=GracefulRestart returns 200 + final state | unit | `uv run pytest tests/api/test_admin.py -k "restart" -x` | No -- Wave 0 |
| PWR-04 | GET returns current power state | unit | `uv run pytest tests/api/test_admin.py -k "get_power" -x` | No -- Wave 0 |
| D-07 | Both endpoints return 503 when redfish is None | unit | `uv run pytest tests/api/test_admin.py -k "503" -x` | No -- Wave 0 |
| D-02 | Hostname normalization applied | unit | `uv run pytest tests/api/test_admin.py -k "canonical" -x` | No -- Wave 0 |
| Error | RedfishError maps to 502 | unit | `uv run pytest tests/api/test_admin.py -k "redfish_error" -x` | No -- Wave 0 |
| Validation | Invalid action returns 422 | unit | `uv run pytest tests/api/test_admin.py -k "invalid_action" -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/api/test_admin.py -x -q`
- **Per wave merge:** `uv run pytest --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Power endpoint tests in `tests/api/test_admin.py` -- covers PWR-01 through PWR-04, D-07, D-02
- No new framework install or conftest changes needed -- `conftest.py` already has `get_redfish_client` override infrastructure

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Internal-only admin API, no auth in v1 |
| V3 Session Management | No | Stateless request |
| V4 Access Control | No | Internal network only (CLAUDE.md constraint) |
| V5 Input Validation | Yes | Pydantic `PowerAction` enum validates action; `canonical_hostname()` normalizes hostname |
| V6 Cryptography | No | No crypto in endpoint layer |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Arbitrary hostname -> BMC access | Tampering | `canonical_hostname()` normalization; BMC template constrains target |
| Invalid reset action injection | Tampering | Pydantic enum rejects at 422 before reaching client |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Keep endpoints in existing `admin.py` rather than creating `power.py` | Architecture Patterns | Minor -- just file organization, easy to split later |
| A2 | Map all RedfishError to HTTP 502 (single catch) rather than splitting by cause | Architecture Patterns | Low -- operators lose granularity on error source, but `human_message` text compensates |

## Open Questions

None. The scope is fully constrained by CONTEXT.md decisions and the existing RedfishClient API surface.

## Sources

### Primary (HIGH confidence)
- `inference_proxy/api/admin.py` -- existing admin router patterns (6 endpoints, DI, error handling)
- `inference_proxy/models/admin.py` -- existing Pydantic model conventions (frozen, field_validator)
- `inference_proxy/redfish/client.py` -- RedfishClient API surface (`get_power_state`, `power_action`, `_ACTION_TARGET_STATE`)
- `inference_proxy/redfish/errors.py` -- RedfishError with `human_message` attribute
- `inference_proxy/config/dependencies.py` -- `get_redfish_client` DI provider returning `RedfishClient | None`
- `tests/conftest.py` -- test fixture patterns, `get_redfish_client` override to None
- `tests/api/test_admin.py` -- admin endpoint test patterns using `dependency_overrides`
- `tests/redfish/test_client.py` -- RedfishClient test patterns using `pytest_httpx`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new packages, all existing
- Architecture: HIGH -- direct extension of existing admin API pattern
- Pitfalls: HIGH -- identified from codebase inspection, all verifiable

**Research date:** 2026-07-22
**Valid until:** 2026-08-22 (stable -- no external dependencies or API changes expected)
