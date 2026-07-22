---
phase: 24-provisioning-error-diagnostics
plan: 02
subsystem: dashboard-error-display
tags: [dashboard, error-display, frontend, accessibility]
dependency_graph:
  requires: [NodeStatus.FAILED, AdminNodeResponse-error-fields]
  provides: [expandable-error-subrow, failed-badge-toggle]
  affects: [inference_proxy/static/js/dashboard.js, inference_proxy/static/css/dashboard.css]
tech_stack:
  added: []
  patterns: [click-to-expand-subrow, aria-expanded-toggle, textContent-xss-prevention]
key_files:
  created: []
  modified:
    - inference_proxy/static/js/dashboard.js
    - inference_proxy/static/css/dashboard.css
decisions:
  - "Use textContent (not innerHTML) for all error rendering to prevent XSS"
  - "Reuse existing badge-failed class for step label in sub-row"
  - "Use pre element with pre-wrap for error text to preserve formatting without truncation"
metrics:
  duration: 129s
  completed: 2026-07-22T11:26:06Z
  tasks_completed: 1
  tasks_total: 2
  test_count: 502
---

# Phase 24 Plan 02: Dashboard Error Display Summary

Expandable error sub-row in fleet table with click-to-toggle failed badge, keyboard accessible, styled with existing design tokens.

## Task Summary

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Dashboard expandable error sub-row and CSS styling | ec0150a | dashboard.js, dashboard.css |
| 2 | Visual verification of error sub-row | pending | (checkpoint: human-verify) |

## Changes Made

### Task 1: Dashboard expandable error sub-row and CSS styling
- In `refreshDashboard()`, after appending a failed node's `<tr>`, creates an `.error-subrow` `<tr>` when `node.failed_step` or `node.error` exists
- Failed state badge gets `cursor: pointer`, `role="button"`, `tabindex="0"`, `aria-expanded` for accessibility
- Click and Enter/Space keydown handlers toggle sub-row display between `none` and `table-row`
- Sub-row contains `<td colspan="7">` with `.error-detail` div holding step badge and `<pre>` error text
- CSS: `.error-subrow` overrides hover highlight, `.error-detail` uses `var(--danger-bg)` background, `.error-message` uses IBM Plex Mono with `pre-wrap`
- All error content rendered via `textContent` (zero `innerHTML` usage) per threat model T-24-03

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- Full test suite: 502 passed, 0 failed
- `error-subrow` in dashboard.js: 1 (present)
- `error-detail` in dashboard.css: 1 (present)
- `aria-expanded` in dashboard.js: 2 (set + update)
- `innerHTML` in dashboard.js: 0 (XSS safe)
- `colSpan = 7` in dashboard.js: 2 (empty state + error subrow)
- `pre-wrap` in dashboard.css: 1 (present)

## Self-Check: PASSED
