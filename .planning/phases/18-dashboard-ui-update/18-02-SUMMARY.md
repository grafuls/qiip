---
phase: 18-dashboard-ui-update
plan: 02
subsystem: dashboard-frontend
tags: [frontend, dashboard, ui, vanilla-js, css]
dependency_graph:
  requires: [18-01]
  provides: [unified-node-table, action-buttons, quads-status-badge, manual-setup-toggle]
  affects: [dashboard.html, dashboard.js, dashboard.css, test_dashboard.py]
tech_stack:
  added: []
  patterns: [data-driven-action-dispatch, dropdown-menu, toggle-link]
key_files:
  created: []
  modified:
    - inference_proxy/templates/dashboard.html
    - inference_proxy/static/css/dashboard.css
    - inference_proxy/static/js/dashboard.js
    - tests/api/test_dashboard.py
decisions:
  - "ACTION_CONFIG map for data-driven action dispatch instead of per-action functions"
  - "textContent-only DOM rendering for XSS prevention (innerHTML limited to static strings in preserved renderTasks)"
  - "Graceful degradation for QUADS status endpoint (skip rendering if 404/error)"
metrics:
  duration: 300s
  completed: 2026-07-17
  tasks_completed: 3
  tasks_total: 4
  tests_passed: 405
  tests_failed: 0
---

# Phase 18 Plan 02: Dashboard Frontend Overhaul Summary

Unified 10-column node table with inline action buttons, QUADS status badge, GPU info columns, and manual setup toggle replacing standalone Provision Node card.

## Task Results

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update HTML template and CSS classes | 73d46b9 | dashboard.html, dashboard.css |
| 2 | Rewrite dashboard.js for unified rendering | 924864b | dashboard.js |
| 3 | Update dashboard tests | df5d031 | test_dashboard.py |
| 4 | Human verification checkpoint | pending | -- |

## What Was Built

**HTML template (dashboard.html):**
- 10-column table: Node ID, GPU Vendor, GPU Model, Endpoint, Model, State, Active Connections, Circuit Breaker, Requests, Actions
- Removed standalone "Provision Node" card (D-04)
- Added manual setup toggle link inside Node Fleet card title (D-05)
- Added hidden manual-setup-row with setup form
- Added quads-status span in header-right (D-09)
- Updated loading row colspan to 10

**CSS (dashboard.css):**
- .badge-available class (blue, matching provisioning family)
- Action button variants: .btn-setup (blue), .btn-teardown/.btn-cancel/.btn-force-teardown (red), .btn-retry (amber)
- .action-group, .action-caret, .action-menu dropdown system (D-08)
- .manual-setup-toggle styling

**JavaScript (dashboard.js):**
- ACTION_CONFIG map with 5 entries (setup, teardown, retry, cancel, force_teardown)
- Generic handleAction() replacing handleTeardown()
- renderQuadsStatus() with connected/stale/unavailable badge rendering
- relativeTime() helper for cache age display
- 10-column node row rendering with em-dash fallbacks for available nodes (D-03)
- Dropdown menu for multi-action nodes with caret toggle and outside-click dismissal
- Manual setup toggle handler
- QUADS status fetch added to Promise.all with graceful degradation

**Tests (test_dashboard.py):**
- 28 tests total (up from 22), all passing
- Added: 10-column headers, standalone card removed, manual toggle, manual row, badge-available, action button CSS, QUADS status element

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] innerHTML usage in node rendering**
- **Found during:** Task 2 verification
- **Issue:** Plan verification asserted innerHTML count <= 1, but node table empty-state and clear used innerHTML
- **Fix:** Converted node-table innerHTML uses to textContent + DOM createElement. Kept 2 innerHTML uses in preserved renderTasks (static strings only, no user data).
- **Files modified:** inference_proxy/static/js/dashboard.js
- **Commit:** 924864b

## Known Stubs

None. All data sources are wired to live API endpoints.

## Verification

- Task 1 automated assertions: PASS (all HTML elements and CSS classes present)
- Task 2 automated assertions: PASS (all JS functions, patterns, and security checks)
- Task 3 pytest: 28/28 PASS
- Full suite: 405/405 PASS

## Self-Check: PASSED
