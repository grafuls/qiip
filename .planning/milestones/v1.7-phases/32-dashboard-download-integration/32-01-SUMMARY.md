---
phase: 32-dashboard-download-integration
plan: 01
subsystem: dashboard-ui
tags: [frontend, vanilla-js, download, polling]
dependency_graph:
  requires: [phase-30-catalog, phase-31-download-api]
  provides: [dashboard-download-ui]
  affects: [node_detail.js]
tech_stack:
  added: []
  patterns: [lazy-polling, optimistic-ui, graceful-degradation]
key_files:
  created: []
  modified:
    - inference_proxy/static/js/node_detail.js
decisions:
  - "Fetch catalog and downloads as independent requests with try/catch, not Promise.all, to prevent cascade failures"
  - "Promote completed downloads into catalogSetCache so poll renders match Reload renders"
  - "Start polling on Reload if any downloads are already active (handles tab-switch scenario)"
metrics:
  duration: "2m"
  completed: "2026-07-29T05:40:39Z"
---

# Phase 32 Plan 01: Dashboard Download Integration Summary

Download column with catalog cross-reference, optimistic trigger, and lazy 4s polling in node_detail.js

## Commits

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Add catalog cross-reference and Download column | 6c7622d | renderDownloadCell, parallel catalog+downloads fetch, 7th column |
| 2 | Add download trigger and status polling | c937188 | triggerDownload, startDownloadPolling, pollDownloadStatuses |

## What Was Built

Modified `inference_proxy/static/js/node_detail.js` to add download functionality to the recommendations table:

- **renderDownloadCell**: 4-state renderer (downloading -> complete/catalog -> failed -> default) with proper operator precedence
- **Parallel fetch**: `loadRecommendations()` fetches catalog and downloads alongside recommendations, each with independent error handling
- **triggerDownload**: Optimistic UI update (immediate badge swap), POST to `/admin/models/download`, toast feedback, retry on failure
- **Lazy polling**: `startDownloadPolling()` with single-timer guard (T-32-02), 4s interval, auto-stop when no active downloads
- **catalogSetCache**: Module-level Set shared between initial load and poll updater

## Deviations from Plan

None - plan executed exactly as written.

## Threat Flags

None found. All endpoints were pre-existing from phases 30-31. No new trust boundaries introduced.

## Known Stubs

None. All data sources are wired to live API endpoints.

## Verification

- `uv run pytest tests/api/test_dashboard.py -x` -- 34/34 passed (no template regressions)
- `uv run pytest` -- 565 passed, 3 pre-existing failures (test_runner.py, test_app.py lifespan tests unrelated to this change)

## Self-Check: PASSED
