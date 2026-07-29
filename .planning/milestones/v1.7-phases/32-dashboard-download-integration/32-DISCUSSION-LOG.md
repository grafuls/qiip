# Phase 32: Dashboard Download Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-28
**Phase:** 32-dashboard-download-integration
**Areas discussed:** Catalog cross-reference, Download status updates, Button state machine, Table column layout

---

## Catalog Cross-Reference

| Option | Description | Selected |
|--------|-------------|----------|
| Client-side merge | JS fetches both recommendations AND catalog, cross-references client-side. No backend changes. | ✓ |
| Server-side enrichment | Add 'downloaded' boolean to recommendations response. More backend work. | |
| Separate catalog fetch | Dedicated JS function fetches catalog independently and caches it. | |

**User's choice:** Client-side merge
**Notes:** Both endpoints already exist. Zero backend work needed.

---

## Download Status Updates

| Option | Description | Selected |
|--------|-------------|----------|
| Poll on timer | Poll GET /admin/models/downloads every 4s after download trigger. Stop when idle. | ✓ |
| Refresh on click only | No automatic polling. User clicks Load again manually. | |
| SSE stream | Stream download status via SSE. Requires new backend endpoint. | |

**User's choice:** Poll on timer
**Notes:** Matches existing setInterval pattern. Starts only after first download trigger.

---

## Button State Machine

| Option | Description | Selected |
|--------|-------------|----------|
| Three-state button | Download → Downloading... → Downloaded / Failed — Retry. Reuses existing badge CSS. | ✓ |
| Icon-only | Small icons for each state. Compact but less discoverable. | |
| Split: badge + button | Separate status badge and action button columns. | |

**User's choice:** Three-state button
**Notes:** Reuses existing badge-complete, badge-in-progress, badge-failed CSS classes.

---

## Table Column Layout

| Option | Description | Selected |
|--------|-------------|----------|
| New 'Download' column | Single column at end of table with three-state button/badge. | ✓ |
| Inline in Model column | Badge/button next to model name. Saves space but busier. | |
| Two columns: Status + Action | Separate columns for status and action. Most explicit but wider. | |

**User's choice:** New 'Download' column
**Notes:** Columns become: Model, Category, Score, Fit, Est. tok/s, Memory, Download.

---

## Claude's Discretion

None — all areas were discussed with the user.

## Deferred Ideas

None — discussion stayed within phase scope.
