# Phase 15: QUADS Client and Models - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 15-QUADS Client and Models
**Areas discussed:** Hostname normalization, QUADS data scope, Availability source, Error behavior

---

## Hostname Normalization

| Option | Description | Selected |
|--------|-------------|----------|
| FQDN with domain | e.g. host01.example.com — we'd strip the domain to get the short name | |
| Short names only | e.g. host01 — no normalization needed, QUADS and etcd already match | ✓ |
| Mixed / unsure | Some hosts have domain suffix, some don't | |

**User's choice:** Short names only
**Notes:** QUADS instance returns short hostnames matching etcd format.

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal normalize | Strip whitespace, lowercase, strip trailing dots | ✓ |
| Skip normalization | Direct string comparison, no function needed | |

**User's choice:** Minimal normalize
**Notes:** Cheap insurance against format drift.

| Option | Description | Selected |
|--------|-------------|----------|
| quads/client.py | Keep it in the QUADS package — move later if needed | ✓ |
| models/node.py | Next to the Node model — shared hostname concern | |
| You decide | Claude picks the laziest correct location | |

**User's choice:** quads/client.py

---

## QUADS Data Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal (GPU only) | hostname, processors (GPU vendor/model/count) | ✓ |
| Moderate | hostname, processors, hardware model, broken/retired | |
| Broad | hostname, processors, hardware model, cloud, broken/retired, host_type | |

**User's choice:** Minimal (GPU only)

| Option | Description | Selected |
|--------|-------------|----------|
| Filter in client | Client drops broken=true and retired=true hosts | ✓ |
| Pass through | Client returns all, merge logic decides | |
| You decide | Claude picks | |

**User's choice:** Filter in client

| Option | Description | Selected |
|--------|-------------|----------|
| Has GPU (boolean) | Just whether host has any GPU processor | Initially selected |
| GPU summary | GPU vendor, model, and count from processors array | ✓ (revised) |

**User's choice:** Initially chose boolean-only, revised to capture GPU vendor/model after noting DASH-05 (Phase 18) requires vendor/model display.

| Option | Description | Selected |
|--------|-------------|----------|
| Capture now | Add gpu_vendor and gpu_model fields now | ✓ |
| Boolean now, extend later | Keep minimal, Phase 18 adds fields | |

**User's choice:** Capture now
**Notes:** Avoids model changes in Phase 18.

---

## Availability Source

| Option | Description | Selected |
|--------|-------------|----------|
| GET /api/v3/available | Dedicated endpoint returns available hostnames | ✓ |
| Check cloud field | cloud.name matching default/spare pool | |
| Both (cross-check) | Fetch /available AND check cloud field | |

**User's choice:** GET /api/v3/available

| Option | Description | Selected |
|--------|-------------|----------|
| Client method now | Add get_available() to QUADSClient in Phase 15 | ✓ |
| Defer to Phase 16 | Phase 15 only implements get_hosts() | |

**User's choice:** Client method now
**Notes:** Clean separation — client has all API calls, poller has scheduling.

---

## Error Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Return empty + log | get_hosts()/get_available() return empty on failure | |
| Raise exception | Typed QUADSConnectionError, callers handle explicitly | ✓ |
| You decide | Claude picks based on codebase patterns | |

**User's choice:** Raise exception

| Option | Description | Selected |
|--------|-------------|----------|
| Optional (enabled flag) | QUADSSettings has enabled=False by default | |
| Required when configured | If quads.base_url is set, QUADS is active | ✓ |
| Always required | Gateway fails to start without QUADS | |

**User's choice:** Required when configured

| Option | Description | Selected |
|--------|-------------|----------|
| Lazy (first call) | No validation at construction | ✓ |
| Eager (constructor) | Client hits QUADS on creation to verify connectivity | |

**User's choice:** Lazy (first call)

---

## Claude's Discretion

- httpx client configuration (timeouts, connection pooling) for the QUADS client
- QUADSHost Pydantic model field naming and exact structure
- QUADSSettings field names and defaults
- Internal method organization within QUADSClient

## Deferred Ideas

None — discussion stayed within phase scope.
