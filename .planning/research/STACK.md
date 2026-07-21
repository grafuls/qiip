# Stack Research

**Domain:** Redfish power management and provisioning diagnostics (v1.5 milestone)
**Researched:** 2026-07-21
**Confidence:** HIGH
**Scope:** Stack additions for Redfish-based power on/off/restart, power status queries, auto-power-on before SSH provisioning, and step-level error capture with dashboard display. Existing stack (Python 3.12, FastAPI, httpx, etcd3gw, asyncssh, structlog, Pydantic v2, Jinja2) is validated and NOT re-evaluated here.

## New Python Dependencies for v1.5

**None.**

Zero new runtime or dev dependencies. httpx covers all Redfish REST calls natively.

## Why No New Python Dependencies

### The Redfish API Is Trivial REST

Redfish (DMTF DSP0266) is a standard REST API served by BMC firmware over HTTPS. The operations needed for v1.5 are:

| Operation | HTTP Method | Endpoint | Body |
|-----------|-------------|----------|------|
| Get power state | `GET` | `/redfish/v1/Systems/{id}` | None (read `PowerState` from response JSON) |
| Power on | `POST` | `/redfish/v1/Systems/{id}/Actions/ComputerSystem.Reset` | `{"ResetType": "On"}` |
| Force off | `POST` | `/redfish/v1/Systems/{id}/Actions/ComputerSystem.Reset` | `{"ResetType": "ForceOff"}` |
| Graceful restart | `POST` | `/redfish/v1/Systems/{id}/Actions/ComputerSystem.Reset` | `{"ResetType": "GracefulRestart"}` |
| Force restart | `POST` | `/redfish/v1/Systems/{id}/Actions/ComputerSystem.Reset` | `{"ResetType": "ForceRestart"}` |
| Discover allowed actions | `GET` | `/redfish/v1/Systems/{id}` | None (read `Actions.#ComputerSystem.Reset.ResetType@Redfish.AllowableValues`) |

That is one GET and one POST with a JSON body. httpx does this in its sleep.

### Python Redfish Libraries Evaluated and Rejected

Three libraries were evaluated. All three use synchronous `requests` under the hood, all three would add dependency trees larger than the code they replace, and none provide meaningful value for our 2-endpoint use case.

| Library | Version | HTTP Client | Key Dependencies | Verdict |
|---------|---------|-------------|------------------|---------|
| `redfish` (DMTF) | 3.3.6 | `requests` (sync) | requests, requests-toolbelt, requests-unixsocket, jsonpatch, jsonpath_ng, jsonpointer | **REJECT** |
| `sushy` (OpenStack) | 5.11.1 | `requests` (sync) | OpenStack dependency graph (openstacksdk ecosystem) | **REJECT** |
| `python-ilorest-library` (HPE) | 7.2.0.0 | `requests` (sync) | HPE-specific; **conflicts with DMTF `redfish` package namespace** | **REJECT** |

#### Why `redfish` (DMTF) Was Rejected

- Pulls in `requests` (sync HTTP client) when we already have `httpx` (async). Every call would need `asyncio.to_thread()` wrapping.
- Adds 6 transitive dependencies (requests, requests-toolbelt, requests-unixsocket, jsonpatch, jsonpath_ng, jsonpointer) for functionality we do not need (JSON patching, Unix socket connections, multipart uploads).
- The library's value is navigating complex Redfish schemas (BIOS settings, storage controllers, firmware updates). We are calling exactly 2 endpoints.
- Actively maintained (latest release July 2026), but the dependency cost is not justified.

#### Why `sushy` (OpenStack) Was Rejected

- Designed for OpenStack Ironic's bare metal provisioning needs. Scope is far broader than power management.
- Pulls in the OpenStack dependency ecosystem. Adding OpenStack dependencies to a lightweight FastAPI proxy is the wrong direction.
- Also uses `requests` (sync), same wrapping problem.
- Good library for its intended audience (Ironic drivers), wrong tool here.

#### Why `python-ilorest-library` (HPE) Was Rejected

- HPE vendor-locked. While it claims generic Redfish support, it is optimized for iLO BMCs.
- **Cannot coexist** with the DMTF `redfish` package in the same Python environment (namespace conflict). This is a hard blocker.
- Our BMC fleet includes multiple vendors (Dell iDRAC, Supermicro, HPE iLO). A vendor-specific library is the wrong choice.

### httpx Covers Everything

httpx is already installed (`httpx>=0.28`). It provides:

- **Async HTTP client**: `httpx.AsyncClient` with connection pooling (already used for proxy engine and QUADS client)
- **Basic auth**: `httpx.BasicAuth(username, password)` -- built-in, one line
- **Self-signed cert handling**: `verify=False` parameter (BMCs universally use self-signed certs)
- **JSON request/response**: `client.post(url, json=payload)`, `response.json()` -- trivial
- **Timeout control**: Per-request or client-level timeouts
- **Error handling**: `httpx.HTTPError` hierarchy, `response.raise_for_status()`

