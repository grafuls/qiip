# Phase 21: Redfish Client & Configuration - Research

**Researched:** 2026-07-21
**Domain:** Redfish BMC power management client (REST over HTTPS with Basic auth)
**Confidence:** HIGH

## Summary

Phase 21 builds a thin Redfish REST client for querying power state and issuing power actions (On, ForceOff, GracefulRestart, ForceRestart) to server BMCs, plus the configuration sub-model and dependency injection wiring. The entire phase uses zero new dependencies -- httpx (already installed, >=0.28) handles the HTTP calls with BasicAuth and `verify=False`, pydantic-settings handles configuration with `SecretStr` for credential masking, and structlog handles logging. The implementation mirrors the existing `QUADSClient` pattern exactly: constructor-injected `httpx.AsyncClient`, typed exception class, async methods.

The Redfish API surface for this phase is small: `GET /redfish/v1/Systems/{id}` for power state, `POST /redfish/v1/Systems/{id}/Actions/ComputerSystem.Reset` for power actions. The complexity is operational, not architectural: BMC power actions are not idempotent (ForceOff on an off server returns HTTP 400), power state transitions are asynchronous (HTTP 200 means "accepted" not "done"), and BMC credentials leak easily without `SecretStr`. All three issues have well-documented mitigations from MAAS and Ironic.

**Primary recommendation:** Mirror `QUADSClient` structure exactly. Dedicated `httpx.AsyncClient` with `verify=False`, `BasicAuth`, and Redfish-specific timeouts (10s connect, 60s read). Check-before-act for idempotency, post-action polling for async transitions.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** BMC hostnames follow the `mgmt-{hostname}` pattern (e.g., server01 -> mgmt-server01)
- **D-02:** Fleet-wide template via `INFERENCE_PROXY_REDFISH__BMC_HOST_TEMPLATE` env var -- no per-host overrides
- **D-03:** Check-before-act with silent success -- query PowerState before issuing reset actions; if already in desired state, return success without hitting the reset endpoint
- **D-04:** Power actions poll PowerState until the target state is confirmed, with configurable timeout -- the client handles the async transition internally so callers get a definitive result
- **D-05:** Always `verify=False` for BMC connections -- no CA bundle support needed (self-signed certs are the norm)
- **D-06:** Suppress urllib3/httpx InsecureRequestWarning entirely -- `verify=False` is intentional, not accidental

### Claude's Discretion
- Error message mapping approach for DIAG-03 (static dict of common Redfish MessageIds -> human-readable text, with generic fallback extraction for unknown errors)
- RedfishClient internal structure (mirrors QUADSClient: constructor-injected httpx.AsyncClient, typed RedfishError exception)
- RedfishSettings sub-model fields and defaults (username, password as SecretStr, system_id, timeouts)
- Dependency injection wiring in dependencies.py (get_redfish_client provider)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIAG-03 | Redfish error responses are mapped to human-readable messages | Static dict mapping common Redfish Base registry MessageIds to operator-friendly text, generic fallback extracts `Message` from `@Message.ExtendedInfo`, caps at 200 chars. Pattern follows `map_proxy_error()` in `errors.py`. |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **SOLID principles required** -- all code must follow SRP, OCP, LSP, ISP, DIP. RedfishClient gets constructor-injected httpx.AsyncClient (DIP). Error mapping is a separate function (SRP).
- **Tech stack**: Python, FastAPI, httpx, pydantic-settings -- all already installed
- **Internal network only** -- `verify=False` acceptable for BMC self-signed certs
- **No new dependencies** -- httpx covers Redfish REST, pydantic SecretStr covers credential masking

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Redfish HTTP calls | API / Backend | -- | Server-to-BMC REST calls, internal network only |
| BMC credential storage | Configuration | -- | pydantic-settings env var injection, SecretStr masking |
| Power state query | API / Backend | -- | GET to BMC, returns PowerState enum |
| Power action dispatch | API / Backend | -- | POST to BMC, check-before-act + poll |
| Error message mapping | API / Backend | -- | Static dict + fallback extraction, pure function |
| Dependency injection | Configuration | API / Backend | get_redfish_client provider in dependencies.py |

