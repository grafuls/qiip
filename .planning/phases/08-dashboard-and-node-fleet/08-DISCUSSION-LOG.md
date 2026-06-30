# Phase 8: Dashboard and Node Fleet - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-30
**Phase:** 08-dashboard-and-node-fleet
**Areas discussed:** Dashboard route & URL, Node status styling, CSS approach

---

## Dashboard Route & URL

| Option | Description | Selected |
|--------|-------------|----------|
| /dashboard | Dedicated path, clear intent. Operators bookmark /dashboard, admin API stays at /admin/*. | ✓ |
| /admin/dashboard | Nested under /admin namespace alongside the JSON API. Groups all ops tooling under one prefix. | |
| / (root) | Dashboard is the default page. Simplest URL, but takes over the root from FastAPI's default docs/redirect. | |

**User's choice:** /dashboard
**Notes:** None

### Data Source

| Option | Description | Selected |
|--------|-------------|----------|
| Server-side render | Template calls the registry directly during render — single request, no JS needed for initial load. | |
| Client-side fetch | Serve a static HTML shell, then JS fetches /admin/nodes on load. Phase 9 polling reuses the same fetch logic. | ✓ |
| You decide | Claude picks whichever fits cleanest with the codebase. | |

**User's choice:** Client-side fetch
**Notes:** None

---

## Node Status Styling

### Status Indicator

| Option | Description | Selected |
|--------|-------------|----------|
| Color badges | Colored pill/badge next to the status text — green for healthy, red for unhealthy, yellow for draining. | ✓ |
| Row highlighting | Entire row gets a tinted background color by status. More prominent, but can be noisy with many nodes. | |
| Color dot + text | Small colored circle indicator next to the status word. Subtle, compact. | |
| You decide | Claude picks what's standard for ops dashboards. | |

**User's choice:** Color badges
**Notes:** None

### Circuit Breaker Display

| Option | Description | Selected |
|--------|-------------|----------|
| Color badge too | Same badge style as node status — green/closed, red/open, yellow/half-open. Consistent visual language. | ✓ |
| Plain text | Just show "closed"/"open"/"half-open" as text. Keeps the status column as the main visual signal. | |
| You decide | Claude picks based on what reads cleanest. | |

**User's choice:** Color badge too
**Notes:** None

---

## CSS Approach

### Styling Method

| Option | Description | Selected |
|--------|-------------|----------|
| Custom minimal CSS | A single hand-written CSS file — table styling, badges, dark/light basics. Full control, ~100-150 lines. | |
| Classless CSS library | Drop in Simple.css or Water.css — instant polished look from semantic HTML alone. Small override for badges. | ✓ |
| You decide | Claude picks whatever gets to readable/functional fastest. | |

**User's choice:** Classless CSS library
**Notes:** None

### Library Choice

| Option | Description | Selected |
|--------|-------------|----------|
| Simple.css | ~4KB, good table styling, active maintenance. CDN link, no install. Most popular classless option. | ✓ |
| Water.css | ~2KB, slightly more minimal. CDN-hosted. Has dark mode toggle built in. | |
| Pico CSS | ~10KB, more features (modals, tooltips) but heavier. May be overkill for one page. | |
| You decide | Claude picks the lightest option that handles tables well. | |

**User's choice:** Simple.css
**Notes:** None

### Loading Method

| Option | Description | Selected |
|--------|-------------|----------|
| CDN link | One `<link>` tag in the template. Simplest, but requires internet access from operator's browser. | ✓ |
| Vendor as static file | Copy Simple.css into the project's static/ dir. Works on air-gapped networks. Slightly more setup. | |

**User's choice:** CDN link
**Notes:** None

---

## Claude's Discretion

- Page layout and structure — information hierarchy, summary header vs pure table, page title

## Deferred Ideas

None
