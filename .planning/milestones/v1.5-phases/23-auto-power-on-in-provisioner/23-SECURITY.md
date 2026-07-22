---
phase: 23
slug: auto-power-on-in-provisioner
status: secured
threats_open: 0
asvs_level: 1
created: 2026-07-22
---

# Phase 23 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| provisioner -> BMC | RedfishClient handles auth/TLS (Phase 21); this phase only calls existing methods | Redfish power_action RPC over HTTPS |
| provisioner -> target SSH | TCP probe only (no auth); existing preflight pattern | SYN packet to port 22 (no data) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-23-01 | Spoofing | BMC hostname resolution | accept | bmc_host_template validated in Phase 21 RedfishSettings; no new input path | closed |
| T-23-02 | Denial of Service | SSH wait loop | mitigate | deadline-based timeout (boot_wait_timeout=300s) prevents indefinite blocking; logs warning on timeout | closed |
| T-23-03 | Information Disclosure | Power-on failure logs | mitigate | RedfishError caught at provisioner.py:142, logged via str(exc) — Phase 21 sanitizes credentials from error strings | closed |
| T-23-SC | Tampering | Supply chain | accept | No new packages installed in this phase | closed |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-23-01 | T-23-01 | BMC hostname derived from validated template; no user-controlled input enters resolution path | plan-time | 2026-07-22 |
| AR-23-02 | T-23-SC | Zero new dependencies added; lock file unchanged | plan-time | 2026-07-22 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-22 | 4 | 4 | 0 | gsd-secure-phase (plan-time register, short-circuit) |

---

## Evidence

### T-23-02: Deadline-based timeout
- `provisioner.py:154` — `deadline = asyncio.get_running_loop().time() + self._settings.boot_wait_timeout`
- `provisioner.py:155` — `while asyncio.get_running_loop().time() < deadline:`
- `settings.py` — `boot_wait_timeout: int = 300`

### T-23-03: Error sanitization
- `provisioner.py:142-143` — `except RedfishError as exc: logger.warning("power_on_failed", hostname=hostname, error=str(exc))`
- Phase 21 RedfishError.__str__ excludes credentials from output
