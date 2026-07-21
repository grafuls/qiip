# Project Research Summary

**Project:** QUADS LLM Inference Proxy -- v1.5 Redfish Power Management & Provisioning Diagnostics
**Domain:** BMC power management integration into existing bare-metal provisioning pipeline
**Researched:** 2026-07-21
**Confidence:** HIGH

## Executive Summary

The v1.5 milestone adds two capabilities to the inference proxy: Redfish-based power management (on/off/restart/status via BMC) and improved provisioning failure diagnostics (step-level error capture with dashboard display). Both features plug into the existing provisioning pipeline and admin dashboard without architectural upheaval. The critical finding across all research areas is that **zero new dependencies are needed**. httpx already handles Redfish REST calls natively (2 endpoints: GET power state, POST reset action), and the existing `ProvisioningState` model already has the `failed_step` and `error` fields -- they just need to be populated correctly.

The recommended approach is to build a thin `RedfishClient` following the exact `QUADSClient` pattern (constructor-injected httpx.AsyncClient, typed errors, Basic auth), wire it into the provisioner as an optional dependency, and extend the admin API with power endpoints. The client must use a dedicated httpx instance with Redfish-specific timeouts (10s connect, 60s read) and scoped `verify=False` for self-signed BMC certificates. The opt-in pattern (Redfish disabled when `username` is None) matches the existing QUADS feature toggle.

The primary risks are operational, not architectural. Redfish power actions are not idempotent (ForceOff on an off server returns HTTP 400), power state transitions are asynchronous (HTTP 200 means "accepted" not "done"), and BMC credentials can leak into logs and error displays if not handled with `SecretStr`. All five critical pitfalls are well-documented from MAAS, OpenShift Ironic, and StarlingX experiences and have straightforward mitigations: check-before-act for idempotency, post-action polling for async transitions, and `SecretStr` + error sanitization for credential safety.

## Key Findings

### Recommended Stack

No new Python dependencies. The existing stack (httpx >= 0.28, FastAPI >= 0.135, Pydantic >= 2.10, pydantic-settings >= 2.14, structlog >= 26.1.0) covers everything. Three Redfish Python libraries were evaluated and rejected:

**Core technologies (all existing):**
- **httpx**: Redfish REST client -- async, connection pooling, Basic auth built-in, already used for proxy engine and QUADS client
- **pydantic-settings**: `RedfishSettings` sub-model for BMC credentials and timeouts -- env var injection via `INFERENCE_PROXY_REDFISH__*`
- **Pydantic SecretStr**: BMC password masking in logs, repr, and model_dump -- prevents credential leaks

**Evaluated and rejected:**
- `redfish` (DMTF): sync `requests`-based, 6 transitive deps, overkill for 2 endpoints
- `sushy` (OpenStack): OpenStack dependency ecosystem, designed for Ironic drivers
- `python-ilorest-library` (HPE): vendor-locked, namespace conflict with DMTF package

### Expected Features

**Must have (table stakes):**
- Power on via Redfish -- cannot SSH into a powered-off server
- Power off (ForceOff) -- operators need to stop nodes when SSH is unavailable
- Power restart (GracefulRestart, ForceRestart) -- common ops action for hung servers
- Power status query -- know if On/Off before attempting operations
- Auto-power-on before provisioning -- if off when setup triggered, power on and wait for SSH
- Step-level error capture -- `failed_step` must show actual provisioning step name, not exception class
- Dashboard error display for failed nodes -- inline error on fleet table, not buried in node detail

**Should have (differentiators, cheap to add):**
- Power status column in fleet table (one Redfish GET per node, cached)
- Power action buttons in dashboard (extend existing ACTION_CONFIG)
- BMC reachability check before power operations
- Collapsible error detail on dashboard

**Defer (v2+):**
- Per-host BMC credential storage
- IPMI fallback for servers without Redfish
- Continuous power state polling (background thread)
- Chassis/thermal/fan monitoring via Redfish
- Provisioning log streaming to dashboard
- Firmware update via Redfish

### Architecture Approach

Four new/modified components, all following established codebase patterns. `RedfishClient` mirrors `QUADSClient` exactly: thin httpx wrapper, constructor-injected AsyncClient, typed `RedfishError`. The provisioner gains an optional `redfish_client` parameter and a `_power_on_if_needed()` step before preflight. Admin API gets two new routes (`GET/POST /admin/nodes/{id}/power`). The dashboard extends `ACTION_CONFIG` and `_STATE_ACTIONS` for power buttons and inline error display.

