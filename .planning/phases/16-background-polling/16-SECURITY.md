---
phase: 16
slug: background-polling
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-16
---

# Phase 16 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| gateway -> QUADS API | Outbound HTTP to internal QUADS server | Host inventory JSON (non-sensitive operational data) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-16-01 | Spoofing | QUADS API response | accept | Internal network only; QUADS is a trusted internal service per project constraints | closed |
| T-16-02 | Tampering | Cached host list | accept | Single writer (poll task); readers get immutable frozen Pydantic models; properties return copies | closed |
| T-16-03 | Denial of Service | Poll loop blocks event loop | mitigate | `_poll_once()` catches all exceptions, increments failure counter, retains cached data, never crashes the loop. QUADSClient uses async httpx with configurable timeout. | closed |
| T-16-04 | Information Disclosure | Staleness metadata | accept | `last_sync` and `consecutive_failures` are operational data only, no PII | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-16-01 | T-16-01 | QUADS runs on internal network; no external access in v1. Spoofing requires network-level compromise outside scope. | plan threat model | 2026-07-16 |
| AR-16-02 | T-16-02 | Cache is single-writer (`_poll_once`). Properties return shallow copies of frozen Pydantic models — no mutation path. | plan threat model | 2026-07-16 |
| AR-16-03 | T-16-04 | Staleness metadata (`last_sync`, `consecutive_failures`) is operational telemetry with no user or security-sensitive content. | plan threat model | 2026-07-16 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-16 | 4 | 4 | 0 | gsd-secure-phase |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-16
