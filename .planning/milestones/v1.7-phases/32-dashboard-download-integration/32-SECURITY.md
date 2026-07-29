---
phase: 32
slug: dashboard-download-integration
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-29
---

# Phase 32 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser -> Admin API | JS sends POST /admin/models/download with user-chosen repo_id | repo_id string (low sensitivity, internal network) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-32-01 | Tampering | POST /admin/models/download body | accept | Internal network only (CLAUDE.md constraint), backend validates repo_id format via Pydantic model | closed |
| T-32-02 | Denial of Service | Multiple poll timers | mitigate | Guard in startDownloadPolling() checks downloadPollTimer before creating new interval (line 362) | closed |
| T-32-03 | Information Disclosure | Error messages from download API | accept | Internal network, error details help operators diagnose issues | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-32-01 | T-32-01 | Internal network only, no external-facing endpoints in v1. Backend Pydantic validation provides defense-in-depth. | plan author | 2026-07-29 |
| AR-32-03 | T-32-03 | Internal network, error details help operators diagnose download failures. No PII in error responses. | plan author | 2026-07-29 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-29 | 3 | 3 | 0 | gsd-secure-phase |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-29
