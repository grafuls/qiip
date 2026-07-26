---
phase: 27
slug: admin-api-endpoint
status: secured
threats_open: 0
asvs_level: 1
created: 2026-07-26
---

# Phase 27 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Client -> Admin API | hostname path parameter is untrusted input | String (hostname) |
| Admin API -> SSH (LLMFitRunner) | Validated hostname becomes SSH connection target | SSH command + hostname |
| Test mock -> endpoint | Tests verify error information does not leak | Error details / raw output |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-27-01 | Tampering | hostname path param | mitigate | `_validated_hostname()` regex + length check blocks injection (existing code, reused) | closed |
| T-27-02 | Information Disclosure | error responses | mitigate | D-01: raw llmfit output logged via structlog only, never in JSONResponse content. `test_raw_output_not_exposed` verifies invariant. | closed |
| T-27-03 | Spoofing | arbitrary SSH target | accept | Internal network only, operators only. Future milestone: hostname allowlist. | closed |
| T-27-SC | Tampering | npm/pip installs | n/a | No new packages installed in this phase. | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-27-01 | T-27-03 | Internal network only, operators are trusted users. Hostname allowlist deferred to future milestone. | plan-phase | 2026-07-26 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-26 | 4 | 4 | 0 | gsd-secure-phase |
