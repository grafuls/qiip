---
phase: 31
slug: download-service-api
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-28
---

# Phase 31 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| client -> admin API | Operator submits repo_id via JSON POST body | repo_id string (low sensitivity) |
| client -> GET /admin/models/downloads | Operator queries download statuses | status list (low sensitivity) |
| gateway -> HuggingFace Hub | snapshot_download authenticates with HF token over HTTPS | HF API token (high sensitivity) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-31-01 | Information Disclosure | DownloadService token handling | mitigate | Token stored as private attr `_token`; never logged by structlog | closed |
| T-31-02 | Tampering | repo_id input | accept | snapshot_download handles path construction internally; HF validates server-side | closed |
| T-31-03 | Denial of Service | concurrent downloads | mitigate | asyncio.Semaphore(2) caps concurrent downloads | closed |
| T-31-04 | Information Disclosure | error messages | mitigate | HF SDK exception strings only (repo names, auth hints); no internal stack traces | closed |
| T-31-05 | Spoofing | POST /admin/models/download | accept | Internal network only; no auth in v1 admin API (consistent with all admin endpoints) | closed |
| T-31-06 | Tampering | repo_id in POST body | accept | Pydantic type validation; snapshot_download validates repo format server-side | closed |
| T-31-07 | Information Disclosure | GET /admin/models/downloads | accept | Returns status and error strings only; no secrets, tokens, or paths exposed | closed |
| T-31-08 | Denial of Service | POST flood | mitigate | Semaphore(2) caps actual downloads; duplicate POSTs return existing status without spawning new work | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-31-02 | HF SDK owns path construction and repo_id validation | plan-time | 2026-07-28 |
| AR-02 | T-31-05 | Internal network only per project constraints; auth deferred to future phase | plan-time | 2026-07-28 |
| AR-03 | T-31-06 | Pydantic validates type; HF validates format server-side | plan-time | 2026-07-28 |
| AR-04 | T-31-07 | Endpoint returns status enums and error strings only | plan-time | 2026-07-28 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-28 | 8 | 8 | 0 | gsd-secure-phase |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-28
