# Phase 29: Dashboard Recommendations - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-26
**Phase:** 29-dashboard-recommendations
**Areas discussed:** Table columns

---

## Table Columns

### Column count

| Option | Description | Selected |
|--------|-------------|----------|
| DASH-01 five | name, score, fit_level, estimated_tps, memory_required_gb — matches requirement spec exactly | ✓ |
| Add params_b + quant | 7 columns: the five above plus parameter count and quantization | |
| Wider set | 9+ columns including category, context_length, utilization_pct | |

**User's choice:** DASH-01 five columns
**Notes:** None

### Score display format

| Option | Description | Selected |
|--------|-------------|----------|
| Numeric (0.85) | Raw float from llmfit, consistent with API response | |
| Percentage (85%) | Multiply by 100, more intuitive at a glance | ✓ |
| Bar + number | Small inline bar with numeric value | |

**User's choice:** Percentage
**Notes:** None

### Fit level styling

| Option | Description | Selected |
|--------|-------------|----------|
| Badge with color | Reuse existing badge pattern (badge-complete/in-progress/failed) | ✓ |
| Plain text | Just the text value, no visual emphasis | |

**User's choice:** Badge with color
**Notes:** None

### Memory column units

| Option | Description | Selected |
|--------|-------------|----------|
| GB with 1 decimal | e.g. '14.2 GB' — matches SystemInfo format | ✓ |
| Raw GB number | e.g. '14.2' with 'GB' in column header | |

**User's choice:** GB with 1 decimal
**Notes:** None

---

## Claude's Discretion

- Loading trigger (auto-load vs button click)
- Error display strategy (how to show llmfit failures)
- Card placement on node detail page
- Empty state messaging

## Deferred Ideas

None — discussion stayed within phase scope.