## Standard Stack

### Core (all existing -- zero new installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| httpx | >=0.28 (installed) | Redfish REST client | Already the proxy engine. Native async, BasicAuth, `verify=False`, connection pooling. [VERIFIED: pyproject.toml] |
| pydantic | >=2.10 (installed) | SecretStr for credentials, frozen response models | Already a core dependency. SecretStr masks in repr/str/model_dump. [VERIFIED: pyproject.toml] |
| pydantic-settings | >=2.14 (installed) | RedfishSettings sub-model with env var injection | Already used for all settings. Nested delimiter `__` for `INFERENCE_PROXY_REDFISH__*`. [VERIFIED: pyproject.toml] |
| structlog | >=26.1.0 (installed) | Structured logging for Redfish operations | Already used everywhere. JSON output in prod, console in dev. [VERIFIED: pyproject.toml] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| httpx + BasicAuth | `redfish` (DMTF library) | DMTF lib is sync (`requests`-based), adds 6 transitive deps, overkill for 2 endpoints. [CITED: .planning/research/SUMMARY.md] |
| httpx + BasicAuth | `sushy` (OpenStack) | OpenStack dependency ecosystem, designed for Ironic drivers, massive overkill. [CITED: .planning/research/SUMMARY.md] |
| Static error dict | Fetch Base registry from BMC at runtime | Over-engineered for ~10 common errors. Registry fetching adds latency and complexity. |

**Installation:** None required. All dependencies already in `pyproject.toml`.

## Architecture Patterns

### System Architecture Diagram

```
Caller (admin endpoint / provisioner)
    |
    v
RedfishClient
    |-- get_power_state(hostname) --> resolve_bmc_host() --> GET /redfish/v1/Systems/{id}
    |                                                            |
    |                                                            v
    |                                                     Parse PowerState
    |                                                     (On/Off/PoweringOn/PoweringOff)
    |
    |-- power_action(hostname, action) --> get_power_state() --> [check-before-act]
                                              |                       |
                                              |  already desired? --> return success (silent)
                                              |
                                              v
                                         POST .../Actions/ComputerSystem.Reset
                                              |
                                              v
                                         poll_power_state() --> loop until target or timeout
                                              |
                                              v
                                         return final PowerState

Error path:
    httpx.HTTPStatusError --> parse @Message.ExtendedInfo --> map MessageId --> RedfishError(human_msg)
```

### Recommended Project Structure

```
inference_proxy/
  redfish/
    __init__.py          # Module init
    client.py            # RedfishClient class (mirrors quads/client.py)
    errors.py            # RedfishError exception + REDFISH_ERROR_MAP + extract_error_message()
  config/
    settings.py          # Add RedfishSettings sub-model to existing file
    dependencies.py      # Add get_redfish_client provider to existing file
  main.py                # Add Redfish httpx.AsyncClient creation in lifespan

tests/
  redfish/
    __init__.py
    test_client.py       # Power state, power actions, idempotency, polling, error mapping
```

### Pattern 1: Constructor-Injected Async Client (QUADSClient analog)

**What:** Thin httpx wrapper with injected AsyncClient for testability (DIP).
**When to use:** Every external HTTP service integration in this codebase.
**Example:**
```python
# Source: inference_proxy/quads/client.py (existing pattern)
class RedfishClient:
    def __init__(self, http_client: httpx.AsyncClient, bmc_host_template: str, system_id: str) -> None:
        self._client = http_client
        self._bmc_host_template = bmc_host_template
        self._system_id = system_id

    def _resolve_bmc_host(self, hostname: str) -> str:
        return self._bmc_host_template.format(hostname=hostname)

    async def get_power_state(self, hostname: str) -> str:
        bmc = self._resolve_bmc_host(hostname)
        url = f"https://{bmc}/redfish/v1/Systems/{self._system_id}"
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RedfishError(_extract_error_message(exc)) from exc
        return resp.json()["PowerState"]
```

