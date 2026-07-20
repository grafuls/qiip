# Phase 15: QUADS Client and Models - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Gateway can discover GPU hosts from the QUADS REST API. Builds a thin httpx-based QUADS client with methods for fetching hosts and available hosts, a Pydantic model for QUADS host data, a hostname normalization function, and QUADS configuration settings. No background polling (Phase 16), no merge logic (Phase 17), no dashboard changes (Phase 18). This is the foundation layer — fully testable in isolation with httpx mocking.

</domain>

<decisions>
## Implementation Decisions

### Hostname Normalization
- **D-01:** QUADS instance returns short hostnames (not FQDNs). No domain stripping needed.
- **D-02:** Minimal `canonical_hostname()` function: strip whitespace, lowercase, strip trailing dots. Cheap insurance against format drift.
- **D-03:** `canonical_hostname()` lives in `quads/client.py`. Move to a shared location if needed when Phase 17 merge logic arrives.

### QUADS Data Scope
- **D-04:** QUADSHost model captures: hostname, GPU vendor, GPU model, GPU count. Minimal data scope.
- **D-05:** GPU info captured now (vendor, model) even though Phase 15 only needs a boolean filter. Avoids model changes in Phase 18 which needs vendor/model display (DASH-05).
- **D-06:** Client filters out broken and retired hosts before returning. Downstream code never sees them.

### Availability Source
- **D-07:** Host availability determined via `GET /api/v3/available` endpoint. Returns list of available hostnames — simple and authoritative.
- **D-08:** `get_available()` method added to QUADSClient in Phase 15. Phase 16 poller calls it. Clean separation: client has all API calls, poller has scheduling.

### Error Behavior
- **D-09:** Client raises typed `QUADSConnectionError` exception on API failure. Callers handle it explicitly.
- **D-10:** QUADS is "required when configured" — if `quads.base_url` is set, QUADS features are active. If not set, QUADS features are skipped. No explicit enabled/disabled toggle.
- **D-11:** Lazy validation — no connectivity check at construction time. First `get_hosts()` or `get_available()` call reveals misconfiguration. Simpler startup.

### Claude's Discretion
- httpx client configuration (timeouts, connection pooling) for the QUADS client
- QUADSHost Pydantic model field naming and exact structure
- QUADSSettings field names and defaults (base_url, request timeout)
- Internal method organization within QUADSClient

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### QUADS API (what the client calls)
- `.planning/research/SUMMARY.md` — QUADS API endpoint reference, response formats, pitfalls, architecture approach
- QUADS GitHub source: `src/quads/server/blueprints/hosts.py` — GET /api/v3/hosts endpoint (unauthenticated)
- QUADS GitHub source: `src/quads/server/blueprints/available.py` — GET /api/v3/available endpoint

### Configuration Pattern (what QUADSSettings follows)
- `inference_proxy/config/settings.py` — Existing settings pattern: sub-models inherit BaseModel, root Settings inherits BaseSettings
- `inference_proxy/config/dependencies.py` — DI pattern for app.state services

### Project Context
- `.planning/ROADMAP.md` — Phase 15 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — QUADS-01, QUADS-03, QUADS-04 requirement definitions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `settings.py` nested BaseModel pattern — QUADSSettings follows same convention as SSHSettings, ProvisioningSettings
- `dependencies.py` app.state DI pattern — add `get_quads_client()` following `get_provisioner()` pattern
- `NodeStatus` StrEnum — established enum pattern for status values
- Frozen Pydantic models — QUADSHost follows same `ConfigDict(frozen=True)` convention

### Established Patterns
- Package-per-domain: new `inference_proxy/quads/` package (like `provisioning/`, `discovery/`, `resilience/`)
- DIP: QUADSClient depends on httpx.AsyncClient (injectable for testing)
- `asyncio.to_thread()` for sync calls — not needed here since httpx AsyncClient is natively async
- structlog for all logging — follow existing bound logger pattern
- pydantic-settings env var prefix: `INFERENCE_PROXY_QUADS__BASE_URL` etc.

### Integration Points
- `settings.py` — add `quads: QUADSSettings` field to root Settings class
- `main.py` lifespan — create QUADSClient (if configured), store in app.state
- `dependencies.py` — add `get_quads_client()` DI provider

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 15-QUADS Client and Models*
*Context gathered: 2026-07-16*
