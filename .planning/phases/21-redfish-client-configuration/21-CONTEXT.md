# Phase 21: Redfish Client & Configuration - Context

**Gathered:** 2026-07-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a thin Redfish REST client that can query power state and issue power actions (On, ForceOff, GracefulRestart, ForceRestart) to server BMCs, with secure credential handling via pydantic-settings and human-readable error mapping (DIAG-03). This is the foundation for all v1.5 Redfish-dependent work.

</domain>

<decisions>
## Implementation Decisions

### BMC Hostname Convention
- **D-01:** BMC hostnames follow the `mgmt-{hostname}` pattern (e.g., server01 → mgmt-server01)
- **D-02:** Fleet-wide template via `INFERENCE_PROXY_REDFISH__BMC_HOST_TEMPLATE` env var — no per-host overrides

### Idempotency Behavior
- **D-03:** Check-before-act with silent success — query PowerState before issuing reset actions; if already in desired state, return success without hitting the reset endpoint
- **D-04:** Power actions poll PowerState until the target state is confirmed, with configurable timeout — the client handles the async transition internally so callers get a definitive result

### TLS Certificate Handling
- **D-05:** Always `verify=False` for BMC connections — no CA bundle support needed (self-signed certs are the norm)
- **D-06:** Suppress urllib3/httpx InsecureRequestWarning entirely — `verify=False` is intentional, not accidental

### Claude's Discretion
- Error message mapping approach for DIAG-03 (static dict of common Redfish MessageIds → human-readable text, with generic fallback extraction for unknown errors)
- RedfishClient internal structure (mirrors QUADSClient: constructor-injected httpx.AsyncClient, typed RedfishError exception)
- RedfishSettings sub-model fields and defaults (username, password as SecretStr, system_id, timeouts)
- Dependency injection wiring in dependencies.py (get_redfish_client provider)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing Client Pattern (primary analog)
- `inference_proxy/quads/client.py` — QUADSClient: the exact pattern to mirror (constructor-injected httpx.AsyncClient, typed error, async methods)
- `inference_proxy/models/quads.py` — QUADSHost: frozen Pydantic model pattern for Redfish response models

### Configuration
- `inference_proxy/config/settings.py` — Settings root with nested sub-models (QUADSSettings is the template for RedfishSettings)
- `inference_proxy/config/dependencies.py` — Dependency injection providers (get_quads_client is the template)

### Error Handling
- `inference_proxy/api/errors.py` — Error mapping pattern (map_proxy_error: exception → human-readable ErrorResponse)

### Project Research
- `.planning/research/SUMMARY.md` — v1.5 research summary with pitfalls, architecture, and phase structure
- `.planning/research/PITFALLS.md` — 13 critical pitfalls with prevention strategies

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `QUADSClient` class: exact structural template for `RedfishClient` (httpx.AsyncClient injection, typed errors, async GET methods)
- `QUADSSettings` sub-model: template for `RedfishSettings` (optional via None base_url, nested env var config)
- `map_proxy_error()` in `errors.py`: pattern for translating exceptions to human-readable messages

### Established Patterns
- Optional features disabled via `None` settings (QUADSSettings.base_url precedent)
- Dedicated httpx.AsyncClient per subsystem with separate timeout/TLS profiles
- Frozen Pydantic models for API response types
- Constructor dependency injection throughout

### Integration Points
- `inference_proxy/config/settings.py` — add `RedfishSettings` sub-model to root `Settings`
- `inference_proxy/config/dependencies.py` — add `get_redfish_client` provider
- `inference_proxy/main.py` — create Redfish httpx.AsyncClient in lifespan, wire into dependency injection

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches following the QUADSClient analog.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 21-redfish-client-configuration*
*Context gathered: 2026-07-21*
