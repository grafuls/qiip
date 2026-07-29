---
phase: 32-dashboard-download-integration
verified: 2026-07-29T06:15:00Z
status: human_needed
score: 6/6
overrides_applied: 0
human_verification:
  - test: "Load node detail page, click Load for recommendations. Verify 7th Download column appears with correct states."
    expected: "Models on NFS show green 'Downloaded' badge. Models not on NFS show 'Download' button."
    why_human: "Requires running server with live data to verify visual rendering and NFS cross-reference."
  - test: "Click Download on a model. Observe button state change and toast."
    expected: "Button immediately changes to 'Downloading...' badge. Toast says 'Download started for <repo_id>'. Network tab shows POST to /admin/models/download."
    why_human: "Requires running server and real download trigger to verify optimistic UI and toast."
  - test: "Observe poll cycle in network tab after triggering a download."
    expected: "GET /admin/models/downloads every 4s. Badge changes to 'Downloaded' on completion. Polling stops when no active downloads (no more requests in network tab)."
    why_human: "Requires real-time observation of network requests and status transitions."
  - test: "Simulate or observe a failed download. Verify retry button."
    expected: "Failed download shows 'Failed -- Retry' badge in red. Clicking it re-triggers the download."
    why_human: "Requires a download failure scenario to verify error state rendering."
---

# Phase 32: Dashboard Download Integration Verification Report

**Phase Goal:** Operators can trigger and monitor model downloads directly from the recommendations table
**Verified:** 2026-07-29T06:15:00Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Each recommended model row has a Download column cell | VERIFIED | Line 457: `<th>Download</th>` in header. Lines 477-482: loop appends `td` with `renderDownloadCell` to each tbody row. |
| 2 | Models already on NFS show a 'Downloaded' badge instead of a button | VERIFIED | Lines 311-313: `catalogSet.has(modelName)` or `dl.status === "complete"` renders `badge badge-complete` with text "Downloaded". catalogSet built from GET /admin/models/catalog (lines 427-430). |
| 3 | Clicking Download triggers POST and button changes to 'Downloading...' | VERIFIED | Lines 323-329: default button with click listener calling `triggerDownload`. Lines 333-358: optimistic UI swaps to "Downloading..." badge immediately, then POSTs to `/admin/models/download`. |
| 4 | Download status auto-updates via 4s poll without page refresh | VERIFIED | Lines 361-364: `startDownloadPolling` with single-timer guard, `setInterval(pollDownloadStatuses, 4000)`. Lines 367-392: polls `/admin/models/downloads`, updates cells via `renderDownloadCell`, stops when no active downloads. |
| 5 | Failed downloads show 'Failed -- Retry' with a clickable retry | VERIFIED | Lines 315-321: `dl.status === "failed"` renders button with `badge badge-failed`, text "Failed -- Retry", click listener calling `triggerDownload`. |
| 6 | Catalog fetch failure degrades gracefully -- table still renders with Download buttons | VERIFIED | Lines 426-431: catalog fetch in try/catch, defaults to empty Set. Lines 432-439: downloads fetch in independent try/catch, defaults to empty object. Empty catalogSet + empty downloadMap falls through to default "Download" button (line 323). |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `inference_proxy/static/js/node_detail.js` | Download column, catalog cross-ref, polling, trigger. Contains `downloadPollTimer`. | VERIFIED | File exists (510 lines). Contains `downloadPollTimer` (line 297), `renderDownloadCell` (line 299), `triggerDownload` (line 333), `startDownloadPolling` (line 361), `pollDownloadStatuses` (line 367). All substantive implementations, no stubs. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `node_detail.js` | `/admin/models/catalog` | fetch in loadRecommendations | WIRED | Line 428: `fetch("/admin/models/catalog")`. Response parsed and used to build `catalogSet` (line 430). |
| `node_detail.js` | `/admin/models/download` | fetch POST on button click | WIRED | Line 342: `fetch("/admin/models/download", { method: "POST", ... })`. Response checked for ok/error, triggers toast and polling (lines 347-354). |
| `node_detail.js` | `/admin/models/downloads` | fetch in poll timer | WIRED | Line 369: `fetch("/admin/models/downloads")`. Response parsed into downloadMap, cells updated via renderDownloadCell (lines 374-384). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `node_detail.js` | `catalogSet` | GET /admin/models/catalog | Yes -- built from `catalogData.models.map(m => m.repo_id)` (line 430) | FLOWING |
| `node_detail.js` | `downloadMap` | GET /admin/models/downloads | Yes -- built from response array keyed by repo_id (lines 374-375, 436-438) | FLOWING |
| `node_detail.js` | cell rendering | `renderDownloadCell` | Yes -- dynamically creates DOM elements based on download/catalog state (lines 299-331) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Dashboard tests pass | `uv run pytest tests/api/test_dashboard.py -x` | 34/34 passed | PASS |
| JS file contains all expected functions | `grep -c 'renderDownloadCell\|triggerDownload\|startDownloadPolling\|pollDownloadStatuses' node_detail.js` | 4 distinct functions found | PASS |
| Template loads the JS file | `grep 'node_detail.js' templates/node_detail.html` | Line 114: `<script src="{{ url_for('static', path='js/node_detail.js') }}"></script>` | PASS |
| CSS classes exist | `grep 'btn-setup\|badge-complete\|badge-in-progress\|badge-failed' dashboard.css` | All 4 classes found in dashboard.css | PASS |