### Pattern 2: Check-Before-Act Idempotency (D-03)

**What:** Query current state before issuing action, skip if already in desired state.
**When to use:** All power actions -- BMCs return HTTP 400 on no-op actions. [CITED: PITFALLS.md Pitfall 1]
**Example:**
```python
# Source: DMTF Redfish spec behavior documented in PITFALLS.md
_ACTION_TARGET_STATE: dict[str, str] = {
    "On": "On",
    "ForceOff": "Off",
    "GracefulRestart": "On",
    "ForceRestart": "On",
}

async def power_action(self, hostname: str, action: str, *, timeout: float = 60.0) -> str:
    target = _ACTION_TARGET_STATE[action]
    current = await self.get_power_state(hostname)
    if current == target:
        return current  # ponytail: silent success, skip BMC call
    await self._post_reset(hostname, action)
    return await self._poll_power_state(hostname, target, timeout)
```

### Pattern 3: Post-Action Polling (D-04)

**What:** After issuing a reset action, poll PowerState until target state or timeout.
**When to use:** Every power action -- HTTP 200 from Redfish means "accepted" not "done". [CITED: PITFALLS.md Pitfall 7]
**Example:**
```python
# Source: DMTF Redfish spec + PITFALLS.md Pitfall 7
async def _poll_power_state(self, hostname: str, target: str, timeout: float) -> str:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        state = await self.get_power_state(hostname)
        if state == target:
            return state
        await asyncio.sleep(self._poll_interval)
    raise RedfishError(f"Power state did not reach {target} within {timeout}s")
```

### Pattern 4: Redfish Error Message Extraction (DIAG-03)

**What:** Parse Redfish `@Message.ExtendedInfo` and map MessageIds to human-readable text.
**When to use:** All Redfish errors before surfacing to callers. [CITED: DMTF DSP0266 error response format]
**Example:**
```python
# Source: DMTF Redfish spec DSP0266 + PITFALLS.md Pitfall 5
REDFISH_ERROR_MAP: dict[str, str] = {
    "ActionNotSupported": "This action is not supported by the BMC",
    "ActionParameterNotSupported": "This action parameter is not supported",
    "ResourceNotFound": "BMC resource not found -- check system ID",
    "InternalError": "BMC internal error -- retry or check BMC health",
    "ServiceTemporarilyUnavailable": "BMC is temporarily busy -- retry later",
    "NoOperation": "No change needed -- system already in requested state",
    "InsufficientPrivilege": "BMC credentials lack permission for this action",
    "PropertyValueTypeError": "Invalid parameter value in request",
}

def _extract_error_message(exc: Exception) -> str:
    """Extract human-readable message from Redfish error or httpx exception."""
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            body = exc.response.json()
            ext_info = body.get("error", {}).get("@Message.ExtendedInfo", [])
            if ext_info:
                msg_id = ext_info[0].get("MessageId", "")
                # Extract MessageKey (last segment): "Base.1.12.ActionNotSupported" -> "ActionNotSupported"
                key = msg_id.rsplit(".", 1)[-1] if msg_id else ""
                if key in REDFISH_ERROR_MAP:
                    return REDFISH_ERROR_MAP[key]
                # Fallback: use the Message field from ExtendedInfo
                return ext_info[0].get("Message", str(exc))[:200]
            # Fallback: use top-level message
            return body.get("error", {}).get("message", str(exc))[:200]
        except Exception:
            pass
    return str(exc)[:200]
```

### Pattern 5: Optional Feature via None Settings (QUADSSettings analog)

**What:** Redfish disabled when `bmc_username` is None. Same pattern as QUADS.
**When to use:** Features that not all deployments need. [VERIFIED: inference_proxy/config/settings.py QUADSSettings]
**Example:**
```python
# Source: inference_proxy/config/settings.py (existing pattern)
class RedfishSettings(BaseModel):
    bmc_username: str | None = None  # None = Redfish disabled
    bmc_password: SecretStr | None = None
    bmc_host_template: str = "mgmt-{hostname}"  # D-01, D-02
    system_id: str = "1"  # ponytail: hardcode "1", configurable for multi-vendor
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    power_poll_timeout: float = 60.0
    power_poll_interval: float = 5.0
    verify_ssl: bool = False  # D-05: always False for self-signed BMC certs
```