The Redfish client will follow the exact same pattern as `QUADSClient` (see `inference_proxy/quads/client.py`): thin async wrapper over an injected `httpx.AsyncClient`.

## Redfish Client Design (httpx-based)

### Authentication: Basic Auth

Use HTTP Basic Authentication. Rationale:

1. **Simplicity**: One header per request, no session lifecycle to manage.
2. **Stateless**: No token expiry, no refresh logic, no cleanup on error.
3. **Sufficient**: Internal network, BMC calls are infrequent (power operations, not continuous polling). Session-based auth saves nothing here.
4. **Standard**: Every Redfish implementation supports basic auth. Session auth support varies by vendor firmware version.

httpx handles this natively:

```python
auth = httpx.BasicAuth(username, password)
client = httpx.AsyncClient(auth=auth, verify=False)
```

### Self-Signed Certificates

BMCs universally use self-signed certificates. `verify=False` is standard practice for BMC communication on internal networks. The DMTF `redfish` library itself suppresses `InsecureRequestWarning` from urllib3 for the same reason. sushy has a dedicated `TLSHttpAdapter` for this.

httpx with `verify=False` handles this cleanly. Suppress the warning at the client level.

### System ID Discovery

The system ID in the Redfish URL (`/redfish/v1/Systems/{id}`) varies by vendor:

| Vendor | Typical System ID |
|--------|-------------------|
| Dell iDRAC | `System.Embedded.1` |
| Supermicro | `1` |
| HPE iLO | `1` |
| NVIDIA DGX | `DGX` |
| OpenBMC | `system` |

The safe approach: GET `/redfish/v1/Systems/` to list members, take the first (and usually only) entry. Cache the result per-BMC. This is what both sushy and the DMTF library do internally.

### Timeout Configuration

BMC operations are slow compared to typical REST APIs. Power state changes take 1-30 seconds to execute. Network latency to BMCs on management networks is typically higher than application networks.

Recommended: connect timeout 10s, read timeout 30s for power operations.

## Configuration Additions

New settings model for Redfish BMC access:

```python
class RedfishSettings(BaseModel):
    """Redfish BMC configuration."""
    username: str = "root"
    password: str = ""  # Must be set via env var
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    # ponytail: single credential set for all BMCs; per-BMC creds if fleet is heterogeneous
```

BMC endpoint derivation: convention-based from hostname. Most lab environments use a naming pattern like `{hostname}-mgmt` or `mgmt-{hostname}` for BMC addresses. This should be configurable:

```python
    bmc_hostname_pattern: str = "{hostname}-mgmt"
    # e.g., "server01" -> "server01-mgmt"
```

Env var: `INFERENCE_PROXY_REDFISH__USERNAME`, `INFERENCE_PROXY_REDFISH__PASSWORD`, etc.

## Step-Level Error Capture

### What Already Exists

The `ProvisioningState` model already has `failed_step: str | None` and `error: str | None` fields. The provisioner writes these to etcd on failure. The admin API already serves them via `GET /admin/provisioning/tasks`.

### What Needs to Change (Code, Not Libraries)

The current error capture is coarse: `failed_step` gets the exception class name (`RemoteCommandError`), and `error` gets the full exception message. The v1.5 improvement is:

1. **Map `failed_step` to the actual provisioning step** (e.g., `nvidia_driver` instead of `RemoteCommandError`). The `_run_setup` method already parses `[STEP:name:FAIL]` markers but only logs them -- it should propagate the step name to the failure state.

2. **Truncate `error` to a useful summary** rather than dumping full SSH output. First 500 chars of stderr is enough for dashboard display.

3. **Surface errors in the dashboard UI** -- the admin API already returns error data; the dashboard JS needs to read and display it.

No new libraries needed. This is a code change in `provisioner.py` (capture the step name from markers) and `dashboard.js` (display the error field).

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| httpx (already installed) | DMTF `redfish` library | Adds `requests` + 5 transitive deps for 2 REST endpoints. Sync-only, needs thread wrapping. |
| httpx (already installed) | `sushy` (OpenStack) | OpenStack dependency graph. Designed for Ironic, massive overkill. |
| httpx (already installed) | `python-ilorest-library` (HPE) | Vendor-locked, namespace conflicts with DMTF package. |
| httpx (already installed) | `aiohttp` | Already have httpx. Adding a second async HTTP client is waste. |
| Basic auth | Session auth (X-Auth-Token) | Session management complexity for infrequent BMC calls. No benefit on internal network. |
| Convention-based BMC hostname | QUADS BMC discovery API | QUADS may not expose BMC addresses. Convention pattern is simpler and standard in lab environments. Configurable pattern covers variations. |
| In-memory error field on ProvisioningState | Separate error log storage | Already have `error` field in etcd state. No new storage needed. |