### Probe Execution

Step 7c: SKIPPED (no probe scripts found for this phase)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DASH-01 | 32-01-PLAN | Node detail recommendations table shows a download button per recommended model | SATISFIED | Download button rendered in default case (lines 323-329). Column header added (line 457). Cells appended to each row (lines 477-482). |
| DASH-02 | 32-01-PLAN | Recommendations table shows "already downloaded" badge when a model exists on NFS | SATISFIED | Catalog cross-reference via `catalogSet.has(modelName)` renders "Downloaded" badge (lines 311-313). Catalog fetched from `/admin/models/catalog` (lines 427-430). |
| DASH-03 | 32-01-PLAN | Download status (downloading/complete/failed) is visible in the recommendations table | SATISFIED | All three states rendered in `renderDownloadCell` (lines 305-331). Auto-updates via 4s poll (lines 361-392). |

No orphaned requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | -- | -- | -- | No debt markers, stubs, or anti-patterns found in phase 32 code |

The "placeholder" grep hits (lines 287, 290) are in the pre-existing log viewer code, not in code modified by this phase.

### Human Verification Required

### 1. Visual Rendering of Download Column

**Test:** Load node detail page, click Load for recommendations. Verify 7th "Download" column appears.
**Expected:** Models on NFS show green "Downloaded" badge. Models not on NFS show "Download" button.
**Why human:** Requires running server with live data to verify visual rendering and NFS cross-reference.

### 2. Download Trigger and Optimistic UI

**Test:** Click Download on a model. Observe button state change and toast notification.
**Expected:** Button immediately changes to "Downloading..." badge. Toast says "Download started for <repo_id>". Network tab shows POST to /admin/models/download.
**Why human:** Requires running server and real download trigger to verify optimistic UI update and toast feedback.

### 3. Polling and Auto-Stop

**Test:** Observe poll cycle in network tab after triggering a download.
**Expected:** GET /admin/models/downloads every 4s. Badge changes to "Downloaded" on completion. Polling stops when no active downloads.
**Why human:** Requires real-time observation of network requests and status transitions.

### 4. Failed Download Retry

**Test:** Simulate or observe a failed download. Verify retry button appears.
**Expected:** Failed download shows red "Failed -- Retry" badge. Clicking it re-triggers the download.
**Why human:** Requires a download failure scenario to verify error state rendering.

### Gaps Summary

No gaps found. All 6 observable truths verified in the codebase. All 3 requirements (DASH-01, DASH-02, DASH-03) satisfied. All 3 key links wired. No anti-patterns or debt markers.

Status is `human_needed` because this is a UI-facing phase -- visual rendering, real-time polling behavior, and toast notifications require manual verification in a browser.

---

_Verified: 2026-07-29T06:15:00Z_
_Verifier: Claude (gsd-verifier)_
