# Phase 7: Request Metrics and Admin API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-29
**Phase:** 07-request-metrics-and-admin-api
**Areas discussed:** What gets counted

---

## What Gets Counted

### Q1: Which requests should the gateway count?

| Option | Description | Selected |
|--------|-------------|----------|
| Proxied inference only | Only POST /v1/chat/completions and /v1/completions — what operators care about | ✓ |
| All HTTP requests | Everything hitting the gateway including /health, /admin/*, /v1/models | |
| You decide | Let Claude pick the best approach | |

**User's choice:** Proxied inference only
**Notes:** None

### Q2: Total counts or success/error breakdown?

| Option | Description | Selected |
|--------|-------------|----------|
| Total counts only | Simple integer counters: total, per-node, per-model. METR-01 says 'request count' | ✓ |
| Success + error breakdown | Separate success/error counters per dimension | |
| You decide | Let Claude pick based on requirements | |

**User's choice:** Total counts only
**Notes:** None

### Q3: How to count retries?

| Option | Description | Selected |
|--------|-------------|----------|
| Count each attempt | Per-node counter increments on every attempt. Total counter increments once. | ✓ |
| Count only the final result | Only the node that ultimately served the response gets counted | |
| You decide | Let Claude pick for operator visibility | |

**User's choice:** Count each attempt
**Notes:** Reflects actual load per node

---

## Claude's Discretion

- Metrics API shape: new endpoint vs extending /admin/nodes vs both
- Counter structure: dict+lock pattern vs other approaches

## Deferred Ideas

None — discussion stayed within phase scope