### Anti-Patterns to Avoid

- **Sharing httpx.AsyncClient across subsystems:** The Redfish client must have its own `httpx.AsyncClient` with `verify=False` and Redfish-specific timeouts. Do not reuse the proxy client or QUADS client. [CITED: PITFALLS.md Pitfall 4]
- **Embedding credentials in URLs:** Never `https://user:pass@bmc-host/redfish/...`. Use httpx `auth` parameter. [CITED: PITFALLS.md Pitfall 2]
- **Using Redfish sessions instead of Basic auth:** Sessions create server-side state, BMCs limit to 4-16 concurrent sessions, leaked sessions cause lockouts. Basic auth is stateless. [CITED: PITFALLS.md Pitfall 6]
- **Treating HTTP 200 from power actions as "done":** Redfish 200 means "accepted". Must poll PowerState for confirmation. [CITED: PITFALLS.md Pitfall 7]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| BMC credential masking | Custom log sanitizer | Pydantic `SecretStr` | Masks in repr, str, model_dump automatically. [CITED: Pydantic docs] |
| HTTP Basic auth | Manual `Authorization` header | `httpx.BasicAuth(username, password)` | Handles encoding, works per-client or per-request. [CITED: httpx auth docs] |
| SSL verification bypass | Custom transport/adapter | `httpx.AsyncClient(verify=False)` | httpx does not emit InsecureRequestWarning (uses httpcore, not urllib3). [ASSUMED -- multiple sources agree httpx != urllib3] |
| Redfish error parsing | Full registry client | Static dict + fallback `Message` extraction | ~10 common errors cover 95% of cases. Full registry is overkill. |
| Async polling loop | Custom thread/timer | `asyncio.sleep()` in a while loop with deadline | Simple, testable, no extra deps. |

**Key insight:** The Redfish API surface is trivially small (1 GET, 1 POST). The complexity is in operational edge cases (idempotency, async transitions, credential safety), not HTTP plumbing.

## Common Pitfalls

### Pitfall 1: ForceOff on Already-Off Server Returns HTTP 400

**What goes wrong:** BMCs reject power actions that are no-ops relative to current state. ForceOff on an off server, On on an on server -- HTTP 400. Most Redfish integration bugs trace to this.
**Why it happens:** Developers assume power actions are idempotent ("make it off"). They are imperative ("turn it off now").
**How to avoid:** D-03 locks this: check-before-act. Query PowerState, skip if already in desired state. Handle 400 as soft error: re-check state, treat as success if desired state reached.
**Warning signs:** Tests pass with mock BMCs but fail against real hardware. [CITED: PITFALLS.md Pitfall 1]

### Pitfall 2: BMC Credentials Leak into Logs

**What goes wrong:** BMC password appears in structlog output, etcd state records, or error messages.
**Why it happens:** `str(exc)` on httpx errors includes request context. Settings model logged at startup.
**How to avoid:** `SecretStr` for password. Never include RedfishSettings in structlog binds. Never embed creds in URLs. Sanitize error messages before writing to any persistent store.
**Warning signs:** `model_dump()` on settings shows plaintext password. [CITED: PITFALLS.md Pitfall 2]

### Pitfall 3: TLS verify=False Leaks to Other Clients

**What goes wrong:** Redfish client shares httpx.AsyncClient with proxy or QUADS client, disabling TLS verification for all outbound requests.
**Why it happens:** Developer reuses existing client or creates global `verify=False` setting.
**How to avoid:** Dedicated httpx.AsyncClient for Redfish with `verify=False` scoped to it only. Created in lifespan, stored separately in app.state. [CITED: PITFALLS.md Pitfall 4]
**Warning signs:** `verify=False` appears on any client other than Redfish.

### Pitfall 4: Async Transitions Treated as Synchronous