**Major components:**
1. **RedfishClient** (`redfish/client.py`) -- GET power state, POST reset action, Basic auth, dedicated httpx instance
2. **RedfishSettings** (sub-model in `settings.py`) -- BMC credentials (SecretStr), hostname template, system ID, timeouts
3. **Power admin endpoints** (routes in `admin.py`) -- HTTP API for manual power operations, returns 503 if Redfish not configured
4. **Provisioner power-on step** (modified `provisioner.py`) -- POWERING_ON step before PREFLIGHT, polls SSH port 22 after power-on

**Key patterns to follow:**
- Optional feature via None settings (QUADSSettings precedent)
- Dedicated httpx.AsyncClient per subsystem (separate TLS/timeout profiles)
- Dependency injection via `dependencies.py` providers

### Critical Pitfalls

1. **ForceOff on an already-off server returns HTTP 400** -- Always query PowerState before issuing reset actions. Handle 400 by re-checking state: if desired state is reached, treat as success. This is the most common Redfish integration bug across MAAS, Ironic, and StarlingX.

2. **BMC credentials leak into logs and error responses** -- Use Pydantic `SecretStr` for the password field. Never include RedfishSettings in structlog context binds. Sanitize error messages before writing to etcd. Never embed credentials in URLs.

3. **SSH preflight starts before OS boots after power-on** -- Redfish power-on returns immediately (accepted, not done). Must poll PowerState until On, then poll TCP port 22 with 5-minute timeout before running SSH preflight. Add POWERING_ON step to ProvisioningStep enum so dashboard shows boot progress.

4. **TLS verify=False leaks to other httpx clients** -- Scope `verify=False` to the Redfish-dedicated httpx.AsyncClient only. Make configurable via `RedfishSettings.verify_ssl`. Do not share client instances across subsystems.

5. **Raw Redfish JSON rendered in dashboard error display** -- Create human-readable error summaries from Redfish error codes. Map common MessageIds to operator-friendly messages. Cap error field at 200 characters. Full context goes to structlog.

## Implications for Roadmap

Based on research, suggested phase structure (4 phases, bottom-up from dependency chain):

### Phase 1: Redfish Client + Configuration

**Rationale:** Foundation for all other v1.5 work. Zero dependencies on other phases. Must get credential handling, TLS scoping, and idempotency right from the start -- 4 of 5 critical pitfalls live here.
**Delivers:** `RedfishClient` class, `RedfishSettings` sub-model, dependency injection wiring, tests with pytest-httpx mocking.
**Addresses:** Power status query, power on/off/restart actions (table stakes features).
**Avoids:** Credential leaks (Pitfall 2), TLS verify leak (Pitfall 4), session exhaustion (Pitfall 6, by using Basic auth), timeout issues (Pitfall 10), vendor URI issues (Pitfall 8).

**Scope:**
- `inference_proxy/redfish/__init__.py`, `inference_proxy/redfish/client.py` (new)
- `inference_proxy/config/settings.py` (add RedfishSettings)
- `inference_proxy/config/dependencies.py` (add get_redfish_client)
- `inference_proxy/main.py` (create client in lifespan)
- `tests/redfish/test_client.py` (new)

### Phase 2: Admin Power Endpoints + Dashboard Buttons

**Rationale:** Depends on RedfishClient from Phase 1. Independent of provisioning changes. Delivers immediate operator value -- power management from the dashboard without SSH.
**Delivers:** `GET/POST /admin/nodes/{id}/power` endpoints, power action buttons in dashboard, power status display.
**Addresses:** Power action buttons (differentiator), admin API power endpoints (table stakes).
**Avoids:** ForceOff on off server (Pitfall 1, check-before-act in endpoint handler), raw error JSON in dashboard (Pitfall 5).

**Scope:**
- `inference_proxy/models/admin.py` (add PowerActionRequest, PowerStatusResponse, PowerActionResponse)
- `inference_proxy/api/admin.py` (add power routes)
- `inference_proxy/services/unified_nodes.py` (add power actions to _STATE_ACTIONS)
- `inference_proxy/static/js/dashboard.js` (add power actions to ACTION_CONFIG)
- `tests/api/test_admin.py` (power endpoint tests)

### Phase 3: Auto-Power-On in Provisioner

**Rationale:** Depends on RedfishClient (Phase 1). Modifies the provisioning state machine. This is the core workflow improvement -- setup button works even when servers are off.
**Delivers:** POWERING_ON provisioning step, automatic power-on before SSH preflight, boot wait polling.
**Addresses:** Auto-power-on before provisioning (table stakes).
**Avoids:** SSH before boot (Pitfall 3), enum not extended (Pitfall 9), retry reboots server (Pitfall 13, via idempotent power check), async transitions treated as synchronous (Pitfall 7).

**Scope:**
- `inference_proxy/provisioning/state.py` (add POWERING_ON to ProvisioningStep)
- `inference_proxy/provisioning/provisioner.py` (add _power_on_if_needed, optional redfish_client param)
- `inference_proxy/main.py` (pass redfish_client to provisioner)
- `tests/provisioning/test_provisioner.py` (power-on flow tests)

