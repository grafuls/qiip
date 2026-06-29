---
phase: 07
slug: request-metrics-and-admin-api
status: verified
threats_open: 0
asvs_level: 1
created: 2026-06-29
---

# Phase 07 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| admin API | Returns internal operational data via /admin/nodes and /admin/metrics | Node IDs, endpoints, models, connection counts, circuit breaker state, request counters — no PII |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-07-01 | Information Disclosure | /admin/nodes, /admin/metrics | accept | Internal network only; no PII in counters; per project constraints | closed |
| T-07-02 | Denial of Service | RequestMetrics lock contention | accept | Single lock on integer increments; ConnectionTracker uses same pattern on same hot path without issues | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-01 | T-07-01 | Admin endpoints expose only operational counters and node metadata on internal network. No PII, no credentials, no user data. Project constraints explicitly scope v1 to internal network only. | Plan author | 2026-06-29 |
| AR-07-02 | T-07-02 | RequestMetrics uses a single threading.Lock protecting integer increments — identical pattern to ConnectionTracker which runs on the same hot path without measured contention. Lock hold time is nanoseconds. | Plan author | 2026-06-29 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-29 | 2 | 2 | 0 | Claude (gsd-secure-phase) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-29