## What NOT to Add

| Technology | Why Not |
|------------|---------|
| `redfish` (DMTF PyPI package) | sync `requests`-based, 6 transitive deps, overkill for 2 endpoints |
| `sushy` (OpenStack) | OpenStack dependency ecosystem, designed for Ironic drivers |
| `python-ilorest-library` (HPE) | Vendor-locked, namespace conflict |
| `requests` | httpx already installed, async-native, same API surface |
| `ipmi` / `pyghmi` | IPMI is legacy. Redfish is the standard. Do not add IPMI as fallback unless a BMC without Redfish is discovered in the fleet. |
| Retry library (tenacity) | Power operations are idempotent and infrequent. If a BMC call fails, surface the error to the operator. One manual retry from the dashboard is simpler than retry logic with exponential backoff against a potentially unreachable BMC. |
| Separate error database | etcd already stores provisioning state with error fields. No SQLite, no Redis, no new storage. |

## Integration Points with Existing App

### Follows QUADSClient Pattern

The Redfish client mirrors `QUADSClient` exactly:

- Constructor-injected `httpx.AsyncClient` (DIP, testable)
- Thin async methods wrapping httpx calls
- Custom exception type for connection errors
- Registered in `config/dependencies.py` alongside other clients

### Provisioner Integration

The provisioner's `provision()` method gains a new step before `preflight`:

```
PENDING -> POWER_ON -> PREFLIGHT -> UPLOADING_SCRIPTS -> ...
```

If the host is already powered on (PowerState == "On"), skip the power-on step. This is a pre-flight enhancement, not a new workflow.

### Admin API Extension

New endpoints follow existing patterns:

```
POST /admin/nodes/{node_id}/power   {"action": "On|ForceOff|GracefulRestart|ForceRestart"}
GET  /admin/nodes/{node_id}/power   -> {"power_state": "On|Off|..."}
```

### Dashboard UI Extension

- Power state badge next to each node in the fleet table
- Power action buttons (on/off/restart) in node row actions
- Error display: inline expandable section showing `failed_step` and `error` from provisioning state

All vanilla JS, same pattern as existing action buttons.

## Installation

```bash
# No new dependencies
# Existing pyproject.toml already has everything needed
```

## Key Version Constraints

No new version constraints. All existing constraints from v1.4 remain valid.

| Existing Dependency | Minimum | Still Valid | v1.5 Relevance |
|---------------------|---------|-------------|----------------|
| httpx >= 0.28 | Stable async streaming | Yes | Redfish REST client uses `AsyncClient` with basic auth |
| Pydantic >= 2.10 | Model validation | Yes | New `RedfishSettings` model, extended `ProvisioningStep` enum |
| FastAPI >= 0.135 | Built-in SSE | Yes | New admin endpoints for power operations |
| structlog >= 26.1.0 | Structured logging | Yes | Redfish operation logging |

## Sources

- DMTF Redfish specification: https://www.dmtf.org/standards/redfish -- DSP0266, REST API standard for hardware management
- DMTF python-redfish-library: https://github.com/DMTF/python-redfish-library -- v3.3.6, evaluated and rejected (sync, heavy deps)
- redfish PyPI: https://pypi.org/project/redfish/ -- v3.3.6 (July 2026), depends on requests + 5 others
- sushy (OpenStack): https://github.com/openstack/sushy -- v5.11.1 (July 2026), requests-based, Ironic-scoped
- sushy PyPI: https://pypi.org/project/sushy/ -- Python >=3.10, actively maintained
- sushy connector.py: https://github.com/openstack/sushy/blob/master/sushy/connector.py -- confirms requests dependency, TLS adapter
- python-ilorest-library: https://github.com/HewlettPackard/python-ilorest-library -- v7.2.0.0, HPE vendor-specific
- Redfish authentication: https://redfish.redoc.ly/docs/concepts/redfishauthentication/ -- Basic + Session auth patterns
- OpenBMC Redfish cheatsheet: https://github.com/openbmc/docs/blob/master/REDFISH-cheatsheet.md -- curl examples for power operations
- Redfish power operations: https://advantech-ncg.zendesk.com/hc/en-us/articles/44142031579417 -- ComputerSystem.Reset action examples
- NVIDIA DGX Redfish: https://docs.nvidia.com/dgx/dgxh100-user-guide/redfish-api-supp.html -- vendor-specific system IDs
- Existing codebase: `inference_proxy/quads/client.py` -- httpx.AsyncClient pattern to follow
- Existing codebase: `inference_proxy/provisioning/state.py` -- ProvisioningState already has error fields
- Existing codebase: `inference_proxy/provisioning/provisioner.py` -- step marker parsing already exists

---
*Stack research for: Redfish power management and provisioning diagnostics (v1.5)*
*Researched: 2026-07-21*
