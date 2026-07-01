---
phase: 09-live-metrics-and-auto-refresh
plan: 01
subsystem: dashboard
tags: [metrics, polling, auto-refresh, dashboard]
dependency_graph:
  requires: [phase-07-request-metrics, phase-08-dashboard-skeleton]
  provides: [live-dashboard-polling, per-node-request-counts]
  affects: [dashboard-ui, settings]
tech_stack:
  added: []
  patterns: [jinja2-context-injection, parallel-fetch, setInterval-polling]
key_files:
  created: []
  modified:
    - inference_proxy/config/settings.py
    - inference_proxy/api/dashboard.py
    - inference_proxy/templates/dashboard.html
    - inference_proxy/static/js/dashboard.js
    - inference_proxy/static/css/dashboard.css
    - tests/api/test_dashboard.py
    - tests/config/test_settings.py
    - .env.example
decisions:
  - DashboardSettings sub-model follows existing GatewaySettings pattern
  - POLL_INTERVAL_MS injected as inline script before dashboard.js load
  - Poll failure keeps stale data visible with amber warning text
metrics:
  duration: 214s
  completed: "2026-07-01T12:55:13Z"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 7
  tests_total: 265
---

# Phase 09 Plan 01: Live Metrics and Auto-Refresh Summary

DashboardSettings sub-model with configurable poll_interval (default 10s), parallel-fetch JS polling loop rendering per-node request counts in a 7-column table with last-updated timestamp and error resilience.

## What Was Done

### Task 1: Backend config, route injection, template, and CSS (bbf3350)

- Added `DashboardSettings(BaseModel)` with `poll_interval: int = 10` to settings
- Registered `dashboard: DashboardSettings` on root `Settings` class
- Injected `poll_interval` into dashboard template context via `Depends(get_settings)`
- Added 7th "Requests" column header to template thead
- Updated loading row colspan from 6 to 7
- Added inline `<script>` block injecting `POLL_INTERVAL_MS` as numeric literal
- Added `#last-updated` and `#poll-warning` elements to template
- Added `.last-updated` and `.poll-warning` CSS classes
- Added `INFERENCE_PROXY_DASHBOARD__POLL_INTERVAL` to `.env.example`

### Task 2: JS polling loop with parallel fetch and tests (7d8a76b)

- Replaced `loadNodes()` with `refreshDashboard()` using `Promise.all` for parallel `/admin/nodes` + `/admin/metrics` fetch
- Added 7th table cell rendering `perNode[node.node_id] || 0` request counts
- Added `setInterval(refreshDashboard, POLL_INTERVAL_MS)` polling loop
- On success: updates last-updated timestamp, clears warning
- On failure: shows warning text without clearing table (stale data preserved)
- Added 7 new tests: DashboardSettings defaults/env override/sub-model check, polling JS variable, default value, last-updated element, poll-warning element
- Updated column header test from 6 to 7 columns

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- `uv run pytest tests/api/test_dashboard.py tests/config/test_settings.py -x -v`: 27 passed
- `uv run pytest`: 265 passed (full suite)
- `uv run mypy inference_proxy/config/settings.py inference_proxy/api/dashboard.py`: no issues

## Commits

| Task | Commit  | Description |
|------|---------|-------------|
| 1    | bbf3350 | Backend config, route injection, template, CSS |
| 2    | 7d8a76b | JS polling loop, request counts, tests |

## Self-Check: PASSED

All 8 modified files verified present. Both task commits (bbf3350, 7d8a76b) verified in git log.
