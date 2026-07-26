# Phase 27: Admin API Endpoint - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-26
**Phase:** 27-admin-api-endpoint
**Areas discussed:** Error response detail

---

## Error Response Detail

### Q1: Raw llmfit output in error responses?

| Option | Description | Selected |
|--------|-------------|----------|
| Log-only | Raw output stays in server logs (structlog). API response has just the error message. Simpler, no risk of leaking unexpected data. | ✓ |
| Include in response | Return raw_output field in the error response body so operators can debug without SSH-ing into the server. Useful since this is internal-only API. | |
| You decide | Let Claude pick the approach that best fits existing patterns in admin.py. | |

**User's choice:** Log-only
**Notes:** None

### Q2: Error type classification?

| Option | Description | Selected |
|--------|-------------|----------|
| Flat message only | HTTPException with detail string, same pattern as every other admin endpoint (power, teardown, etc.). | |
| Typed error body | Return {"error_type": "timeout", "detail": "..."} so dashboard JS can show different icons/messages per failure type. | ✓ |
| You decide | Let Claude pick based on existing patterns. | |

**User's choice:** Typed error body
**Notes:** None

### Q3: HTTP status code for llmfit failures?

| Option | Description | Selected |
|--------|-------------|----------|
| 502 for all | Treat llmfit as an upstream dependency (like Redfish uses 502). Consistent regardless of failure type. | ✓ |
| 502 for SSH, 422 for parse | SSH/timeout = upstream failure (502). Parse error = unprocessable response from llmfit (422). Gives clients more signal. | |
| You decide | Let Claude pick based on existing patterns. | |

**User's choice:** 502 for all
**Notes:** None

---

## Claude's Discretion

- Runner wiring (DI pattern, lifespan initialization)
- LLMFitSettings scope (timeout, binary path as env vars)
- Response model design (wrap LLMFitResult with hostname)
- Node validation (reuse _validated_hostname, no registry check required)
- Error response model structure

## Deferred Ideas

None — discussion stayed within phase scope.