### Phase 4: Provisioning Error Diagnostics

**Rationale:** Independent of Redfish (could be built in parallel with Phases 2-3), but benefits from POWERING_ON step existing (tests can verify error display for power failures). Completes the v1.5 milestone's "step-level error capture" requirement.
**Delivers:** Precise `failed_step` values, stderr context in error messages, inline error display on dashboard fleet table.
**Addresses:** Step-level error capture, dashboard error display (table stakes).
**Avoids:** Error field too terse (Pitfall 12), raw error messages (Pitfall 5).

**Scope:**
- `inference_proxy/provisioning/provisioner.py` (fix failed_step to use step name, capture stderr)
- `inference_proxy/models/admin.py` (add last_error to AdminNodeResponse)
- `inference_proxy/services/unified_nodes.py` (populate last_error from provisioning tasks)
- `inference_proxy/static/js/dashboard.js` (render inline error for failed nodes)
- `inference_proxy/templates/dashboard.html` (error column in fleet table)
- Tests for error capture and display

### Phase Ordering Rationale

- **Bottom-up from dependencies:** RedfishClient is the foundation; admin endpoints and provisioner integration both depend on it; error diagnostics is independent but logically last.
- **Immediate operator value:** Phase 2 delivers power management from the dashboard before the provisioner is modified -- operators get value while Phase 3 is built.
- **Pitfall isolation:** Critical pitfalls (credential leaks, TLS scope, idempotency) are contained in Phase 1 where they can be tested in isolation before integration.
- **Error diagnostics last:** The error capture fix is a code change (not a new subsystem), so it is lowest risk and can absorb learnings from earlier phases.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1:** Redfish client needs vendor-specific testing (Dell iDRAC vs Supermicro vs HPE iLO system IDs and error responses). The specification is clear but implementations vary.
- **Phase 3:** Boot wait timing varies significantly by hardware. The 5-minute timeout is a starting estimate; real fleet data needed during implementation.

Phases with standard patterns (skip research-phase):
- **Phase 2:** Standard CRUD admin endpoints following existing patterns. Well-documented in codebase.
- **Phase 4:** Error message formatting and dashboard rendering. Existing patterns in provisioner.py and dashboard.js cover this.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new deps. httpx covers everything. All three alternative libraries were evaluated with version numbers, dependency trees, and concrete rejection reasons. |
| Features | HIGH | Clear table stakes vs differentiators. Anti-features are well-reasoned. Feature dependency chain is explicit. |
| Architecture | HIGH | Follows established codebase patterns (QUADSClient, opt-in via None settings). Build order derived from dependency analysis. |
| Pitfalls | HIGH | Verified against MAAS, OpenShift Ironic, StarlingX bug reports. DMTF specification confirms non-idempotent behavior. 13 pitfalls with concrete prevention strategies. |

**Overall confidence:** HIGH

### Gaps to Address

- **Multi-vendor BMC testing:** Research confirms vendor variation in system IDs and error responses, but actual fleet composition determines whether `system_id = "1"` default is sufficient or discovery is needed. Validate during Phase 1 implementation against real lab hardware.
- **Boot wait timing:** The 300s timeout for SSH readiness after power-on is an estimate. Actual POST + boot times vary by server model (2-5 minutes). Instrument during Phase 3 to calibrate.
- **BMC hostname convention:** Research assumes `mgmt-{hostname}` pattern. Confirm against actual QUADS lab DNS naming before finalizing the default template.

## Sources

### Primary (HIGH confidence)
- DMTF Redfish Specification (DSP0266) -- PowerState, ComputerSystem.Reset, ResetType values
- DMTF Redfish Resource and Schema Guide (DSP2046) -- error response format, AllowableValues
- MAAS Redfish power driver (Canonical) -- vendor quirks, session management, state polling
- OpenBMC docs -- system ID conventions, state management, TLS configuration
- Existing codebase (`inference_proxy/`) -- QUADSClient pattern, ProvisioningState model, provisioner state machine

### Secondary (MEDIUM confidence)
- HPE Redfish authentication docs -- session limits (16 max), Basic auth support
- Dell iDRAC Redfish scripting -- system ID `System.Embedded.1`, reset action patterns
- Supermicro Redfish user guide -- session timeout configuration
- DMTF Python Redfish library -- evaluated for rejection, confirms sync/requests architecture

### Tertiary (LOW confidence)
- Boot wait timing estimates -- based on general server POST times, not lab-specific measurements
- BMC hostname convention `mgmt-{hostname}` -- assumed from common lab patterns, needs validation

---
*Research completed: 2026-07-21*
*Ready for roadmap: yes*
