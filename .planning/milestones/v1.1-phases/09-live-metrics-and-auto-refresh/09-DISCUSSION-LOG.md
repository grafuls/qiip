# Phase 9: Live Metrics and Auto-Refresh - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-01
**Phase:** 09-live-metrics-and-auto-refresh
**Areas discussed:** Metrics placement, Polling config, Refresh UX

---

## Metrics Placement

| Option | Description | Selected |
|--------|-------------|----------|
| New column in node table | Add a 'Requests' column to the existing table. One fetch, one table, single view. | ✓ |
| Separate metrics section | Summary block above or below the node table showing total, per-model, and per-node counts. | |
| Both | Request count column in node table plus a summary header with total and per-model breakdown. | |

**User's choice:** New column in node table
**Notes:** None

### Follow-up: Aggregate totals

| Option | Description | Selected |
|--------|-------------|----------|
| Total in header + per-node in table | Header shows 'N nodes registered · M total requests'. Per-node counts in table column. | |
| Per-node only | Just the new column in the table. Total is implicit (sum the column). | ✓ |

**User's choice:** Per-node only
**Notes:** None

---

## Polling Config

### Configurability approach

| Option | Description | Selected |
|--------|-------------|----------|
| Backend env var only | INFERENCE_PROXY_DASHBOARD__POLL_INTERVAL env var, injected into template as JS variable. | ✓ |
| UI dropdown on page | Dropdown on dashboard itself (5s/10s/30s/off). JS-only, no backend setting. | |
| Both | Backend env var sets default, page has UI control to override per-session. | |

**User's choice:** Backend env var only
**Notes:** None

### Default interval

| Option | Description | Selected |
|--------|-------------|----------|
| 10 seconds | Responsive enough for monitoring, low overhead. Good for internal ops tool. | ✓ |
| 30 seconds | More conservative. Fine for glancing, not actively watching. | |
| 5 seconds | Near real-time feel. More API calls but internal traffic. | |

**User's choice:** 10 seconds
**Notes:** None

### Fetch strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Two fetches (nodes + metrics) | Keep existing endpoints unchanged. JS calls both in parallel. Clean API separation. | ✓ |
| One fetch (enrich /admin/nodes) | Add request_count field to AdminNodeResponse. Single fetch but mixes concerns. | |
| You decide | Claude picks whichever fits existing code best. | |

**User's choice:** Two fetches (nodes + metrics)
**Notes:** None

---

## Refresh UX

### Last-updated indicator

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, last-updated timestamp | Small text like 'Last updated: 10:42:15' in the header or footer. | ✓ |
| No, just silently refresh | Table updates in place, no timestamp. Simpler. | |

**User's choice:** Yes, last-updated timestamp
**Notes:** None

### Poll failure handling

| Option | Description | Selected |
|--------|-------------|----------|
| Show stale data + warning | Keep last successful data, show subtle warning that clears on next success. | ✓ |
| Show error state | Replace table content with error message. More disruptive but clear. | |
| Silently retry | Skip failed poll and try again next interval. No visual feedback. | |

**User's choice:** Show stale data + warning
**Notes:** None

---

## Claude's Discretion

- Placement of "Last updated" text (header, footer, or near table)
- Warning text and styling for poll failure state
- Whether to add poll interval to a new DashboardSettings sub-model or extend existing settings group

## Deferred Ideas

None — discussion stayed within phase scope
