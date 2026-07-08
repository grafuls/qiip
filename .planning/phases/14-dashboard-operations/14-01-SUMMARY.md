---
phase: 14-dashboard-operations
plan: 01
status: complete
started: 2026-07-08T10:00:00Z
completed: 2026-07-08T10:30:00Z
---

# Plan 14-01: Dashboard Operations UI

## What Was Built

Extended the existing Jinja2+vanilla JS dashboard with three operator workflows:

1. **Setup form** — Hostname input above the node table. Submits POST /admin/nodes/setup with JSON body, 2s button disable + flash confirmation, non-empty validation.

2. **Teardown buttons** — Actions column (8th) with per-node Teardown button. Confirm dialog, graceful only (no force param), disabled for provisioning/draining nodes.

3. **Provisioning tasks panel** — Section below the table showing task status with step badges (green=complete, red=failed, blue=in-progress). Polls on the same interval as node table via shared Promise.all in refreshDashboard().

## Key Files

- `inference_proxy/templates/dashboard.html` — Setup form, Actions column header, tasks panel section
- `inference_proxy/static/css/dashboard.css` — Badge classes for provisioning step states
- `inference_proxy/static/js/dashboard.js` — Form handler, teardown handler, tasks renderer, stepBadgeClass helper
- `tests/api/test_dashboard.py` — 22 tests covering HTML structure, form elements, tasks panel, badge CSS

## Commits

1. `feat(14-01): add setup form, actions column, tasks panel, and badge CSS` — Task 1: HTML structure, CSS badges, test coverage
2. `feat(14-01): add dashboard JS behavior for setup, teardown, and tasks` — Task 2: All dynamic behavior

## Self-Check: PASSED

- All 338 tests pass (`uv run pytest tests/ -x`)
- Setup form contains id="setup-form", id="setup-hostname", id="setup-btn"
- Actions column is 8th th, colspan updated to 8
- Tasks panel contains id="tasks-panel", id="tasks-table-body"
- dashboard.js contains fetch("/admin/provisioning/tasks") in Promise.all
- dashboard.js contains renderTasks, stepBadgeClass, handleTeardown functions
- dashboard.js uses textContent for all user-provided values (XSS prevention)
- Badge CSS contains .badge-complete, .badge-failed, .badge-in-progress

## Deviations

None.