**What goes wrong:** Power action returns HTTP 200 but server hasn't transitioned yet. Next step assumes new state.
**Why it happens:** HTTP 200 universally means "done" -- Redfish breaks this convention. 200 means "accepted".
**How to avoid:** D-04 locks this: poll PowerState after every action. Handle transitional states (PoweringOn, PoweringOff) as "in progress, keep polling". [CITED: PITFALLS.md Pitfall 7]
**Warning signs:** Power actions "work" on fast hardware but fail on slow-booting servers.

### Pitfall 5: httpx Timeouts Too Short for BMC Response Times

**What goes wrong:** Proxy-tuned timeouts (5s connect) too aggressive for BMCs under load. BMCs can take 30-60s during sensor cache rebuilds or firmware updates.
**Why it happens:** Developers set timeouts for healthy BMC response times, not degraded states.
**How to avoid:** Redfish-specific timeouts: 10s connect, 60s read. Handle HTTP 503 from BMC as retryable. [CITED: PITFALLS.md Pitfall 10]
**Warning signs:** Intermittent "BMC unreachable" on servers that respond fine from curl.

## Code Examples

### RedfishSettings Sub-Model

```python
# Source: follows inference_proxy/config/settings.py QUADSSettings pattern
from pydantic import BaseModel, SecretStr

class RedfishSettings(BaseModel):
    """Redfish BMC configuration.

    When ``bmc_username`` is ``None`` (the default), Redfish features
    are disabled. Setting it via ``INFERENCE_PROXY_REDFISH__BMC_USERNAME``
    activates the Redfish integration.
    """
    bmc_username: str | None = None
    bmc_password: SecretStr | None = None
    bmc_host_template: str = "mgmt-{hostname}"  # D-01, D-02
    system_id: str = "1"
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    power_poll_timeout: float = 60.0
    power_poll_interval: float = 5.0
    verify_ssl: bool = False  # D-05
```

### Redfish httpx.AsyncClient Creation in Lifespan

```python
# Source: follows inference_proxy/main.py QUADS client creation pattern
# In lifespan, after QUADS client block:
if resolved_settings.redfish.bmc_username is not None:
    redfish_http = httpx.AsyncClient(
        auth=httpx.BasicAuth(
            username=resolved_settings.redfish.bmc_username,
            password=resolved_settings.redfish.bmc_password.get_secret_value(),
        ),
        verify=resolved_settings.redfish.verify_ssl,  # D-05: False
        timeout=httpx.Timeout(
            connect=resolved_settings.redfish.connect_timeout,
            read=resolved_settings.redfish.read_timeout,
            write=10.0,
            pool=10.0,
        ),
    )
    redfish_client = RedfishClient(
        redfish_http,
        bmc_host_template=resolved_settings.redfish.bmc_host_template,
        system_id=resolved_settings.redfish.system_id,
        poll_timeout=resolved_settings.redfish.power_poll_timeout,
        poll_interval=resolved_settings.redfish.power_poll_interval,
    )
    app.state.redfish_client = redfish_client
else:
    app.state.redfish_client = None
    redfish_http = None

# In shutdown:
if redfish_http is not None:
    await redfish_http.aclose()
```

### Dependency Injection Provider

```python
# Source: follows inference_proxy/config/dependencies.py get_quads_client pattern
def get_redfish_client(request: Request) -> RedfishClient | None:
    """Return the Redfish client, or None when Redfish is not configured."""
    return request.app.state.redfish_client
```

### Warning Suppression (D-06)

```python
# httpx uses httpcore, not urllib3 -- so InsecureRequestWarning is NOT emitted.
# D-06 is satisfied by default with httpx. No explicit suppression needed.
# If any transitive dep triggers warnings, scope the filter narrowly:
import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request", module="httpx")
```

### Test Pattern (mirrors tests/quads/test_client.py)

```python
# Source: follows tests/quads/test_client.py pattern with pytest-httpx
import httpx
import pytest
from pytest_httpx import HTTPXMock

class TestGetPowerState:
    async def test_returns_on(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url="https://mgmt-server01/redfish/v1/Systems/1",
            json={"PowerState": "On"},
        )
        async with httpx.AsyncClient() as client:
            rc = RedfishClient(client, bmc_host_template="mgmt-{hostname}", system_id="1")
            state = await rc.get_power_state("server01")
        assert state == "On"

class TestPowerActionIdempotent:
    async def test_skip_if_already_on(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url="https://mgmt-server01/redfish/v1/Systems/1",
            json={"PowerState": "On"},
        )
        async with httpx.AsyncClient() as client:
            rc = RedfishClient(client, bmc_host_template="mgmt-{hostname}", system_id="1")
            state = await rc.power_action("server01", "On")
        assert state == "On"
        # Only 1 request made (GET power state), no POST reset
        assert len(httpx_mock.get_requests()) == 1
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `redfish` (DMTF) + `requests` (sync) | httpx (async, native BasicAuth) | httpx 0.28+ (Dec 2024) | No sync-to-async bridge needed |
| Redfish sessions (4-16 limit) | Basic auth (stateless) | Always valid for simple ops | No session exhaustion risk |
| `urllib3` SSL warnings | httpx uses httpcore (no warnings) | httpx architecture | D-06 satisfied by default |

**Deprecated/outdated:**
- `python-redfish-library` (DMTF): sync-only, `requests`-based. Still maintained but wrong fit for async codebase.
- Redfish session auth for simple operations: Creates server-side state with 4-16 session limit. Basic auth is simpler and safer.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | httpx does not emit InsecureRequestWarning when verify=False (uses httpcore, not urllib3) | Don't Hand-Roll, Warning Suppression | LOW -- if wrong, add a one-line `warnings.filterwarnings` call. Multiple sources confirm httpx != urllib3. |
| A2 | system_id default of "1" works for Dell iDRAC, HPE iLO, and Supermicro BMCs | RedfishSettings | MEDIUM -- some blade/chassis servers use UUIDs. Mitigated by making system_id configurable. |
| A3 | ~10 common Base registry MessageIds cover 95% of operator-facing errors | Error mapping | LOW -- generic fallback extracts Message field for unknown IDs. Worst case: operator sees the raw Message text instead of a curated one. |

## Open Questions

1. **Warning suppression scope (D-06)**
   - What we know: httpx uses httpcore, not urllib3, so `InsecureRequestWarning` is not emitted by httpx itself.
   - What's unclear: Whether any transitive dependency in the stack triggers warnings when httpx makes `verify=False` requests.
   - Recommendation: Build without suppression. If warnings appear in testing, add scoped `warnings.filterwarnings` targeting the specific module.

2. **System ID for actual fleet hardware**
   - What we know: Dell uses `System.Embedded.1`, most others use `1`. The setting defaults to `"1"`.
   - What's unclear: What the actual lab fleet uses.
   - Recommendation: Default `"1"`, validate against real hardware during Phase 22 (admin endpoints hit real BMCs). The field is configurable per D-02.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 + pytest-asyncio >=1.4 + pytest-httpx >=0.36 |
| Config file | `pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `uv run pytest tests/redfish/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DIAG-03 (power state) | get_power_state returns On/Off/PoweringOn/PoweringOff | unit | `uv run pytest tests/redfish/test_client.py::TestGetPowerState -x` | No -- Wave 0 |
| DIAG-03 (power action) | power_action issues correct ResetType | unit | `uv run pytest tests/redfish/test_client.py::TestPowerAction -x` | No -- Wave 0 |
| DIAG-03 (idempotency) | power_action skips if already in target state (D-03) | unit | `uv run pytest tests/redfish/test_client.py::TestPowerActionIdempotent -x` | No -- Wave 0 |
| DIAG-03 (polling) | power_action polls until target state (D-04) | unit | `uv run pytest tests/redfish/test_client.py::TestPowerStatePoll -x` | No -- Wave 0 |
| DIAG-03 (error mapping) | Redfish errors mapped to human-readable text | unit | `uv run pytest tests/redfish/test_client.py::TestErrorMapping -x` | No -- Wave 0 |
| DIAG-03 (credential safety) | SecretStr masks password in model_dump/repr | unit | `uv run pytest tests/config/test_settings.py::TestRedfishSettings -x` | No -- Wave 0 |
| Success Criteria 4 | Credentials never in logs/errors/responses | unit | `uv run pytest tests/redfish/test_client.py::TestCredentialSafety -x` | No -- Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/redfish/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/redfish/__init__.py` -- package init
- [ ] `tests/redfish/test_client.py` -- covers all DIAG-03 behaviors
- [ ] `tests/config/test_settings.py` -- add RedfishSettings tests (file exists, tests don't)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | httpx.BasicAuth over HTTPS (BMC auth) |
| V3 Session Management | No | Basic auth is stateless, no sessions |
| V4 Access Control | No | Handled by existing admin endpoint auth |
| V5 Input Validation | Yes | Pydantic model validation on ResetType |
| V6 Cryptography | No | TLS handled by httpx, no custom crypto |

### Known Threat Patterns for Redfish Client

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential exposure in logs | Information Disclosure | Pydantic SecretStr, never log RedfishSettings |
| Credential exposure in error messages | Information Disclosure | Sanitize error strings, cap at 200 chars, never embed creds in URLs |
| MITM on management VLAN | Tampering / Spoofing | Accepted risk per D-05 (self-signed certs, internal network). Configurable verify_ssl for future CA cert support. |
| BMC session exhaustion | Denial of Service | Use Basic auth (stateless), not Redfish sessions |

## Sources

### Primary (HIGH confidence)
- DMTF Redfish Resource and Schema Guide (DSP2046): [dmtf.org](https://www.dmtf.org/sites/default/files/standards/documents/DSP2046_2024.2.html) -- PowerState, ResetType, AllowableValues
- DMTF Redfish Specification (DSP0266): [redfish.dmtf.org](https://redfish.dmtf.org/schemas/DSP0266_1.1.html) -- error response format, @Message.ExtendedInfo structure
- httpx SSL docs: [python-httpx.org/advanced/ssl](https://www.python-httpx.org/advanced/ssl/) -- verify=False, custom SSL context
- httpx auth docs: [python-httpx.org/advanced/authentication](https://www.python-httpx.org/advanced/authentication/) -- BasicAuth API
- Existing codebase: `inference_proxy/quads/client.py`, `inference_proxy/config/settings.py`, `inference_proxy/config/dependencies.py`, `inference_proxy/main.py` -- established patterns
- Project research: `.planning/research/SUMMARY.md`, `.planning/research/PITFALLS.md` -- pitfall documentation with MAAS/Ironic/StarlingX sources
- Phase context: `.planning/phases/21-redfish-client-configuration/21-CONTEXT.md` -- locked decisions D-01 through D-06

### Secondary (MEDIUM confidence)
- Redfish error responses: [redfish.redoc.ly/docs/concepts/errorresponses](https://redfish.redoc.ly/docs/concepts/errorresponses/) -- Base registry MessageIds
- DMTF Redfish Message Registry Guide (DSP2065): [dmtf.org](https://www.dmtf.org/sites/default/files/standards/documents/DSP2065_2022.3.html) -- MessageId format

### Tertiary (LOW confidence)
- httpx InsecureRequestWarning behavior: multiple web sources confirm httpx uses httpcore not urllib3, so no InsecureRequestWarning -- but not officially documented by httpx [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new deps, all existing, versions verified in pyproject.toml
- Architecture: HIGH -- mirrors QUADSClient exactly, all patterns established in codebase
- Pitfalls: HIGH -- 5 critical pitfalls verified against DMTF spec, MAAS, Ironic, StarlingX bug reports
- Error mapping: MEDIUM -- MessageId list covers common cases, but vendor-specific registries may surface unknown IDs (generic fallback handles this)

**Research date:** 2026-07-21
**Valid until:** 2026-08-21 (stable -- Redfish spec changes slowly, httpx API stable at 0.28)
